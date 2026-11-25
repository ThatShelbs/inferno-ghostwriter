"""Wiring: one place that builds every long-lived service the API uses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session

from inferno_ghostwriter.config import SecondaryProvider, SecondarySettings, Settings
from inferno_ghostwriter.db import AppSetting, make_engine
from inferno_ghostwriter.idealab.collect import HttpSignalCollector, NoSignalCollector, SignalCollector
from inferno_ghostwriter.images import ImageService
from inferno_ghostwriter.jobs import JobManager
from inferno_ghostwriter.legacy import LEGACY_KEYRING_SERVICE, copy_legacy_secrets
from inferno_ghostwriter.llm import LLM
from inferno_ghostwriter.llm.auth import ClaudeAuth
from inferno_ghostwriter.llm.claude import ClaudeLLM
from inferno_ghostwriter.llm.claude_code import ClaudeCodeLLM
from inferno_ghostwriter.llm.router import RoutingLLM
from inferno_ghostwriter.llm.secondary import SecondaryCLI
from inferno_ghostwriter.secrets import KeyringSecretStore, SecretStore
from inferno_ghostwriter.storage import Storage
from inferno_ghostwriter.writer.links import HttpLinkChecker, LinkChecker, NoLinkChecker
from inferno_ghostwriter.writer.pages import HttpPageReader, NoPageReader, PageReader

# Settings the user can change in the app; persisted in the app_setting table.
RUNTIME_SETTINGS = (
    "claude_connection",
    "model",
    "use_fallbacks",
    "secondary",
    "revision_passes",
    "ai_detection",
    "detector_models",
    "humanize_rounds",
    "reference_max_searches",
    "check_reference_links",
    "image_quality",
)


@dataclass
class Services:
    settings: Settings
    engine: Engine
    storage: Storage
    secrets: SecretStore
    auth: ClaudeAuth
    secondary: dict[SecondaryProvider, SecondaryCLI]
    llm: LLM
    images: ImageService
    jobs: JobManager
    # Checks that reference URLs still exist; tests and demo mode trust every link instead of going online.
    links: LinkChecker
    # Reads a page the author pastes as a reference; tests and demo mode use a canned page.
    pages: PageReader
    # Reads the Idea Lab's free feeds; tests and demo mode use canned items instead of going online.
    signals: SignalCollector

    def save_runtime_setting(self, key: str, value: Any) -> None:
        if key not in RUNTIME_SETTINGS:
            raise KeyError(key)
        with Session(self.engine) as session:
            row = session.get(AppSetting, key) or AppSetting(key=key)
            row.value = value.model_dump() if isinstance(value, SecondarySettings) else value
            session.add(row)
            session.commit()
        setattr(self.settings, key, value)
        if key == "image_quality":
            self.settings.apply_image_quality()


def load_runtime_settings(engine: Engine, settings: Settings) -> None:
    with Session(engine) as session:
        for key in RUNTIME_SETTINGS:
            row = session.get(AppSetting, key)
            if row is not None and row.value is not None:
                value = SecondarySettings.model_validate(row.value) if key == "secondary" else row.value
                setattr(settings, key, value)
        settings.apply_image_quality()
        # Older versions had one switch for both trained detectors ("deep_check"): keep them selected for those authors.
        old = session.get(AppSetting, "deep_check")
        if old is not None and old.value is True and session.get(AppSetting, "detector_models") is None:
            settings.detector_models = ["light", "curvature", "classifier"]


def build_services(
    settings: Settings,
    *,
    secrets: SecretStore | None = None,
    llm: LLM | None = None,
    auth: ClaudeAuth | None = None,
    inline_jobs: bool = False,
    links: LinkChecker | None = None,
    pages: PageReader | None = None,
    signals: SignalCollector | None = None,
) -> Services:
    # Only the real Claude finds real links worth checking; a stand-in LLM (tests, demo mode) never goes online.
    links = links or (HttpLinkChecker() if llm is None and not settings.demo else NoLinkChecker())
    pages = pages or (HttpPageReader() if llm is None and not settings.demo else NoPageReader())
    signals = signals or (HttpSignalCollector() if llm is None and not settings.demo else NoSignalCollector())
    engine = make_engine(settings.db_path)
    load_runtime_settings(engine, settings)
    storage = Storage(settings.data_dir)
    if settings.demo:
        from inferno_ghostwriter.demo import FakeLLM
        from inferno_ghostwriter.secrets import MemorySecretStore

        secrets = secrets or MemorySecretStore({"anthropic_api_key": "demo-mode"})
        llm = llm or FakeLLM(delay=0.03, showcase=True)
    if secrets is None:
        secrets = KeyringSecretStore(settings.keyring_service)
        copy_legacy_secrets(secrets, KeyringSecretStore(LEGACY_KEYRING_SERVICE))
    auth = auth or ClaudeAuth(secrets)
    secondary: dict[SecondaryProvider, SecondaryCLI] = {
        "codex": SecondaryCLI("codex", discover=llm is None),
        "gemini": SecondaryCLI("gemini", discover=llm is None),
    }
    llm = llm or RoutingLLM(
        settings,
        api=ClaudeLLM(settings, auth.build_client),
        subscription=ClaudeCodeLLM(settings, auth.claude_code),
        secondary=secondary,
        claude_ready=lambda: auth.status(settings.claude_connection).signed_in,
    )
    images = ImageService(engine=engine, llm=llm, settings=settings, storage=storage)
    jobs = JobManager(engine, inline=inline_jobs)
    return Services(
        settings=settings,
        engine=engine,
        storage=storage,
        secrets=secrets,
        auth=auth,
        secondary=secondary,
        llm=llm,
        images=images,
        jobs=jobs,
        links=links,
        pages=pages,
        signals=signals,
    )

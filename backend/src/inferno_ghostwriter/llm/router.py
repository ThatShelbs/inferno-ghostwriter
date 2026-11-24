"""Keep Claude primary while honoring opt-in model choices for eligible stages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from inferno_ghostwriter.config import SecondaryProvider, Settings, WritingProvider
from inferno_ghostwriter.llm.base import (
    LLM,
    LLMError,
    LLMLimitError,
    LLMNotConfiguredError,
    LLMRefusalError,
    OnDelta,
    OnReset,
    ResearchResult,
    SystemBlock,
    T,
    UsageSink,
)
from inferno_ghostwriter.llm.secondary import MODEL_IDS, SecondaryCLI

log = logging.getLogger(__name__)
PROVIDERS = {model: provider for provider, model in MODEL_IDS.items()}
STAGES = {"draft": "draft", "critique": "critique", "revision": "revision", "post tweak": "tweak"}
FALLBACK_TASKS = {
    *STAGES,
    "post plan",
    "title options",
    "humanize",
    "idea ranking",
    "idea research digest",
    "reference plan",
    "reference weave",
    "interview",
    "linkedin post",
    "opening ideas",
    "meme ideas",
}


class RoutingLLM:
    """Reads ``settings.claude_connection`` on every call, so switching needs no restart."""

    def __init__(
        self,
        settings: Settings,
        *,
        api: LLM,
        subscription: LLM,
        secondary: dict[SecondaryProvider, SecondaryCLI] | None = None,
        claude_ready: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.api = api
        self.subscription = subscription
        self.secondary = secondary or {}
        self.claude_ready = claude_ready

    @property
    def active(self) -> LLM:
        return self.subscription if self.settings.claude_connection == "subscription" else self.api

    def _preferred(self, task: str) -> WritingProvider:
        stage = STAGES.get(task)
        if stage is None and task.startswith("passage "):
            stage = "tweak"
        return getattr(self.settings.secondary, stage) if stage is not None else "claude"

    def _fallback(self, task: str, images: list[bytes] | None) -> list[SecondaryProvider]:
        if task not in FALLBACK_TASKS and not task.startswith(("ideas ", "passage ")):
            return []
        return [
            provider
            for provider in dict.fromkeys(self.settings.secondary.fallback)
            if provider in self.secondary and (not images or provider == "codex")
        ]

    async def _connected_cli(self, provider: SecondaryProvider) -> SecondaryCLI:
        cli = self.secondary.get(provider)
        if cli is None:
            raise LLMError("This optional model connection is unavailable.")
        if self.claude_ready and not await asyncio.to_thread(self.claude_ready):
            raise LLMNotConfiguredError()
        return cli

    async def _secondary_structured(
        self,
        provider: SecondaryProvider,
        *,
        task: str,
        system: list[SystemBlock],
        prompt: str,
        schema: type[T],
        images: list[bytes] | None = None,
        usage: UsageSink | None = None,
    ) -> T:
        cli = await self._connected_cli(provider)
        result = await cli.complete(system=system, prompt=prompt, schema=schema, images=images, usage=usage)
        if not isinstance(result, schema):
            raise LLMError(f"{cli.label} returned an invalid {task} response.")
        return result

    async def structured(
        self,
        *,
        task: str,
        system: list[SystemBlock],
        prompt: str,
        schema: type[T],
        effort: str,
        max_tokens: int = 16000,
        usage: UsageSink | None = None,
        images: list[bytes] | None = None,
        model: str | None = None,
    ) -> T:
        explicit = PROVIDERS.get(model) if model else None
        if explicit:
            # An independent judge or brainstormer must never silently become a second Claude vote.
            return await self._secondary_structured(
                explicit, task=task, system=system, prompt=prompt, schema=schema, images=images, usage=usage
            )
        preferred = self._preferred(task)
        if preferred != "claude":
            try:
                return await self._secondary_structured(
                    preferred, task=task, system=system, prompt=prompt, schema=schema, images=images, usage=usage
                )
            except LLMRefusalError:
                raise
            except LLMError as exc:
                log.info("Secondary %s unavailable during %s: %s", preferred, task, exc)
        try:
            return await self.active.structured(
                task=task,
                system=system,
                prompt=prompt,
                schema=schema,
                effort=effort,
                max_tokens=max_tokens,
                usage=usage,
                images=images,
                model=model,
            )
        except LLMLimitError:
            for provider in self._fallback(task, images):
                if provider == preferred:
                    continue
                try:
                    return await self._secondary_structured(
                        provider, task=task, system=system, prompt=prompt, schema=schema, images=images, usage=usage
                    )
                except LLMRefusalError:
                    raise
                except LLMError as exc:
                    log.info("Secondary fallback %s unavailable during %s: %s", provider, task, exc)
            raise

    async def text(
        self,
        *,
        task: str,
        system: list[SystemBlock],
        prompt: str,
        effort: str,
        max_tokens: int = 64000,
        on_delta: OnDelta | None = None,
        usage: UsageSink | None = None,
        on_reset: OnReset | None = None,
    ) -> str:
        preferred = self._preferred(task)
        fallback = [provider for provider in self._fallback(task, None) if provider != preferred]

        streamed = False

        async def secondary_text(provider: SecondaryProvider) -> str | None:
            try:
                cli = await self._connected_cli(provider)
                value = await cli.complete(system=system, prompt=prompt, usage=usage)
            except LLMRefusalError:
                raise
            except LLMError as exc:
                log.info("Secondary %s unavailable during %s: %s", provider, task, exc)
                return None
            if not isinstance(value, str):
                return None
            if on_delta:
                if streamed and on_reset:
                    await on_reset()
                await on_delta(value)
            return value

        if preferred != "claude" and (result := await secondary_text(preferred)) is not None:
            return result

        async def delta(value: str) -> None:
            nonlocal streamed
            if on_delta:
                await on_delta(value)
                streamed = True

        try:
            return await self.active.text(
                task=task,
                system=system,
                prompt=prompt,
                effort=effort,
                max_tokens=max_tokens,
                on_delta=delta if on_delta and fallback else on_delta,
                usage=usage,
            )
        except LLMLimitError:
            # The preview is append-only. Do not append another provider's draft to a partial Claude draft.
            if not streamed or on_reset:
                for provider in fallback:
                    if (result := await secondary_text(provider)) is not None:
                        return result
            raise

    async def research(
        self,
        *,
        system: list[SystemBlock],
        prompt: str,
        effort: str,
        max_searches: int = 8,
        usage: UsageSink | None = None,
    ) -> ResearchResult:
        return await self.active.research(system=system, prompt=prompt, effort=effort, max_searches=max_searches, usage=usage)

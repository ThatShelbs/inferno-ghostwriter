"""Keep Claude primary while honoring opt-in model choices for eligible stages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

from inferno_ghostwriter.config import ImageRoute, SecondaryProvider, Settings, WritingProvider
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
from inferno_ghostwriter.llm.ledger import tap
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


ImageCategory = Literal["pitch", "design", "svg", "judge"]
# What `auto` tries first for each kind of image work, best fit first; Claude is always the last resort.
AUTO_IMAGE: dict[ImageCategory, list[SecondaryProvider]] = {
    "pitch": ["codex", "gemini"],
    "design": ["codex", "gemini"],
    "judge": ["codex"],
    "svg": [],
}


# The model the author chose for one redraw or edit (Ideas, Remix, Edit); None or "auto" = the Settings routing.
_image_model: ContextVar[ImageRoute | None] = ContextVar("image_model", default=None)


@contextmanager
def image_model(choice: ImageRoute | None) -> Iterator[None]:
    """Route this job's image work (pitches, designs, drawings) to ``choice`` instead of the Settings routing. The
    judge keeps its seat, so a chosen model never grades its own work alone; Claude or Gemini turn GPT painting off
    (a redraw of a painting is then drawn instead)."""
    token = _image_model.set(choice)
    try:
        yield
    finally:
        _image_model.reset(token)


def image_category(task: str) -> ImageCategory | None:
    """The kind of image work a task name stands for (see ``config.ImageRouting``), or None for other work."""
    if task in ("opening ideas", "meme ideas", "image improvement plan") or task.endswith(" image ideas"):
        return "pitch"
    if task in ("image pitch judge", "image sheet judge"):
        return "judge"
    if (
        task in ("chart image design", "chart image edit", "diagram design", "opening data art")
        or task.startswith("meme edit (")
        or (task.startswith("opening ") and task.endswith(" build"))
    ):
        return "design"
    if task.endswith((" image design", " image edit")) or (task.startswith("opening ") and task.endswith(" drawing")):
        return "svg"
    return None


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

    async def image_route(self, task: str, images: list[bytes] | None = None) -> list[SecondaryProvider]:
        """The optional models to try, in order, for one piece of image work before Claude."""
        category = image_category(task)
        if category is None:
            return []
        choice: ImageRoute = getattr(self.settings.secondary.images, category)
        chosen = _image_model.get()
        if chosen not in (None, "auto") and category != "judge":
            choice = chosen
        if choice == "claude":
            return []
        if choice != "auto":
            return [choice] if choice in self.secondary and (not images or choice == "codex") else []
        return [
            provider
            for provider in AUTO_IMAGE[category]
            if provider in self.secondary and (not images or provider == "codex") and await self.secondary[provider].signed_in()
        ]

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
        result = await cli.complete(system=system, prompt=prompt, schema=schema, images=images, usage=tap(usage, provider, task))
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
        first = [preferred] if preferred != "claude" else await self.image_route(task, images)
        for provider in first:
            try:
                return await self._secondary_structured(
                    provider, task=task, system=system, prompt=prompt, schema=schema, images=images, usage=usage
                )
            except LLMRefusalError:
                raise
            except LLMError as exc:
                log.info("Secondary %s unavailable during %s: %s", provider, task, exc)
        try:
            return await self.active.structured(
                task=task,
                system=system,
                prompt=prompt,
                schema=schema,
                effort=effort,
                max_tokens=max_tokens,
                usage=tap(usage, "claude", task),
                images=images,
                model=model,
            )
        except LLMLimitError:
            for provider in self._fallback(task, images):
                if provider in first:
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
        model: str | None = None,
    ) -> str:
        # A named Claude model is an experiment's own choice: it never goes to an optional model.
        preferred: Any = "claude" if model else self._preferred(task)
        fallback = [] if model else [provider for provider in self._fallback(task, None) if provider != preferred]

        streamed = False

        async def secondary_text(provider: SecondaryProvider) -> str | None:
            try:
                cli = await self._connected_cli(provider)
                value = await cli.complete(system=system, prompt=prompt, usage=tap(usage, provider, task))
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
                usage=tap(usage, "claude", task),
                model=model,
            )
        except LLMLimitError:
            # The preview is append-only. Do not append another provider's draft to a partial Claude draft.
            if not streamed or on_reset:
                for provider in fallback:
                    if (result := await secondary_text(provider)) is not None:
                        return result
            raise

    async def can_paint(self) -> bool:
        codex = self.secondary.get("codex")
        if _image_model.get() in ("claude", "gemini"):
            return False
        return bool(self.settings.secondary.images.raster and codex is not None and await codex.signed_in())

    async def online(self) -> list[SecondaryProvider]:
        """The optional models signed in now (the choices an image dialog may offer besides Claude)."""
        return [provider for provider, cli in self.secondary.items() if await cli.signed_in()]

    async def paint(self, prompt: str, *, images: list[bytes] | None = None, usage: UsageSink | None = None) -> bytes:
        """A picture from GPT image generation (see ``SecondaryCLI.paint``); raises LLMError when it is unavailable."""
        if not await self.can_paint():
            raise LLMError("GPT image generation is off or not signed in.")
        cli = await self._connected_cli("codex")
        return await cli.paint(prompt, images=images, usage=tap(usage, "codex", "raster image"))

    async def research(
        self,
        *,
        system: list[SystemBlock],
        prompt: str,
        effort: str,
        max_searches: int = 8,
        usage: UsageSink | None = None,
    ) -> ResearchResult:
        return await self.active.research(
            system=system, prompt=prompt, effort=effort, max_searches=max_searches, usage=tap(usage, "claude", "web research")
        )


async def lead_provider(llm: LLM, task: str, images: list[bytes] | None = None) -> str:
    """Who answers ``task`` first through ``llm``: an optional model's id when image routing sends it there, else
    "claude" (any other LLM, such as the demo's, counts as Claude)."""
    if isinstance(llm, RoutingLLM):
        route = await llm.image_route(task, images)
        if route:
            return route[0]
    return "claude"


def chosen_image_model() -> ImageRoute | None:
    """The model the author picked for this job (``image_model``), or None for the Settings routing."""
    return _image_model.get()


async def can_paint(llm: LLM) -> bool:
    """Whether ``llm`` can add a painted (raster) candidate now: GPT image generation is on and signed in."""
    check = getattr(llm, "can_paint", None)
    return bool(check and await check())

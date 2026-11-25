from __future__ import annotations

import asyncio
import io
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from PIL import Image

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.llm.base import T, UsageSink
from inferno_ghostwriter.llm.router import lead_provider
from inferno_ghostwriter.llm.secondary import MODEL_IDS

log = logging.getLogger(__name__)

# Where an image sits in a post's Markdown: ``{{image:slot_id}}`` on its own line.
PLACEHOLDER_RE = re.compile(r"\{\{image:([A-Za-z0-9_\-]+)\}\}")


class ImageProviderError(RuntimeError):
    """An image could not be designed or rendered."""


async def guest_pitches(
    llm: LLM, settings: Settings, *, task: str, system: list[SystemBlock], prompt: str, schema: type[T], usage: UsageSink | None
) -> list[T]:
    async def ask(model: str) -> T | None:
        try:
            return await llm.structured(task=task, system=system, prompt=prompt, schema=schema, effort="medium", model=model, usage=usage)
        except LLMError as exc:
            log.info("Guest pitches from %s skipped: %s", model, exc)
            return None

    lead = await lead_provider(llm, task)  # the model already pitching through image routing does not pitch twice
    return [
        ideas
        for ideas in await asyncio.gather(*(ask(MODEL_IDS[p]) for p in dict.fromkeys(settings.secondary.ideation) if p != lead))
        if ideas is not None
    ]


def to_png(data: bytes) -> tuple[bytes, int, int]:
    """Normalize any image bytes to PNG and return (png, width, height)."""
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        width, height = img.size
        if img.format == "PNG":
            return data, width, height
        out = io.BytesIO()
        img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(out, format="PNG")
        return out.getvalue(), width, height


def retry_note(problems: str) -> str:
    """What a second attempt is told about the first (one problem per line)."""
    lines = "\n".join(f"- {line}" for line in problems.splitlines() if line.strip())
    return f"\n\nYour previous attempt had these problems; fix every one:\n{lines}\n"


async def draw_with_retry[D, R](ask: Callable[[str], Awaitable[D]], draw: Callable[[D, bool], R], *, tries: int = 2) -> tuple[D, R]:
    """Ask Claude for a design and draw it. A design that cannot be drawn is asked for again with the problems quoted back.

    ``ask(note)`` returns a design (``note`` is empty on the first try); ``draw(design, last)`` renders it or raises
    :class:`ImageProviderError` naming the problems, one per line. The last failure is raised.
    """
    note = ""
    for attempt in range(tries):
        design = await ask(note)
        try:
            return design, draw(design, attempt == tries - 1)
        except ImageProviderError as exc:
            if attempt == tries - 1:
                raise
            note = retry_note(str(exc))
    raise ImageProviderError("No attempts were made.")  # unreachable: tries >= 1


def thumbnail_png(png: bytes, width: int = 800) -> bytes:
    """A smaller copy for a reviewer: cheaper to send, and closer to how a feed shows it."""
    with Image.open(io.BytesIO(png)) as source:
        img = source.convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


@dataclass
class Drawn:
    """One drawn image: what a room hands back to the image service.

    ``finalists`` are the best candidates of a fresh room run (this one included), each a ``Drawn`` with its own
    ``spec``; the author can swap between them with no model call. ``label``/``score``/``reads_as`` describe a finalist.
    """

    png: bytes
    width: int
    height: int
    provider: str
    spec: str
    alt: str
    caption: str
    label: str = ""
    score: float | None = None
    reads_as: str = ""
    finalists: list[Drawn] = field(default_factory=list)

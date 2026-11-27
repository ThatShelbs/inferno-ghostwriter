"""Native images: GPT's own image generation (through the author's Codex sign-in) in place of Claude's SVG.

Some slots (``use_native``: a share of the eligible ones per kind, see ``share_for``) are made by GPT from a prompt
instead of being drawn by code from Claude's design; a candidate is one or the other, never both. Painted candidates
go through the same judge sheet as drawn ones. Code writes the prompt from the writer-room pitch (palette, house
cast) and fits the result to the slot. Illustrations, icons, visual metaphors and data art have no words in the
picture (captions and credits stay on the image page); a meme is painted whole, its words quoted exactly
(``MEME_RULES``), and the judge checks the spelling. A generation that fails falls back to code drawing the same
pitch. Nothing here runs unless the author has GPT signed in and the feature on
(``Settings.secondary.images.raster``).

A painting has no spec to edit, so an edit or a redraw paints again from the stored prompt, showing GPT the
current picture when the author asked for a change.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

from PIL import Image

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images.palettes import Scheme
from inferno_ghostwriter.llm import LLM, LLMError
from inferno_ghostwriter.llm.base import UsageSink
from inferno_ghostwriter.llm.router import can_paint, chosen_image_model

PROVIDER = "gpt-image"
TOOL_LABEL = "GPT image generation (ChatGPT)"

RULES = (
    "Style: a polished flat editorial illustration for a technical blog, clean shapes, soft light, generous empty "
    "space, the main subject centred so a square crop still works.\n"
    "Never put any words, letters, numbers, labels, logos or watermarks in the picture.\n"
    "No real people, celebrities, brands or other people's characters. When a character helps, use a friendly, round, "
    "white cartoon ghost (never scary) or simple, faceless people."
)


MEME_RULES = (
    "Paint the whole meme as one finished image, panels and lettering included.\n"
    "Letter every quoted text exactly as written, in bold, clean, highly legible meme lettering, each in its place; "
    "spell every word exactly and add no other words, letters, logos or watermarks.\n"
    "Recreate the famous format's composition so it is recognized at a glance, but never draw the original meme's "
    "real people, celebrities or other people's characters: the cast is a friendly, round, white cartoon ghost "
    "(never scary), other ghosts, or simple stylized people with no real likeness."
)

ART_RULES = (
    "Style: abstract generative data art, as if drawn by code from a dataset: flowing structure, rhythm, density "
    "and colour, crisp and high-resolution, the main mass centred so a square crop still works.\n"
    "Purely abstract: no literal objects, people, characters, animals, icons, symbols, charts with axes, or "
    "scenery; the subject is only a hint in the structure, rhythm and colour.\n"
    "Never put any words, letters, numbers, labels, logos or watermarks in the picture."
)

PaintKind = Literal["illustration", "meme", "data_art"]

# Each redraw rolls again: the round is the number of earlier versions of this image (set by the image service).
_round: ContextVar[int] = ContextVar("paint_round", default=0)


@contextmanager
def paint_round(n: int) -> Iterator[None]:
    """Make ``use_native`` roll for the ``n``-th version of an image (0 = its first), so a redraw can flip a slot."""
    token = _round.set(max(0, n))
    try:
        yield
    finally:
        _round.reset(token)


def share_for(settings: Settings, kind: PaintKind) -> float:
    """The share of eligible ``kind`` slots that GPT paints."""
    images = settings.secondary.images
    return {"meme": images.meme_share, "data_art": images.art_share}.get(kind, images.native_share)


def _roll(seed: str) -> float:
    """A stable number in [0, 1) for ``seed``: the same slot always gets the same answer."""
    return int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) / 0x100000000


async def use_native(llm: LLM, settings: Settings, seed: str, kind: PaintKind = "illustration") -> bool:
    """Whether this slot is generated natively by GPT instead of drawn by code. Never both for one candidate.

    False without a signed-in GPT (Claude-only behaves as always). An author's per-image choice of ChatGPT forces
    it; Claude or Gemini (``can_paint`` is then off) force a drawing. Otherwise the kind's share (``share_for``) of
    the eligible slots are native, picked by a stable hash of ``seed`` and the redraw round (``paint_round``).
    """
    if not await can_paint(llm):
        return False
    if chosen_image_model() == "codex":
        return True
    share = share_for(settings, kind)
    attempt = _round.get()
    return share > 0 and _roll(f"{seed}:{attempt}" if attempt else seed) < share


def aspect(width: int, height: int) -> str:
    """How a prompt names the shape of a ``width`` x ``height`` slot."""
    ratio = width / height if height else 1
    if ratio > 1.5:
        return "16:9 landscape"
    if ratio > 1.15:
        return "4:3 landscape"
    if ratio >= 0.87:
        return "1:1 square"
    return "3:4 portrait"


def prompt_for(
    subject: str,
    *,
    scheme: Scheme | None = None,
    palette: tuple[str, ...] = (),
    extra: str = "",
    wide: bool = True,
    shape: str = "",
    rules: str = RULES,
) -> str:
    """The painting prompt for one pitch. ``palette`` (a brand kit's colours) wins over the post's ``scheme``;
    ``shape`` (see ``aspect``) overrides ``wide``; ``rules`` are the house rules for the kind of picture."""
    colours = list(palette) or ([scheme.bg, *scheme.ramp] if scheme is not None else [])
    lines = [
        subject.strip(),
        f"Aspect ratio: {shape or ('16:9 landscape' if wide else '4:3 landscape')}.",
        rules,
    ]
    if colours:
        lines.append(
            f"Use only this colour palette: {', '.join(colours[:7])}"
            + (f", on a {scheme.bg} background." if scheme and not palette else ".")
        )
    if extra.strip():
        lines.append(extra.strip())
    return "\n".join(lines)


def fit(png: bytes, width: int, height: int) -> bytes:
    """Cover-crop and resize a painting to exactly ``width`` x ``height``."""
    with Image.open(io.BytesIO(png)) as source:
        img = source.convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.Resampling.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    out = io.BytesIO()
    img.crop((left, top, left + width, top + height)).save(out, format="PNG", optimize=True)
    return out.getvalue()


async def paint(
    llm: LLM,
    prompt: str,
    *,
    size: tuple[int, int],
    images: list[bytes] | None = None,
    usage: UsageSink | None = None,
) -> bytes | None:
    """One painting at ``size``, or None when painting is unavailable or fails (a painting never fails an image)."""
    if not await can_paint(llm):
        return None
    try:
        png = await llm.paint(prompt, images=images, usage=usage)  # type: ignore[attr-defined]
        return fit(png, *size)
    except (LLMError, OSError, ValueError):
        return None


def spec(prompt: str, **extra: Any) -> str:
    """The stored spec of a painting: its prompt, so a redraw or an edit can paint again."""
    return json.dumps({"raster": True, "prompt": prompt, **extra})


def load(spec_text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(spec_text) if spec_text else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) and data.get("raster") else None

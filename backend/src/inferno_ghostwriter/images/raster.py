"""Painted candidates: GPT's own image generation (through the author's Codex sign-in) as a rival to Claude's SVG.

A painted picture joins the same judge sheet as the drawn ones, so the judge decides per slot whether a vector
drawing or a painting tells the story better. Code writes the painting prompt from the pitch (palette, house cast,
no words in the picture: captions and credits stay on the image page) and fits the result to the slot. Nothing
here runs unless the author has GPT signed in and painting on (``Settings.secondary.images.raster``).

A painting has no spec to edit, so an edit or a redraw paints again from the stored prompt, showing GPT the
current picture when the author asked for a change.
"""

from __future__ import annotations

import io
import json
from typing import Any

from PIL import Image

from inferno_ghostwriter.images.palettes import Scheme
from inferno_ghostwriter.llm import LLM, LLMError
from inferno_ghostwriter.llm.base import UsageSink
from inferno_ghostwriter.llm.router import can_paint

PROVIDER = "gpt-image"
TOOL_LABEL = "GPT image generation (ChatGPT)"

RULES = (
    "Style: a polished flat editorial illustration for a technical blog, clean shapes, soft light, generous empty "
    "space, the main subject centred so a square crop still works.\n"
    "Never put any words, letters, numbers, labels, logos or watermarks in the picture.\n"
    "No real people, celebrities, brands or other people's characters. When a character helps, use a friendly, round, "
    "white cartoon ghost (never scary) or simple, faceless people."
)


def prompt_for(subject: str, *, scheme: Scheme | None = None, palette: tuple[str, ...] = (), extra: str = "", wide: bool = True) -> str:
    """The painting prompt for one pitch. ``palette`` (a brand kit's colours) wins over the post's ``scheme``."""
    colours = list(palette) or ([scheme.bg, *scheme.ramp] if scheme is not None else [])
    lines = [
        subject.strip(),
        f"Aspect ratio: {'16:9 landscape' if wide else '4:3 landscape'}.",
        RULES,
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

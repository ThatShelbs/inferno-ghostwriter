"""Hands-on data viz: the picture is what the code block right above it draws.

The writer puts a complete example in the post and ``{{image:ID}}`` directly after it. This builder finds that block,
runs it (``sandbox.py``; only when the author allowed it) and keeps the chart it really makes, so the image and the code
beside it always match. If the code fails it gets one repair round: Claude returns a corrected script and **the post's
block is replaced with it**, so the text never shows code that does not make the picture.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PIL import Image

from inferno_ghostwriter.codecheck import imports
from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images.base import Drawn, ImageProviderError
from inferno_ghostwriter.images.codeblocks import CodeBlock, code_before, replace_code
from inferno_ghostwriter.images.specs import HandsOnFix
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.llm.base import UsageSink
from inferno_ghostwriter.prompts import render
from inferno_ghostwriter.sandbox import Sandbox

log = logging.getLogger(__name__)

PROVIDER = "hands-on-code"
MONTAGE_PROVIDER = "montage"
TOOL_LABEL = "code run on this computer"
MAX_WIDTH = 2000
# Library names in the order the credit and the card name the one a script is about.
LIBRARIES = ("matplotlib", "seaborn", "plotly", "altair", "bokeh", "plotnine", "pandas")
LABELS = {
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "plotly": "Plotly",
    "altair": "Altair",
    "bokeh": "Bokeh",
    "plotnine": "plotnine",
    "pandas": "pandas",
}
SYSTEM = [SystemBlock("You write short, correct, runnable Python for readers learning data visualization. You change only what is needed.")]


@dataclass
class HandsOnResult:
    drawn: Drawn
    code: str
    # The post with the block's code replaced when it had to change; unchanged otherwise.
    markdown: str
    changed: bool = False
    note: str = ""


def code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode()).hexdigest()[:16]


def library_of(code: str) -> str:
    found = imports(code)
    return next((name for name in LIBRARIES if name in found), "")


def load_spec(spec: str | None) -> dict[str, Any]:
    try:
        data = json.loads(spec or "")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def is_stale(spec: str | None, markdown: str, slot_id: str) -> bool:
    """True when the block above the image is no longer the code the picture was made from."""
    saved = load_spec(spec).get("code_hash")
    block = code_before(markdown, slot_id)
    return bool(saved) and block is not None and code_hash(block.code) != saved


def caption_for(library: str, lines: int, chars: int) -> str:
    return f"What the code above draws ({lines} lines of {LABELS.get(library, 'Python')}, {chars:,} characters)"


def png_size(png: bytes) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(png)) as opened:
        opened.load()
        width, height = opened.size
        if width <= MAX_WIDTH:
            return png, width, height
        small = opened.convert("RGB").resize((MAX_WIDTH, round(height * MAX_WIDTH / width)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    small.save(out, format="PNG")
    return out.getvalue(), small.width, small.height


class HandsOn:
    """Builds the picture for a ``hands_on_viz`` slot; ``sandbox`` is read each call (the author may switch it on later)."""

    def __init__(self, llm: LLM, settings: Settings, sandbox: Callable[[], Sandbox | None]) -> None:
        self.llm = llm
        self.settings = settings
        self._sandbox = sandbox

    async def make(
        self, *, slot_id: str, markdown: str, purpose: str, instruction: str = "", usage: UsageSink | None = None
    ) -> HandsOnResult:
        """Run the block above ``slot_id`` (after changing it as asked) and return the chart, with the post if its code changed."""
        block = code_before(markdown, slot_id)
        if block is None:
            raise ImageProviderError(
                "No code block sits right above this image. Put the image directly after the code that draws it, or Replace it."
            )
        sandbox = self._sandbox()
        if sandbox is None:
            raise ImageProviderError("Running example code is off. Turn on “Run example code” in Settings to draw this chart.")
        code, changed, note = block.code, False, ""
        if instruction.strip():
            code, note = await self._fix(block, purpose, instruction=instruction, error="", usage=usage)
            changed = code.strip() != block.code.strip()
        result = await sandbox.run(code)
        if not (result.ok and result.png):
            code, note = await self._fix(block, purpose, instruction="", error=result.error, usage=usage, current=code)
            changed = code.strip() != block.code.strip()
            result = await sandbox.run(code)
            if not (result.ok and result.png):
                raise ImageProviderError(
                    "The example code did not draw a chart: " + (result.error.strip().splitlines() or ["it did not finish"])[-1][:300]
                )
        png, width, height = png_size(result.png)
        new_markdown = replace_code(markdown, block, code) if changed else markdown
        library = library_of(code)
        lines, chars = len(code.strip("\n").splitlines()), len(code.strip("\n"))
        spec = json.dumps(
            {"code_hash": code_hash(code), "library": library, "lines": lines, "chars": chars, "versions": result.versions},
            separators=(",", ":"),
        )
        drawn = Drawn(
            png, width, height, PROVIDER, spec,
            alt=purpose or "The chart the code above draws",
            caption=caption_for(library, lines, chars),
        )  # fmt: skip
        return HandsOnResult(drawn, code, new_markdown, changed, note)

    async def _fix(
        self, block: CodeBlock, purpose: str, *, instruction: str, error: str, usage: UsageSink | None, current: str = ""
    ) -> tuple[str, str]:
        """Claude's corrected script for a failure, or for the author's change request."""
        prompt = render(
            "handson_fix",
            code=(current or block.code).strip("\n"),
            purpose=purpose or "a chart that makes the point of this section",
            error=error.strip()[-1800:] or "(it ran; the author wants a change)",
            instruction=instruction.strip() or "Fix the error. Keep everything else the same.",
        )
        try:
            fix = await self.llm.structured(
                task="hands-on code fix",
                system=SYSTEM,
                prompt=prompt,
                schema=HandsOnFix,
                effort=self.settings.effort_images,
                max_tokens=16000,
                usage=usage,
            )
        except LLMError as exc:
            raise ImageProviderError(f"The example code did not run and Claude could not fix it: {exc}") from exc
        code = fix.code.strip("\n")
        if code.startswith("```"):
            code = "\n".join(line for line in code.splitlines() if not line.strip().startswith("```"))
        if not code.strip():
            raise ImageProviderError("Claude returned no code to fix this chart.")
        return code, fix.what_changed.strip()

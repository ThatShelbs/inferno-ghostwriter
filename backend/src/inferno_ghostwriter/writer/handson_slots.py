"""Hands-on data viz in the writer: what the planner is told, and the backstop that makes the dial true.

A ``hands_on_viz`` image is the chart a code example in the post draws (see ``images/handson.py``), so its placeholder
must sit directly after that code block. The planner and the writer are asked for it; this module then repairs what they
leave out: a slot with no code above it becomes an ordinary chart, and (in "lots" mode) a plotting example that has no
picture gets one.
"""

from __future__ import annotations

import re

from inferno_ghostwriter.codecheck import imports
from inferno_ghostwriter.images.base import PLACEHOLDER_RE
from inferno_ghostwriter.images.codeblocks import CodeBlock, code_before, code_blocks
from inferno_ghostwriter.writer.examples import _section_index
from inferno_ghostwriter.writer.schemas import ImageSlot

KIND = "hands_on_viz"
PLOT_LIBRARIES = frozenset({"matplotlib", "seaborn", "plotly", "altair", "bokeh", "plotnine"})
PYTHON = {"python", "py", "python3", ""}
MAX_EXTRA = 8
MAX_IMAGES = 22
MAX_FEW = 2

EXAMPLE_RULES = (
    "For each `hands_on_viz` slot the section shows ONE complete, runnable Python example that loads a real public dataset "
    "(for example from `vega_datasets` or a library's own sample data, never an invented file or URL), draws one chart and ends "
    "with the call that shows it (`plt.show()`, `fig.show()`, `chart.show()`, `show(p)`). The example is a fenced ```python block, "
    "and the slot's `{{image:ID}}` goes on its own line DIRECTLY after that block (no text between them): the picture is made by "
    "running that exact code, so it always matches. Keep each example short enough to read."
)

GUIDES = {
    "lots": (
        "This is a hands-on, do-it-alongside post, so hands-on data viz images are its main images. Make most of the middle image "
        "slots (at least two of every three) kind `hands_on_viz`, one for each code example that draws a chart. " + EXAMPLE_RULES + " "
        "Use other kinds only for what code cannot draw (a concept diagram, a screenshot of a tool)."
    ),
    "few": (
        f"A hands-on data viz image (kind `hands_on_viz`) is an option here, used sparingly: at most {MAX_FEW} slots, and only where "
        "a code example the post already shows draws a chart the reader should compare with the text. " + EXAMPLE_RULES
    ),
    "none": "Do not use the `hands_on_viz` kind.",
}


def guide(level: str) -> str:
    return GUIDES.get(level, GUIDES["none"])


def draws_chart(block: CodeBlock) -> bool:
    """A Python example that plots something."""
    if block.language not in PYTHON:
        return False
    found = imports(block.code)
    return bool(found & PLOT_LIBRARIES) or (bool(found) and ".plot(" in block.code)


def _next_number(slots: list[ImageSlot], markdown: str) -> int:
    used = {int(m.group(1)) for s in slots if (m := re.fullmatch(r"img(\d+)", s.slot_id))}
    used |= {int(n) for n in re.findall(r"\{\{image:img(\d+)\}\}", markdown)}
    return max(used | {1}) + 1


_LIBRARY_RE = re.compile(r"\b(?:" + "|".join(sorted(PLOT_LIBRARIES)) + r")\b", re.IGNORECASE)


def _neutral(text: str) -> str:
    """Drop plotting-library names from a brief: a plain chart is drawn as Vega-Lite whatever the brief asked for."""
    return _LIBRARY_RE.sub("a chart library", text)


def settle_slots(markdown: str, slots: list[ImageSlot], level: str) -> tuple[str, list[ImageSlot]]:
    """Make the slots and the post agree: ``hands_on_viz`` only where a code example sits right above the placeholder."""
    # 1. A hands-on slot with no code above it (or when the dial says none) is still a chart: the image just is not code-made.
    settled: list[ImageSlot] = []
    for slot in slots:
        if slot.kind == KIND and (level == "none" or code_before(markdown, slot.slot_id) is None):
            slot = slot.model_copy(update={"kind": "chart", "brief": _neutral(slot.brief), "purpose": _neutral(slot.purpose)})
        settled.append(slot)
    slots = settled
    if level != "lots":
        return markdown, slots

    # 2. Plotting examples with no picture after them get one (bottom-up so line numbers stay valid).
    lines = markdown.split("\n")
    pictured = {b.end for b in code_blocks(markdown) if _followed_by_image(lines, b)}
    room = max(0, min(MAX_EXTRA, MAX_IMAGES - len(slots)))
    number = _next_number(slots, markdown)
    todo = [b for b in code_blocks(markdown) if draws_chart(b) and b.end not in pictured][:room]
    added: list[ImageSlot] = []
    inserts: list[tuple[int, str]] = []
    for block in todo:
        slot_id = f"img{number}"
        number += 1
        added.append(
            ImageSlot(
                slot_id=slot_id,
                kind=KIND,
                section_index=_section_index(lines, block.start),
                purpose="The chart this example draws",
                brief="The chart the code above draws.",
            )
        )
        inserts.append((block.end, slot_id))
    for end, slot_id in reversed(inserts):
        lines[end + 1 : end + 1] = ["", f"{{{{image:{slot_id}}}}}"]
    if not added:
        return markdown, slots
    text = "\n".join(lines)
    order = {slot_id: i for i, slot_id in enumerate(PLACEHOLDER_RE.findall(text))}
    middle = sorted((s for s in [*slots, *added] if s.kind not in ("hero", "meme")), key=lambda s: order.get(s.slot_id, len(order)))
    return text, [*[s for s in slots if s.kind == "hero"], *middle, *[s for s in slots if s.kind == "meme"]]


def _followed_by_image(lines: list[str], block: CodeBlock) -> bool:
    after = next((line.strip() for line in lines[block.end + 1 :] if line.strip()), "")
    return bool(PLACEHOLDER_RE.fullmatch(after)) or after.startswith("![")

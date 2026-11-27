"""Every image kind in one table: how it is named, which room makes it, how it may be drawn and checked.

This is the place to read (and change) what differs between kinds. The rooms and the API read their per-kind
rules from here (``body.PAINTABLE``, ``body.KIND_OPTIONS``, ``remix.KIND_DIMENSIONS``, ``api.image_room.KIND_LABELS``
are views of it), and ``ImageOut.kind_label`` sends the label to the app. To add a kind: add it to
``writer.schemas.ImageKind``, add a ``KindSpec`` here, then teach its room to draw it (see ``docs/images.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Room = Literal["opening", "meme", "body", "code"]
# How model-written SVG of this kind is checked before judging (``images/lint.py``): "scheme" removes strays and
# snaps every color to the post's scheme; "structure" removes strays and repairs references but keeps the colors
# (a screen mock needs its own greys); None = not SVG, or drawn by code.
Lint = Literal["scheme", "structure"] | None


@dataclass(frozen=True)
class KindSpec:
    id: str
    label: str
    # One line for the "Ways to draw it" menu.
    use: str
    room: Room
    # Whether GPT may paint it instead of a drawing (with the author's ChatGPT sign-in), and at what size.
    paintable: bool = False
    paint_size: tuple[int, int] = (1600, 900)
    # The width model SVG of this kind is rendered at.
    render_width: int = 1600
    lint: Lint = None
    # What a slot of this kind may be redrawn as (its own kind first). Empty = no other way.
    redraw_as: tuple[str, ...] = ()
    # What a redraw may vary at random: "palette", "cast", "staging", "medium" (see ``images/remix.py``).
    remix: tuple[str, ...] = ("palette",)


KINDS: dict[str, KindSpec] = {
    k.id: k
    for k in (
        KindSpec(
            "hero",
            "Opening image",
            "The post's first picture and thumbnail.",
            "opening",
            remix=("palette", "cast", "staging", "medium"),
        ),
        KindSpec(
            "illustration",
            "Illustration",
            "An illustrated metaphor or scene for the idea.",
            "body",
            paintable=True,
            lint="scheme",
            redraw_as=("illustration", "diagram"),
            remix=("palette", "cast", "staging", "medium"),
        ),
        KindSpec(
            "diagram",
            "Diagram",
            "A clean diagram: flow, layers, rings, matrix, before/after.",
            "body",
            lint="scheme",
            redraw_as=("diagram", "illustration", "chart"),
            remix=("palette", "staging"),
        ),
        KindSpec(
            "chart",
            "Chart",
            "A chart of the numbers (illustrative unless the post has them).",
            "body",
            redraw_as=("chart", "diagram"),
        ),
        KindSpec(
            "screenshot",
            "Screenshot mock",
            "A drawn mock of the screen the text describes.",
            "body",
            lint="structure",
            redraw_as=("screenshot",),
        ),
        KindSpec(
            "icon",
            "Icon",
            "A crisp icon or row of icons.",
            "body",
            paintable=True,
            paint_size=(768, 768),
            render_width=768,
            lint="scheme",
            redraw_as=("icon",),
            remix=("palette", "medium"),
        ),
        KindSpec("meme", "Closing meme", "The joke that lands the ending.", "meme", remix=("palette", "cast")),
        KindSpec(
            "hands_on_viz",
            "Hands-on data viz",
            "The chart the code right above it draws, made by running that code.",
            "code",
            remix=(),
        ),
    )
}

BODY_KINDS = tuple(k for k, spec in KINDS.items() if spec.room == "body")


def get(kind: str) -> KindSpec | None:
    return KINDS.get(kind)


def label(kind: str) -> str:
    spec = KINDS.get(kind)
    return spec.label if spec else kind.replace("_", " ").capitalize()

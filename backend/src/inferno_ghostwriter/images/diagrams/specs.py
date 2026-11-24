"""What Claude fills in for a code-drawn diagram: one typed payload per template, joined in ``DiagramSpec``.

Claude writes the words (labels, short notes, optional values, which item to highlight); code owns layout, type and
color. Labels and notes are fitted to their boxes, so a long one shrinks or wraps instead of overflowing, but the
``description`` limits are what reads best at Medium's column width.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

LABEL = "A short label, 1-4 words (about 28 characters reads best)."
NOTE = "Optional one-line note under the label, at most about 70 characters; empty for none."
HIGHLIGHT = "Index (0-based) of the item to emphasize, or null for none."

Glyph = Literal["bars", "radial", "line", "dots", "donut"]


class Item(BaseModel):
    label: str = Field(description=LABEL)
    note: str = Field(default="", description=NOTE)


class ValueItem(Item):
    value: float = Field(description="The number this item stands for (same unit for every item).")


class _Diagram(BaseModel):
    title: str = Field(default="", description="Optional heading drawn on the image; usually empty (the post's caption says it).")
    alt: str = Field(default="", description="Alt text: what the diagram shows, in one sentence.")


class NestedRings(_Diagram):
    template: Literal["nested_rings"] = "nested_rings"
    items: list[Item] = Field(min_length=2, max_length=6, description="Outermost (broadest) first, innermost (most specific) last.")
    highlight: int | None = Field(default=None, description=HIGHLIGHT)


class RadialBars(_Diagram):
    template: Literal["radial_bars"] = "radial_bars"
    items: list[ValueItem] = Field(min_length=3, max_length=7, description="Largest value first reads best (outer ring).")
    unit: str = Field(default="", description="Unit printed after each value, e.g. '%' or ' ms'; empty for none.")
    center: str = Field(default="", description="A word or two for the center of the rings; empty for none.")
    highlight: int | None = Field(default=None, description="Item called out beside the chart; null calls out the largest.")


class Option(Item):
    glyph: Glyph | None = Field(default=None, description="Mini chart drawn on the card; null picks one.")


class WinnerCard(_Diagram):
    template: Literal["winner_card"] = "winner_card"
    options: list[Option] = Field(min_length=3, max_length=5, description="The alternatives, the winner among them.")
    winner: int = Field(default=0, description="Index (0-based) of the option that wins.")


class Pipeline(_Diagram):
    template: Literal["pipeline"] = "pipeline"
    steps: list[Item] = Field(min_length=3, max_length=6, description="The steps in order, left to right.")
    highlight: int | None = Field(default=None, description=HIGHLIGHT)


class LayerStack(_Diagram):
    template: Literal["layer_stack"] = "layer_stack"
    layers: list[Item] = Field(min_length=3, max_length=6, description="Top layer first, foundation last.")
    highlight: int | None = Field(default=None, description=HIGHLIGHT)


class HubSpoke(_Diagram):
    template: Literal["hub_spoke"] = "hub_spoke"
    hub: str = Field(description="The center: the thing every spoke connects to (1-3 words).")
    spokes: list[Item] = Field(min_length=3, max_length=8, description="The parts around the hub, clockwise from the top.")
    highlight: int | None = Field(default=None, description=HIGHLIGHT)


class Axis(BaseModel):
    name: str = Field(description="What the axis measures, e.g. 'Effort'.")
    low: str = Field(default="Low", description="Label at the low end.")
    high: str = Field(default="High", description="Label at the high end.")


class Point(BaseModel):
    label: str = Field(description=LABEL)
    x: float = Field(ge=0, le=1, description="0 = low end of the x axis, 1 = high end.")
    y: float = Field(ge=0, le=1, description="0 = low end of the y axis, 1 = high end.")


class Matrix2x2(_Diagram):
    template: Literal["matrix_2x2"] = "matrix_2x2"
    x_axis: Axis
    y_axis: Axis
    quadrants: list[Item] = Field(min_length=4, max_length=4, description="Top-left, top-right, bottom-left, bottom-right.")
    points: list[Point] = Field(default_factory=list, max_length=8, description="Optional labeled dots placed on the grid.")
    highlight: int | None = Field(default=None, description="Quadrant index to emphasize, or null.")


class Event(Item):
    when: str = Field(description="The date or stage, short: '2017', 'Q3', 'Week 2'.")


class Timeline(_Diagram):
    template: Literal["timeline"] = "timeline"
    events: list[Event] = Field(min_length=3, max_length=7, description="In time order, earliest first.")
    highlight: int | None = Field(default=None, description=HIGHLIGHT)


class Venn(_Diagram):
    template: Literal["venn"] = "venn"
    sets: list[Item] = Field(min_length=2, max_length=3, description="The overlapping sets.")
    overlap: str = Field(description="What sits where all the sets meet (1-3 words).")
    highlight: int | None = Field(default=None, description="Set index to emphasize, or null.")


DiagramSpec = Annotated[
    NestedRings | RadialBars | WinnerCard | Pipeline | LayerStack | HubSpoke | Matrix2x2 | Timeline | Venn,
    Field(discriminator="template"),
]
DIAGRAM_ADAPTER: TypeAdapter[DiagramSpec] = TypeAdapter(DiagramSpec)


class Diagram(BaseModel):
    """A structured-output wrapper: one diagram spec."""

    spec: DiagramSpec


def parse_diagram(data: object) -> DiagramSpec:
    """A diagram spec from a dict (or JSON string), validated against its template's payload."""
    if isinstance(data, str | bytes):
        return DIAGRAM_ADAPTER.validate_json(data)
    return DIAGRAM_ADAPTER.validate_python(data)


__all__ = [
    "DIAGRAM_ADAPTER",
    "Axis",
    "Diagram",
    "DiagramSpec",
    "Event",
    "Glyph",
    "HubSpoke",
    "Item",
    "LayerStack",
    "Matrix2x2",
    "NestedRings",
    "Option",
    "Pipeline",
    "Point",
    "RadialBars",
    "Timeline",
    "ValueItem",
    "Venn",
    "WinnerCard",
    "parse_diagram",
]

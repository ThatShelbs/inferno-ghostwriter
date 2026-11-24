"""Code-drawn diagrams for the body of a post: Claude fills a typed spec, code draws it in the author's clean style.

``render_diagram(spec, scheme, credit)`` returns SVG; ``TEMPLATES`` lists each template with a one-line "use when".
Not wired into ``ImageService`` yet.
"""

from inferno_ghostwriter.images.diagrams.board import Board, Colors, Placed
from inferno_ghostwriter.images.diagrams.specs import (
    DIAGRAM_ADAPTER,
    Axis,
    Diagram,
    DiagramSpec,
    Event,
    HubSpoke,
    Item,
    LayerStack,
    Matrix2x2,
    NestedRings,
    Option,
    Pipeline,
    Point,
    RadialBars,
    Timeline,
    ValueItem,
    Venn,
    WinnerCard,
    parse_diagram,
)
from inferno_ghostwriter.images.diagrams.templates import TEMPLATES, Template, layout_diagram, menu, render_diagram, render_diagram_png

__all__ = [
    "DIAGRAM_ADAPTER",
    "TEMPLATES",
    "Axis",
    "Board",
    "Colors",
    "Diagram",
    "DiagramSpec",
    "Event",
    "HubSpoke",
    "Item",
    "LayerStack",
    "Matrix2x2",
    "NestedRings",
    "Option",
    "Pipeline",
    "Placed",
    "Point",
    "RadialBars",
    "Template",
    "Timeline",
    "ValueItem",
    "Venn",
    "WinnerCard",
    "layout_diagram",
    "menu",
    "parse_diagram",
    "render_diagram",
    "render_diagram_png",
]

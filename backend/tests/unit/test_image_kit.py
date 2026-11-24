"""The image overhaul's building blocks: palettes, the character kit, SVG lint, the judging panel and the author's taste."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel

from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.images.kit import ACCESSORIES, EXPRESSIONS, KINDS, POSES, STYLES, Character, draw
from inferno_ghostwriter.images.kit.rig import REST_L, REST_R
from inferno_ghostwriter.images.lint import lint
from inferno_ghostwriter.images.opening.scene import LAYOUTS, compose_scene
from inferno_ghostwriter.images.opening.specs import SceneSpec
from inferno_ghostwriter.images.palettes import (
    DARK_SURFACES,
    RAMPS,
    SURFACES,
    brand_scheme,
    choose,
    colors_in,
    from_id,
    house_ramp,
    pick,
    scheme,
    snap_svg,
)
from inferno_ghostwriter.images.remix import HOUSE, PALETTE, choose_tweaks
from inferno_ghostwriter.images.render import svg_to_png
from inferno_ghostwriter.llm.base import LLMImagesUnsupportedError

# -- palettes -----------------------------------------------------------------------------------------------------------


def test_schemes_rotate_through_the_house_ramps_and_surfaces() -> None:
    first = choose(())
    second = choose((first.id,))
    third = choose((second.id, first.id))
    assert len({first.ramp_id, second.ramp_id, third.ramp_id}) == 3  # inferno, magma and viridis take turns
    assert (first.surface_id in DARK_SURFACES) != (second.surface_id in DARK_SURFACES)  # light and dark alternate
    assert choose((), ramp="viridis", dark=True).ramp_id == "viridis" and choose((), dark=False).surface_id not in DARK_SURFACES
    assert from_id("magma:white") == scheme("magma", "white") and from_id("nope:white") is None and from_id(None) is None
    for sch in (scheme(r, s) for r in RAMPS for s in SURFACES):
        assert sch.bg in SURFACES.values() and set(sch.accents) <= set(sch.ramp) and len(sch.accents) == 6
        assert "palette on a" in sch.describe()


def test_a_brand_palette_wins_but_a_house_ramp_from_remix_keeps_the_rotation() -> None:
    brand = pick(("#003366", "#00aa88", "#ffcc00"))
    assert brand.ramp_id == "brand" and set(brand.ramp) == {"#003366", "#00aa88", "#ffcc00"}
    assert house_ramp(RAMPS["magma"]) == "magma" and house_ramp(("#003366", "#00aa88", "#ffcc00")) is None
    assert pick(RAMPS["viridis"]).ramp_id == "viridis"
    assert brand_scheme(("#ffffff",)).ramp_id == "inferno"  # too few colors: the house default


def test_snap_moves_every_color_onto_the_scheme() -> None:
    sch = scheme("viridis", "white")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><style>.a{fill:#ff00ff}</style>'
        '<rect fill="red" stroke="rgb(10, 200, 30)" width="5" height="5"/><circle style="fill:#123" r="2"/>'
        '<linearGradient id="g"><stop stop-color="#ABCDEF"/></linearGradient><rect fill="url(#g)" width="1" height="1"/></svg>'
    )
    snapped = snap_svg(svg, sch.allowed)
    assert colors_in(snapped) <= {c.lower() for c in sch.allowed}
    assert 'fill="url(#g)"' in snapped and "red" not in snapped


def test_house_only_remixes_never_leave_inferno_magma_or_viridis() -> None:
    picked = {t.id for _ in range(40) for t in choose_tweaks((PALETTE,), house_only=True)}
    assert picked <= set(HOUSE) and len(picked) >= 2


# -- the character kit --------------------------------------------------------------------------------------------------


def test_every_character_expression_pose_and_look_renders_whole() -> None:
    sch = scheme("inferno", "white")
    svgs = []
    for kind in KINDS:
        for k, expression in enumerate(EXPRESSIONS):
            pose = list(POSES)[k % len(POSES)]
            look = list(STYLES)[k % len(STYLES)]
            accessory = ACCESSORIES[k % len(ACCESSORIES)]
            drawn = draw(
                Character(kind, expression, pose, "left" if k % 2 else "right", accessory, "mug", k % 3), 300, 560, 400, sch=sch, look=look
            )
            svgs.append(drawn.svg)
            x0, y0, x1, y1 = drawn.bbox
            assert x1 > x0 and y1 < y0 + 1000 and drawn.anchors["head_top"][1] < drawn.anchors["mouth"][1] < drawn.anchors["feet"][1]
    # One sheet renders (resvg would reject broken markup), and characters have ink on them.
    sheet = "".join(f'<g transform="translate({(i % 12) * 600 - 0},{(i // 12) * 600})">{s}</g>' for i, s in enumerate(svgs[:24]))
    png, _, _ = svg_to_png(f'<svg xmlns="http://www.w3.org/2000/svg" width="7200" height="1200">{sheet}</svg>', width=1800)
    with Image.open(io.BytesIO(png)) as img:
        assert img.convert("L").getextrema()[0] < 60


def test_limbs_start_inside_the_body_so_nothing_floats() -> None:
    from inferno_ghostwriter.images.kit import paint, rig, style

    sch = scheme()
    for kind, builder in (("ghost", rig._ghost), ("dog", rig._dog), ("cat", rig._cat), ("robot", rig._robot)):
        c = style.coat(kind, sch, style.kit_style(None))
        b = builder(c, paint.Painter(style.kit_style(None), c.line, "t"), rig.POSES["stand"])
        _hx, hy, hr = b.head
        for sx, sy in b.shoulders:
            # A shoulder sits inside the body's outline (within its half-width) and below the head's centre.
            assert abs(sx) < b.width and sy > hy, kind
        assert hr > 60 and b.top < hy - hr + 40, kind
    # Animals stand on their front legs at rest: the paws reach the ground.
    assert REST_R.dy > 0 and REST_L.dy > 0


def test_a_scene_places_kit_characters_props_and_one_linted_object() -> None:
    sch = scheme("magma", "charcoal")
    stray = '<circle cx="5000" cy="10" r="4" fill="#00ff00"/>'
    for layout in LAYOUTS:
        spec = SceneSpec(
            layout=layout,
            backdrop="plain",
            characters=[{"kind": "ghost", "expression": "shocked", "pose": "point", "slot": "left"}] if layout != "object" else [],
            props=[{"name": "chart_screen", "slot": "right"}],
            object_svg='<rect x="50" y="50" width="500" height="400" rx="30" fill="#ff0000"/>' + stray,
            labels=[{"text": "The object", "slot": "object"}],
            alt="a",
            caption="c",
        )
        _png, width, height, problems = compose_scene(spec, sch)
        assert (width, height) == (1600, 900) and problems == [], layout


# -- lint ---------------------------------------------------------------------------------------------------------------


def test_lint_removes_strays_and_reports_dead_references_and_text_outside_the_band() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">'
        '<rect width="1600" height="900" fill="#000004"/>'
        '<circle cx="800" cy="450" r="200" fill="url(#missing)"/>'
        '<rect x="1900" y="20" width="40" height="40" fill="#fff"/>'  # off canvas
        '<circle cx="60" cy="860" r="2" fill="#fff"/>'  # a lone stray mark
        + "".join(f'<circle cx="{300 + i * 9}" cy="300" r="2" fill="#fff"/>' for i in range(6))  # a deliberate cluster
        + '<text x="100" y="40" font-size="40">Too high</text></svg>'
    )
    report = lint(svg, size=(1600, 900), safe_band=(130, 770), allowed_colors=scheme().allowed)
    assert report.removed == 2 and report.svg.count("<circle") == 7
    assert any("missing" in p for p in report.problems) and any("Too high" in p for p in report.problems)
    budget = lint('<svg xmlns="http://www.w3.org/2000/svg">' + '<rect width="1" height="1"/>' * 30 + "</svg>", size=(10, 10), budget=20)
    assert any("shapes" in p for p in budget.problems)


class BlindLLM(FakeLLM):
    """Blind readers see pictures; images may be unsupported (headless Claude Code)."""

    def __init__(self, unsupported: bool = False) -> None:
        super().__init__()
        self.unsupported = unsupported

    async def structured(self, *, task: str, schema: type[BaseModel], **kwargs: Any) -> Any:
        if kwargs.get("images") and self.unsupported:
            raise LLMImagesUnsupportedError()
        return await super().structured(task=task, schema=schema, **kwargs)


FAKE = Path(__file__).parents[1] / "fixtures" / "fake_claude.py"


class Plan(BaseModel):
    title: str


# -- taste ----------------------------------------------------------------------------------------------------------------


def test_snap_leaves_css_id_selectors_alone() -> None:
    sch = scheme("inferno", "white")
    snapped = snap_svg("<svg><style>#add { fill: #00ff00 } #bad{stroke:#0000ff}</style></svg>", sch.allowed)
    assert "#add" in snapped and "#bad" in snapped and "#00ff00" not in snapped

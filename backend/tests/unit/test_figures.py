"""The figure library: every figure renders, ids are unique and parse back, feet sit on the ground, colors apply."""

from __future__ import annotations

import io

import pytest
from lxml import etree
from PIL import Image

from inferno_ghostwriter.images import figures as fg
from inferno_ghostwriter.images.palettes import scheme
from inferno_ghostwriter.images.render import svg_to_png

ALL = [(s, p) for s in fg.STYLES for p in fg.POSES]


def _alone(sym: fg.SvgSymbol, width: int = 240) -> Image.Image:
    """The symbol placed on a transparent canvas exactly its viewBox in size."""
    x, _y, w, h = sym.view_box
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><defs>{sym.svg}</defs>{sym.use(-x, h, h)}</svg>'
    png, _, _ = svg_to_png(svg, width=width, background=None)
    return Image.open(io.BytesIO(png)).convert("RGBA")


@pytest.mark.parametrize(("style", "pose"), ALL)
def test_every_figure_renders_and_stands_on_the_ground(style: str, pose: str) -> None:
    sym = fg.figure(style, pose)
    assert sym.id == f"fig-{style}-{pose}"
    x, y, w, h = sym.view_box
    assert y + h == 0, "the viewBox bottom is the ground"
    assert x == -w / 2, "x = 0 is the centre line"
    img = _alone(sym)
    bbox = img.getchannel("A").point(lambda a: 255 if a > 10 else 0).getbbox()
    assert bbox is not None
    left, top, right, bottom = bbox
    # Something touches the ground line (feet, a floating ghost's shadow, a desk leg) and nothing is cut off at the edges.
    assert bottom >= img.height - 2
    assert top > 0 and left > 0 and right < img.width


@pytest.mark.parametrize("style", list(fg.STYLES))
def test_left_facing_mirrors(style: str) -> None:
    right = fg.figure(style, "pointing")
    left = fg.figure(style, "pointing", facing="left")
    assert left.id.endswith("-left")
    assert left.anchors["hand"] == (-right.anchors["hand"][0], right.anchors["hand"][1])
    assert right.anchors["hand"][0] > 0


def test_ids_are_unique_and_parse_back() -> None:
    ids = [fg.figure(s, p).id for s, p in ALL]
    variants = [
        fg.figure("line", p, expression=e, outfit=o, hair=h, facing=f, tag=t).id
        for p in ("standing", "nope")
        for e in (None, "crying", "smug")
        for o in (None, "plaid", "dress")
        for h in (None, "long")
        for f in ("right", "left")
        for t in (None, "b")
    ]
    assert len(set(ids)) == len(ids)
    assert len(set(variants)) == len(variants)
    for fid in ids + variants:
        assert fg.parse_id(fid).id == fid
    assert set(fg.CATALOG) == set(ids)


def test_parse_id_rejects_junk() -> None:
    for bad in ("fig-line", "fig-cyborg-standing", "fig-line-dance", "fig-bean-standing-plaid", "fig-line-standing-a-b", "rect-1"):
        with pytest.raises(ValueError):
            fg.parse_id(bad)


def test_recolor() -> None:
    red = fg.FigureColors(shirt="#e0383e", skin="#8d5a3b", accent="#123456")
    for style in fg.STYLES:
        svg = fg.figure(style, "flashlight", colors=red).svg
        assert "#e0383e" in svg or style in ("ghost", "robot")
        assert "#123456" in svg
    assert "#8d5a3b" in fg.figure("line", "standing", colors=red).svg
    assert "#abcdef" in fg.figure("ghost", "standing", colors=red.with_(ghost="#abcdef")).svg
    plaid = fg.figure("line", "looking_back", colors=red.with_(plaid="#0a0b0c"), outfit="plaid").svg
    assert "#0a0b0c" in plaid and "url(#fig-line-looking_back-plaid-plaid)" in plaid
    sch = scheme("viridis", "white")
    c = fg.FigureColors.from_scheme(sch, 2)
    assert c.shirt == sch.accent(2)
    assert c.skin in fg.SKIN_TONES


def test_defs_for_parses_and_renders_claude_svg() -> None:
    colors = {"fig-line-standing-plaid-messy": fg.FigureColors(shirt="#3f6fb0")}
    claude = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400"><rect width="800" height="400" fill="#fff"/>'
        '<use href="#fig-line-standing-plaid-messy" x="100" y="100" width="290" height="298"/>'
        '<use href="#fig-line-standing-dress-long-left" x="400" y="100" width="290" height="298"/>'
        '<use href="#fig-ghost-laptop" x="0" y="0" width="90" height="80"/>'
        '<use href="#not-a-figure"/></svg>'
    )
    assert fg.ids_in(claude) == ["fig-line-standing-plaid-messy", "fig-line-standing-dress-long-left", "fig-ghost-laptop"]
    defs = fg.defs_for([*fg.ids_in(claude), "fig-ghost-laptop"], colors)
    root = etree.fromstring(defs.replace("<defs>", '<defs xmlns="http://www.w3.org/2000/svg">', 1).encode())
    symbols = root.findall("{http://www.w3.org/2000/svg}symbol")
    assert [s.get("id") for s in symbols] == fg.ids_in(claude)
    assert "#3f6fb0" in defs
    png, w, h = svg_to_png(fg.inject(claude), width=400)
    assert (w, h) == (400, 200) and png


def test_defs_keep_an_id_that_spells_out_the_default_expression() -> None:
    defs = fg.defs_for(["fig-line-nope-disgusted"])
    assert 'id="fig-line-nope-disgusted"' in defs


def test_catalog_text_lists_everything() -> None:
    text = fg.catalog_text()
    for name in [*fg.POSES, *fg.EXPRESSIONS, *fg.OUTFITS, *fg.HAIRS, *fg.STYLES]:
        assert name in text
    assert "lens" in fg.CATALOG["fig-line-flashlight"]

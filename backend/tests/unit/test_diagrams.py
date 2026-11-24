from __future__ import annotations

import copy
import io
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from inferno_ghostwriter.images.diagrams import TEMPLATES, Colors, layout_diagram, menu, parse_diagram, render_diagram, render_diagram_png
from inferno_ghostwriter.images.diagrams.board import MIN_TEXT
from inferno_ghostwriter.images.diagrams.samples import SAMPLES
from inferno_ghostwriter.images.palettes import RAMPS, _lab, colors_in, from_id, mix, scheme

SCHEMES = ["inferno:light_gray", "viridis:white", "magma:near_black"]
LONG = "An unreasonably long label that someone pasted from a slide deck about governance and lineage"


def _long(template_id: str) -> dict[str, Any]:
    """The sample with every label (and the first note) made far too long."""
    data = copy.deepcopy(SAMPLES[template_id])
    for key in ("items", "options", "steps", "layers", "spokes", "quadrants", "events", "sets", "points"):
        for i, item in enumerate(data.get(key, [])):
            item["label"] = LONG
            if i == 0 and "note" in item:
                item["note"] = LONG + " and then some more words " * 3
    for key in ("hub", "overlap", "center"):
        if key in data:
            data[key] = LONG
    return data


def test_the_catalog_has_every_template_with_a_sample_and_a_use_when() -> None:
    assert set(TEMPLATES) == {
        "nested_rings",
        "radial_bars",
        "winner_card",
        "pipeline",
        "layer_stack",
        "hub_spoke",
        "matrix_2x2",
        "timeline",
        "venn",
    }
    assert set(SAMPLES) == set(TEMPLATES)
    for t in TEMPLATES.values():
        assert t.width == 1400 and 500 <= t.height <= 1400 and t.use_when
        assert f"`{t.id}`" in menu()


@pytest.mark.parametrize("scheme_id", SCHEMES)
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_every_template_renders_at_its_size(template_id: str, scheme_id: str) -> None:
    sch = from_id(scheme_id)
    assert sch is not None
    png, width, height = render_diagram_png(SAMPLES[template_id], sch, "@author")
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (width, height) == TEMPLATES[template_id].size
    svg = render_diagram(SAMPLES[template_id], sch, "@author")
    assert svg.startswith("<svg") and "@author" in svg


@pytest.mark.parametrize("long", [False, True])
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_text_stays_inside_its_box_and_on_the_canvas(template_id: str, long: bool) -> None:
    board = layout_diagram(_long(template_id) if long else SAMPLES[template_id], scheme("inferno", "light_gray"), "@author")
    board.svg()
    assert board.placed
    for p in board.placed:
        x, y, w, h = p.box
        assert p.fitted.width <= w + 1 and p.fitted.height <= h + 1, (template_id, p.text, p.box, p.fitted.width, p.fitted.height)
        assert p.fitted.size >= MIN_TEXT
        cx, cy = x + w / 2, y + h / 2
        if p.rotate:  # a quarter turn swaps the box's sides about its center
            w, h = h, w
        assert cx - w / 2 >= -1 and cx + w / 2 <= board.width + 1, (template_id, p.text, p.box)
        assert cy - h / 2 >= -1 and cy + h / 2 <= board.height + 1, (template_id, p.text, p.box)


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_long_labels_wrap_or_shrink_instead_of_overflowing(template_id: str) -> None:
    board = layout_diagram(_long(template_id), scheme("viridis", "white"))
    board.svg()
    long_ones = [p for p in board.placed if LONG.split()[0] in p.text]
    assert long_ones
    for p in long_ones:
        assert len(p.fitted.lines) > 1 or p.fitted.size < p.style.max_size or p.fitted.lines[-1].endswith("…")


@pytest.mark.parametrize("scheme_id", SCHEMES)
@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_only_scheme_colors_are_used(template_id: str, scheme_id: str) -> None:
    sch = from_id(scheme_id)
    assert sch is not None
    card = Colors(sch).card  # the surface lifted toward white: cards and tints sit on it
    anchors = [*sch.ramp, sch.bg, sch.ink, card, "#ffffff", "#000000", "#14101f"]
    steps = [i / 20 for i in range(21)]
    family = {mix(a, b, t) for a in anchors for b in ("#ffffff", "#000000", sch.bg, sch.ink, card, "#14101f") for t in steps}
    family |= {sch.at(i / 40) for i in range(41)}
    family |= {mix(sch.at(i / 40), b, t) for i in range(41) for b in ("#ffffff", "#000000", sch.bg, sch.ink, card) for t in steps}
    labs = [_lab(f) for f in family]
    for color in colors_in(render_diagram(SAMPLES[template_id], sch)):
        lab = _lab(color)
        nearest = min(sum((p - q) ** 2 for p, q in zip(lab, f, strict=True)) for f in labs) ** 0.5
        assert nearest < 3, (template_id, scheme_id, color)


def test_other_ramps_change_the_colors() -> None:
    inferno = colors_in(render_diagram(SAMPLES["pipeline"], scheme("inferno", "white")))
    viridis = colors_in(render_diagram(SAMPLES["pipeline"], scheme("viridis", "white")))
    assert set(RAMPS["viridis"]) & viridis and not set(RAMPS["viridis"][3:8]) & inferno


def test_specs_validate_and_bad_ones_are_refused() -> None:
    spec = parse_diagram(SAMPLES["venn"])
    assert spec.template == "venn"
    assert parse_diagram('{"template": "pipeline", "steps": [{"label": "a"}, {"label": "b"}, {"label": "c"}]}').template == "pipeline"
    with pytest.raises(ValidationError):
        parse_diagram({"template": "pipeline", "steps": [{"label": "only one"}]})
    with pytest.raises(ValidationError):
        parse_diagram({"template": "spiral", "items": []})


def test_an_out_of_range_highlight_is_ignored_and_a_title_moves_the_body_down() -> None:
    data = {**SAMPLES["timeline"], "highlight": 42, "title": "Ten years of deep learning"}
    board = layout_diagram(data, scheme())
    board.svg()
    title = next(p for p in board.placed if p.text == "Ten years of deep learning")
    others = [p for p in board.placed if p is not title and p.text != "@author"]
    assert all(p.box[1] > title.box[1] + title.box[3] for p in others)

"""The image building blocks: palettes, remix palettes and SVG lint."""

from __future__ import annotations

from inferno_ghostwriter.images.lint import lint
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


# -- lint ---------------------------------------------------------------------------------------------------------------


def test_lint_removes_strays_repairs_dead_references_and_reports_text_outside_the_band() -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">'
        '<rect width="1600" height="900" fill="#000004"/>'
        '<circle cx="800" cy="450" r="200" fill="url(#missing)"/>'
        '<rect x="1900" y="20" width="40" height="40" fill="#fff"/>'  # off canvas
        '<circle cx="60" cy="860" r="2" fill="#fff"/>'  # a lone stray mark
        + "".join(f'<circle cx="{300 + i * 9}" cy="300" r="2" fill="#fff"/>' for i in range(6))  # a deliberate cluster
        + '<use href="#nothing"/><g filter="url(#gone)"><rect width="10" height="10" fill="#fff"/></g>'
        + '<text x="100" y="40" font-size="40">Too high</text></svg>'
    )
    report = lint(svg, size=(1600, 900), safe_band=(130, 770), allowed_colors=scheme().allowed)
    # Repaired in code, no second design call: the missing paint becomes a scheme colour, the missing filter and
    # the <use> of nothing are dropped. Two strays (off canvas, lone mark) are removed as before.
    assert report.removed == 5 and report.svg.count("<circle") == 7
    assert "url(#" not in report.svg and "#nothing" not in report.svg
    assert report.problems == [p for p in report.problems if "Too high" in p] and report.problems
    budget = lint('<svg xmlns="http://www.w3.org/2000/svg">' + '<rect width="1" height="1"/>' * 30 + "</svg>", size=(10, 10), budget=20)
    assert any("shapes" in p for p in budget.problems)


# -- snapping ----------------------------------------------------------------------------------------------------------------


def test_snap_leaves_css_id_selectors_alone() -> None:
    sch = scheme("inferno", "white")
    snapped = snap_svg("<svg><style>#add { fill: #00ff00 } #bad{stroke:#0000ff}</style></svg>", sch.allowed)
    assert "#add" in snapped and "#bad" in snapped and "#00ff00" not in snapped


# -- fewer, better builds ------------------------------------------------------------------------------------------------


def test_builds_differ_in_style_and_only_weak_winners_are_refined(settings) -> None:  # type: ignore[no-untyped-def]
    from inferno_ghostwriter.images.judge import to_refine
    from inferno_ghostwriter.images.opening.room import pick_builds

    concepts = [{"style": s} for s in ("editorial", "editorial", "meme", "data_art", "meme", "receipt")]
    assert pick_builds(concepts, [0, 1, 2, 3, 4, 5], 3) == [0, 3, 5]  # a meme is built only when ranked first
    assert pick_builds(concepts, [2, 4, 0, 1], 4) == [2, 0, 1]  # never two memes
    settings.image_refine, settings.image_refine_below = 1, 8.0
    assert to_refine([6.0, 9.0], [1, 0], settings) == []  # the winner already works
    assert to_refine([6.0, 7.5], [1, 0], settings) == [1]
    settings.image_refine = 3
    assert to_refine([6.0, 7.5, 9.5], [2, 1, 0], settings) == [1, 0]


def test_condense_keeps_every_section_in_the_posts_own_words() -> None:
    from inferno_ghostwriter.images.memes.generate import clip_post
    from inferno_ghostwriter.images.story import anchored, condense

    sections = [
        f"## Part {n}\n\nFirst point of part {n} is clear. Then a detail follows here. And another one. And a last one.\n\n"
        f"```python\nprint({n})\nprint({n})\n```"
        for n in range(1, 40)
    ]
    post = "\n\n".join(sections) + "\n\nThe ending pays off the joke about pie charts."
    short = condense(post, 4000)
    assert len(short) <= 4000 and "## Part 39" in short and "[code block (python): 2 lines]" in short
    assert anchored("First point of part 39 is clear.", post)
    clipped = clip_post(post, 4500, tail=500)
    assert clipped.endswith("The ending pays off the joke about pie charts.") and "## Part 1" in clipped

"""The data-art engines: they render, are deterministic per seed, vary across seeds and stay in the scheme."""

from __future__ import annotations

import io
import re

import pytest
from PIL import Image

from inferno_ghostwriter.images import palettes
from inferno_ghostwriter.images.art import ENGINES, ArtPalette, DataArtSpec, art_scheme, band, render_art
from inferno_ghostwriter.images.render import svg_to_png

SCHEMES = [palettes.scheme("inferno", "near_black"), palettes.scheme("viridis", "white")]
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


@pytest.mark.parametrize("engine", list(ENGINES))
def test_engine_renders_to_png(engine: str) -> None:
    for scheme in SCHEMES:
        svg = render_art(DataArtSpec(engine=engine, seed=3), scheme)  # type: ignore[arg-type]
        png, width, height = svg_to_png(svg, width=400)
        assert (width, height) == (400, 225)
        img = Image.open(io.BytesIO(png)).convert("L")
        lo, hi = img.getextrema()
        assert hi - lo > 60, "the piece should have real contrast, not a flat fill"


@pytest.mark.parametrize("engine", list(ENGINES))
def test_engine_is_deterministic_and_varies_by_seed(engine: str) -> None:
    scheme = SCHEMES[0]
    a = render_art(DataArtSpec(engine=engine, seed=11), scheme)  # type: ignore[arg-type]
    b = render_art(DataArtSpec(engine=engine, seed=11), scheme)  # type: ignore[arg-type]
    c = render_art(DataArtSpec(engine=engine, seed=12), scheme)  # type: ignore[arg-type]
    assert a == b
    assert a != c


@pytest.mark.parametrize("engine", list(ENGINES))
def test_engine_uses_only_scheme_colors(engine: str) -> None:
    for scheme in [*SCHEMES, palettes.scheme("magma", "paper")]:
        svg = render_art(DataArtSpec(engine=engine, seed=5, density=1.0), scheme)  # type: ignore[arg-type]
        allowed = ArtPalette(scheme).colors()
        stray = {c.lower() for c in HEX.findall(svg)} - allowed
        assert not stray, f"{engine} used colors outside the scheme: {sorted(stray)[:5]}"


@pytest.mark.parametrize("engine", list(ENGINES))
def test_engine_stays_within_size(engine: str) -> None:
    svg = render_art(DataArtSpec(engine=engine, seed=9, density=1.0), SCHEMES[0])  # type: ignore[arg-type]
    assert 'viewBox="0 0 1600 900"' in svg
    assert len(svg) < 1_500_000


def test_structure_hints_change_the_piece() -> None:
    scheme = SCHEMES[0]
    three = render_art(DataArtSpec(engine="fan_streams", seed=1, inputs=3), scheme)
    five = render_art(DataArtSpec(engine="fan_streams", seed=1, inputs=5), scheme)
    assert three != five
    assert render_art(DataArtSpec(engine="rings", seed=1, outputs=1), scheme) != render_art(
        DataArtSpec(engine="rings", seed=1, outputs=3), scheme
    )


def test_background_switches_house_scheme_surface() -> None:
    light = palettes.scheme("magma", "white")
    assert art_scheme(DataArtSpec(engine="rings", background="dark"), light).dark
    assert not art_scheme(DataArtSpec(engine="rings", background="light"), SCHEMES[0]).dark
    assert art_scheme(DataArtSpec(engine="rings"), light) == light
    brand = palettes.brand_scheme(["#112233", "#445566", "#aabbcc"])
    assert art_scheme(DataArtSpec(engine="rings", background="light"), brand) == brand


def test_band_is_centre_five_by_two() -> None:
    top, bottom = band(1600, 900)
    assert (top, bottom) == (130, 770)
    assert all(len(line) < 200 for line in ENGINES.values())


def test_weaker_engines_come_last_and_say_so() -> None:
    from inferno_ghostwriter.images.art import PREFERRED, WEAKER

    assert list(ENGINES) == [*PREFERRED, *WEAKER]
    assert set(WEAKER) == {"network_mesh", "rings"}
    assert all(ENGINES[k].startswith("Weaker") for k in WEAKER)

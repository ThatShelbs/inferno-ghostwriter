"""The six-up sheet: a labelled grid of finished pictures, drawn by code."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from inferno_ghostwriter.demo import png_bytes
from inferno_ghostwriter.images.montage import HEIGHT, WIDTH, Tile, grid, make_montage


def tiles(count: int) -> list[Tile]:
    return [
        Tile(f"Library {i}", f"{10 * i} lines, {300 * i:,} characters", png_bytes(1200 + 40 * i, 700, "#3b528b"))
        for i in range(1, count + 1)
    ]


@pytest.mark.parametrize(("count", "shape"), [(2, (2, 1)), (3, (3, 1)), (4, (2, 2)), (5, (3, 2)), (6, (3, 2)), (9, (3, 3))])
def test_grid_shapes(count: int, shape: tuple[int, int]) -> None:
    assert grid(count) == shape


@pytest.mark.parametrize("count", [2, 4, 6])
def test_the_sheet_is_a_1600_by_900_png(count: int) -> None:
    png = make_montage(tiles(count), "One prompt, six libraries")
    with Image.open(io.BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (WIDTH, HEIGHT) == (1600, 900)


def test_each_tile_is_actually_drawn() -> None:
    with Image.open(io.BytesIO(make_montage(tiles(6), "Title"))) as image:
        rgb = image.convert("RGB")
        colors = {rgb.getpixel((x, y)) for x in range(80, 1500, 40) for y in range(200, 800, 40)}
    assert (0x3B, 0x52, 0x8B) in colors  # the tiles' blue shows up below the title band


def test_fewer_than_two_or_more_than_nine_pictures_is_an_error() -> None:
    with pytest.raises(ValueError, match="2 to 9"):
        make_montage(tiles(1), "x")
    with pytest.raises(ValueError, match="2 to 9"):
        make_montage(tiles(10), "x")

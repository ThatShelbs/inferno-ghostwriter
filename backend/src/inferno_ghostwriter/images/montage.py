"""Several finished pictures on one labeled sheet, drawn by code (no model call).

Used by the experiment's closing image: every library's real chart side by side with its name and size of code.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from inferno_ghostwriter.images.palettes import Scheme
from inferno_ghostwriter.images.palettes import scheme as default_scheme

WIDTH, HEIGHT = 1600, 900
MARGIN = 40
GAP = 24
TITLE_BAND = 92
LABEL_BAND = 70
FONTS = Path(__file__).parent / "memes" / "fonts"
MIN_TILES = 2
MAX_TILES = 9


@dataclass
class Tile:
    label: str
    caption: str
    png: bytes


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _fit(text: str, font_name: str, size: int, width: int) -> ImageFont.FreeTypeFont:
    """The largest font (down to a floor) in which ``text`` fits ``width``."""
    while size > 12:
        font = _font(font_name, size)
        if font.getlength(text) <= width:
            return font
        size -= 1
    return _font(font_name, 12)


def grid(count: int) -> tuple[int, int]:
    """(columns, rows) for ``count`` tiles."""
    columns = count if count <= 3 else 2 if count == 4 else 3
    return columns, -(-count // columns)


def make_montage(tiles: list[Tile], title: str, scheme: Scheme | None = None) -> bytes:
    """A 1600x900 sheet with every tile fitted whole (never cropped) above its label."""
    if not MIN_TILES <= len(tiles) <= MAX_TILES:
        raise ValueError(f"A montage needs {MIN_TILES} to {MAX_TILES} pictures, not {len(tiles)}.")
    scheme = scheme or default_scheme()
    sheet = Image.new("RGB", (WIDTH, HEIGHT), scheme.bg)
    draw = ImageDraw.Draw(sheet)
    inner = WIDTH - 2 * MARGIN
    draw.text((MARGIN, MARGIN - 6), title, font=_fit(title, "Inter-Black.ttf", 46, inner), fill=scheme.ink)
    draw.rectangle((MARGIN, TITLE_BAND - 8, MARGIN + 120, TITLE_BAND - 3), fill=scheme.accent(0))

    columns, rows = grid(len(tiles))
    cell_w = (inner - (columns - 1) * GAP) // columns
    cell_h = (HEIGHT - TITLE_BAND - MARGIN - (rows - 1) * GAP) // rows
    for index, tile in enumerate(tiles):
        left = MARGIN + (index % columns) * (cell_w + GAP)
        top = TITLE_BAND + (index // columns) * (cell_h + GAP)
        draw.rounded_rectangle((left, top, left + cell_w, top + cell_h), radius=14, fill="#ffffff", outline=scheme.line, width=2)
        with Image.open(io.BytesIO(tile.png)) as source:
            picture = source.convert("RGB")
        area_w, area_h = cell_w - 20, cell_h - LABEL_BAND - 12
        picture.thumbnail((area_w, area_h), Image.Resampling.LANCZOS)
        sheet.paste(picture, (left + (cell_w - picture.width) // 2, top + 10 + (area_h - picture.height) // 2))
        text_w = cell_w - 28
        draw.text(
            (left + 14, top + cell_h - LABEL_BAND + 2), tile.label, font=_fit(tile.label, "Inter-Bold.ttf", 28, text_w), fill=scheme.ink
        )
        draw.text((left + 14, top + cell_h - 32), tile.caption, font=_fit(tile.caption, "Inter-Regular.ttf", 20, text_w), fill=scheme.muted)
    out = io.BytesIO()
    sheet.save(out, format="PNG")
    return out.getvalue()

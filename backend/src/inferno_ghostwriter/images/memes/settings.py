"""Meme settings from the author's Cartoon Character Kit: painted backgrounds behind the code-drawn cast.

The kit's meme setting sheet (``<reference library>/Cartoon Character Kit/``) paints the places famous memes happen:
the street of Distracted Boyfriend, the burning room of This is Fine, the balcony at sunset of "Right? Right?". A
staged format with a setting here is drawn over that painting (enlarged and softly blurred, like a photo's background)
instead of the code backdrop. The sheets are the author's own files in the git-ignored library: without them every
format keeps its code backdrop, so nothing depends on them.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

KIT_FOLDER = "Cartoon Character Kit"
SHEET = "Chartoon character Meme Kit II.png"
Box = tuple[int, int, int, int]

# Painted settings on the setting sheet (left, top, right, bottom in sheet pixels, below each tile's title tab).
SETTINGS: dict[str, Box] = {
    "street": (283, 146, 540, 278),
    "garden": (546, 146, 795, 278),
    "burning_room": (802, 146, 1050, 278),
    "meadow": (8, 322, 282, 422),
    "basement": (8, 611, 282, 713),
}
# Which formats are drawn over a painted setting (by the code backdrop they replace).
FORMAT_SETTINGS: dict[str, tuple[str, ...]] = {
    "distracted": ("street",),
    "is_this_a": ("garden",),
    "this_is_fine": ("burning_room",),
    "this_is_fine_2": ("burning_room",),
    "right_right": ("meadow",),
    "pointing_twins": ("basement",),
}

_root: Path | None = None


def configure(reference_dir: Path | None) -> None:
    """Where the reference library lives (set from ``Settings.image_reference_dir`` by the meme room)."""
    global _root
    if reference_dir != _root:
        _root = reference_dir
        _setting_uri.cache_clear()


def settings_for(format_id: str) -> dict[str, str]:
    """Code backdrop name -> painted setting (a PNG data URI) for this format; {} when the kit is not on this machine."""
    out = {}
    for name in FORMAT_SETTINGS.get(format_id, ()):
        uri = _setting_uri(name, str(_root) if _root else "")
        if uri:
            out[name] = uri
    return out


@lru_cache(maxsize=16)
def _setting_uri(name: str, root: str) -> str:
    sheet = Path(root) / KIT_FOLDER / SHEET if root else None
    if sheet is None or name not in SETTINGS or not sheet.is_file():
        return ""
    try:
        with Image.open(sheet) as img:
            tile = img.convert("RGB").crop(SETTINGS[name])
    except OSError:
        return ""
    # Enlarged paintings look soft, so lean into it: a gentle blur and a touch less contrast reads as depth of field,
    # which keeps the eye on the crisp cast and the words in front.
    tile = tile.resize((tile.width * 4, tile.height * 4), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(3))
    tile = ImageEnhance.Contrast(tile).enhance(0.92)
    buf = io.BytesIO()
    tile.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def image_svg(uri: str, box: tuple[float, float, float, float]) -> str:
    """The painted setting filling ``box`` (cropped to cover it, never stretched)."""
    x, y, w, h = box
    return f'<image href="{uri}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" preserveAspectRatio="xMidYMid slice"/>'

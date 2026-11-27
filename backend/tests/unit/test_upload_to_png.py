import io

import pytest
from PIL import Image

from inferno_ghostwriter.images.render import upload_to_png

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100"><rect width="200" height="100" fill="#ed6925"/></svg>'


def png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (30, 20), "#ed6925").save(out, format="PNG")
    return out.getvalue()


def test_png_passes_through() -> None:
    data = png_bytes()
    assert upload_to_png(data) == (data, 30, 20)


@pytest.mark.parametrize("prefix", ["", "﻿", '<?xml version="1.0" encoding="UTF-8"?>\n', "  \n<!-- made by a tool -->\n"])
def test_svg_is_rendered_to_png(prefix: str) -> None:
    png, width, height = upload_to_png((prefix + SVG).encode("utf-8"))
    assert png.startswith(b"\x89PNG") and width == 1600 and height == 800


def test_garbage_still_fails() -> None:
    with pytest.raises(OSError):
        upload_to_png(b"not an image")

import base64
import io

from PIL import Image

from inferno_ghostwriter.export.render import CLIPBOARD_MAX_WIDTH, web_data_uri


def _decode(uri: str) -> Image.Image:
    header, data = uri.split(",", 1)
    assert header.startswith("data:image/")
    return Image.open(io.BytesIO(base64.b64decode(data)))


def test_large_image_is_shrunk_for_paste() -> None:
    noise = Image.effect_noise((3000, 2000), 80).convert("RGB")
    buf = io.BytesIO()
    noise.save(buf, format="PNG")
    original = buf.getvalue()

    uri = web_data_uri(original)

    assert _decode(uri).width <= CLIPBOARD_MAX_WIDTH
    assert len(uri) < len(original) / 4


def test_small_image_is_left_alone() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, format="PNG")

    uri = web_data_uri(buf.getvalue())

    assert uri.startswith("data:image/png;base64,")
    assert _decode(uri).size == (200, 100)

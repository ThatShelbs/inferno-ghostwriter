"""The local reference library: example images the author collected as the quality bar.

The library is a folder (``Settings.image_reference_dir``, by default ``examples/`` at the repository root) with one
subfolder per category. The images are third-party memes and art, so the folder is git-ignored and never shipped;
everything works without it, just without references for the judge and the compare galleries.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

CATEGORIES = {
    "meme": "Meme",
    "data_art": "Data Art",
    "cartoon": "Cartoon Jokes",
    "diagram": "Others",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# Which reference file shows the original of each meme format (a case-insensitive prefix of the file name).
MEME_REFERENCES = {
    "nope_yep": "drake",
    "pointing_twins": "spiderman meme",
    "distracted": "distracted boyfriend",
    "expanding_brain": "expanding brain",
    "this_is_fine": "this is fine",
    "this_is_fine_2": "this is fine",
    "two_buttons": "button push",
    "midwit_bell_curve": "iq bell curve",
    "gru_plan": "gru",
    "right_right": "starwars anakin",
    "is_this_a": "is this a",
    "backs_into_hedge": "simpson bush",
    "joke_pie": "zombie apocalypse",
    "joke_pie_3d": "1_jt-r6",
    "labeled_map": "north still north",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


class ReferenceLibrary:
    def __init__(self, root: Path | None) -> None:
        self.root = root

    @property
    def available(self) -> bool:
        return self.root is not None and self.root.is_dir()

    def images(self, category: str) -> list[Path]:
        if not self.available or category not in CATEGORIES:
            return []
        assert self.root is not None
        folder = self.root / CATEGORIES[category]
        if not folder.is_dir():
            return []
        return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)

    def find(self, category: str, prefix: str) -> list[Path]:
        want = _slug(prefix)
        return [p for p in self.images(category) if _slug(p.stem).startswith(want)]

    def for_meme(self, format_id: str) -> Path | None:
        prefix = MEME_REFERENCES.get(format_id)
        if not prefix:
            return None
        found = self.find("meme", prefix) or self.find("cartoon", prefix)
        return found[0] if found else None

    def for_category(self, category: str, limit: int = 2) -> list[Path]:
        return self.images(category)[:limit]


def load_png(paths: Iterable[Path], max_side: int = 768) -> list[bytes]:
    """Read reference images as PNG bytes small enough to send to a model; unreadable files are skipped."""
    from io import BytesIO

    from PIL import Image

    out: list[bytes] = []
    for path in paths:
        try:
            with Image.open(path) as source:
                img = source.convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = BytesIO()
            img.save(buf, format="PNG")
            out.append(buf.getvalue())
        except Exception:  # noqa: BLE001 - a bad reference never breaks an image
            continue
    return out

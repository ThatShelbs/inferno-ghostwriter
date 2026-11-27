"""The ideas board every image room shares (opening image, meme, in-body images).

New pitches are *added* to the board instead of replacing it, so the idea the author is looking at keeps its index
while a new round is pitched, and earlier ideas (tried or not) stay one click away. Each round is a ``batch`` so the
board can show the newest first. The board holds at most ``MAX_PITCHES``: when it is full the oldest untried ideas
make room, and every stored index (chosen, tried, vetoed...) is moved with :func:`remap`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

MAX_PITCHES = 18


def batch_of(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("batch") or 0)
    except (TypeError, ValueError):
        return 0


def merge(
    old: list[dict[str, Any]], new: list[dict[str, Any]], *, keep: Iterable[int] = (), cap: int = MAX_PITCHES
) -> tuple[list[dict[str, Any]], dict[int, int], list[int]]:
    """Add ``new`` pitches after ``old`` ones.

    Returns the merged entries, where each surviving old index went (old -> new index) and the indexes of the new
    pitches. Old pitches in ``keep`` (the one on show, the tried ones) are never dropped; others go oldest first
    when the board would hold more than ``cap``."""
    kept_ids = set(keep)
    batch = max((batch_of(e) for e in old), default=0) + 1
    overflow = max(0, len(old) + len(new) - cap)
    droppable = [i for i in range(len(old)) if i not in kept_ids]
    dropped = set(droppable[:overflow])
    survivors = [i for i in range(len(old)) if i not in dropped]
    mapping = {i: k for k, i in enumerate(survivors)}
    entries = [old[i] for i in survivors] + [{**e, "batch": batch} for e in new]
    return entries, mapping, list(range(len(survivors), len(entries)))


def remap(indexes: Iterable[Any], mapping: dict[int, int]) -> list[int]:
    """Stored indexes moved to their place on the merged board (dropped ones are left out)."""
    return sorted({mapping[i] for i in indexes if isinstance(i, int) and i in mapping})


def remap_one(index: Any, mapping: dict[int, int]) -> int | None:
    return mapping.get(index) if isinstance(index, int) else None


def edit_pitch(entry: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    """The pitch with the author's changes (only non-empty text fields the pitch already uses are taken)."""
    changed = dict(entry)
    for key, value in fields.items():
        text = str(value or "").strip()
        if text:
            changed[key] = text
    changed["edited"] = True
    return changed

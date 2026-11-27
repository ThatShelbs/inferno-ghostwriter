"""Which styles, formats and looks the author wants more or less of (Image studio's priorities chart).

A priority is a tag id mapped to ``prefer`` or ``avoid``; anything missing is neutral. Tag ids are namespaced
(``style:editorial``, ``meme:nope_yep``, ``kind:chart``, ``palette:viridis``, ``medium:flat``, ``cast:dogs``,
``staging:wide``). This module is the only place the chart is built and applied:

* ``avoid`` removes an opening style from what Auto may pitch and a look from random experiments
  (``remix.choose_tweaks(priorities=)`` does the weighting);
* ``prefer`` moves a style first and makes a look likelier;
* every pitching room is also told in one line (``note``), which is how meme formats and image kinds are steered.

No model call is spent on any of it. A pin the author sets on one image still wins over a priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inferno_ghostwriter.images import remix
from inferno_ghostwriter.images.kinds import KINDS
from inferno_ghostwriter.images.memes.formats import FAMILIES, FORMATS
from inferno_ghostwriter.images.opening.styles import STYLES

PREFER, AVOID = "prefer", "avoid"
VALUES = (PREFER, AVOID)

GROUPS = {
    "style": "Opening styles",
    "meme": "Meme formats",
    "kind": "Image kinds",
    "palette": "Colors",
    "medium": "Medium",
    "cast": "Who is in it",
    "staging": "Staging",
}


@dataclass(frozen=True)
class Tag:
    id: str
    label: str
    group: str
    hint: str = ""
    swatch: tuple[str, ...] = ()


def catalog() -> list[Tag]:
    """Every tag the chart offers, in display order."""
    tags = [Tag(f"style:{s.id}", s.label, GROUPS["style"], s.summary) for s in STYLES if s.id != "meme"]
    tags += [Tag(f"meme:{f.id}", f.name, f"{GROUPS['meme']}: {FAMILIES[f.family]}", f.when_to_use) for f in FORMATS]
    tags += [Tag(f"kind:{k.id}", k.label, GROUPS["kind"], k.use) for k in KINDS.values() if k.id not in ("hero", "meme", "hands_on_viz")]
    for dimension in (remix.PALETTE, remix.MEDIUM, remix.CAST, remix.STAGING):
        tags += [
            Tag(f"{dimension}:{t.id}", t.label, GROUPS[dimension], swatch=tuple(t.colors)) for t in remix.TWEAKS if t.dimension == dimension
        ]
    return tags


def clean(raw: dict[str, Any] | None) -> dict[str, str]:
    """Keep only known tags with a real value (a bad entry is dropped, never an error)."""
    known = {t.id for t in catalog()}
    return {k: str(v) for k, v in (raw or {}).items() if k in known and v in VALUES}


def merge(persona: dict[str, Any] | None, post: dict[str, Any] | None) -> dict[str, str]:
    """The post's own choices win over the persona's defaults; ``neutral`` is not stored, so a post cannot clear one
    except by choosing the opposite, which is what the chart does."""
    return {**clean(persona), **clean(post)}


def ids(priorities: dict[str, str] | None, namespace: str, value: str) -> list[str]:
    """The ids (without namespace) marked ``value`` in one namespace, in a stable order."""
    prefix = f"{namespace}:"
    return sorted(k[len(prefix) :] for k, v in (priorities or {}).items() if v == value and k.startswith(prefix))


def order_styles(style_ids: list[str] | tuple[str, ...], priorities: dict[str, str] | None) -> list[str]:
    """Style ids with avoided ones removed (never all of them) and preferred ones first; the rest keep their order."""
    avoided, liked = set(ids(priorities, "style", AVOID)), ids(priorities, "style", PREFER)
    kept = [s for s in style_ids if s not in avoided] or list(style_ids)
    return [*[s for s in kept if s in liked], *[s for s in kept if s not in liked]]


def note(priorities: dict[str, str] | None) -> str:
    """One line for the pitching rooms; empty when nothing is set."""
    labels = {t.id: t.label for t in catalog()}
    parts = []
    for value, phrase in ((PREFER, "The author prefers"), (AVOID, "The author does not want")):
        names = [labels[k] for k, v in sorted((priorities or {}).items()) if v == value and k in labels]
        if names:
            parts.append(f"{phrase}: {', '.join(names)}.")
    return " ".join(parts)

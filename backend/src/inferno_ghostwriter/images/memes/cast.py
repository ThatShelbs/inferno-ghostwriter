"""The cast of the staged memes, drawn with the figure library (``images/figures``).

Stagings still speak the casting vocabulary Claude picks from (a kind, an expression, a pose, a role). This module turns
each pick into a figure: people in clean line art by default, dressed the way the original meme dresses that role
(the plaid shirt and the red dress of Distracted Boyfriend, the orange puffer jacket of Drake, the sweating man in blue
of Two Buttons), and our ghost only when Claude casts it. Animals and robots are no longer drawn; they become people.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from inferno_ghostwriter.images.figures import SKIN_TONES, FigureColors, figure
from inferno_ghostwriter.images.figures.base import HAIR_TONES
from inferno_ghostwriter.images.palettes import Scheme

# The casting vocabulary's poses and expressions, as the figure library names them.
POSE = {
    "stand": "standing",
    "wave": "yep",
    "point": "pointing",
    "point_up": "yep",
    "arms_up": "shrug",
    "shrug": "shrug",
    "hold": "standing",
    "hold_both": "standing",
    "typing": "laptop",
    "facepalm": "nervous",
    "chin": "arms_crossed",
    "wipe": "nervous",
    "block": "nope",
    "block_back": "nope",
    "reach": "pointing",
    "present": "pointing",
    "proud": "arms_crossed",
    "sit": "standing",
    "sit_hold": "standing",
    "sit_type": "laptop",
    "float": "standing",
}
EXPRESSION = {
    "happy": "happy",
    "beaming": "happy",
    "smug": "smug",
    "blank": "neutral",
    "hopeful": "happy",
    "nervous": "nervous",
    "worried": "nervous",
    "shocked": "shocked",
    "panic": "panicked",
    "calm": "calm",
    "thinking": "focused",
    "mind_blown": "impressed",
    "deadpan": "neutral",
    "sad": "crying",
    "nope": "disgusted",
    "grumpy": "disgusted",
    "determined": "focused",
    "sweating": "nervous",
    "love": "impressed",
    "sleepy": "calm",
    "content": "calm",
    "frozen_smile": "smug",
}


@dataclass(frozen=True)
class RoleLook:
    outfit: str = "tee"
    hair: str = "short"
    shirt: str = ""
    pose: str = ""  # a figure pose that replaces the beat's mapped pose
    skin: int = 1
    hair_tone: int = 0
    facing: str = ""  # "left"/"right" replaces the beat's facing ("" keeps it)


# How the original meme dresses each role (by role name; the same name means the same look in every format).
ROLE_LOOKS: dict[str, RoleLook] = {
    # Body toward his partner (right), head turned back over his shoulder at the passer-by walking off to the left.
    "distracted": RoleLook("plaid", "messy", "#3b6ea8", pose="looking_back", skin=1, hair_tone=1, facing="right"),
    "shiny": RoleLook("dress", "long", "#d6232a", pose="walking", skin=0, hair_tone=2, facing="left"),
    "partner": RoleLook("tee", "long", "#5b8fc9", skin=1, hair_tone=2),
    "chooser": RoleLook("jacket", "short", "#f08a24", skin=3, hair_tone=0),
    "twin": RoleLook("tee", "short", "#c8282e", skin=1, hair_tone=0),
    "midwit": RoleLook("tee", "messy", "#6d6d78", skin=1, hair_tone=0),
    "beginner": RoleLook("tee", "bald", "#e8e2d6", skin=1),
    "expert": RoleLook("hoodie", "short", "#7a4a2a", skin=1, hair_tone=0),
    "calm_one": RoleLook("tee", "bald", "#f2c14e", skin=2),
    "planner": RoleLook("tee", "bald", "#3a3a46", skin=1),
    "debater": RoleLook("tee", "short", "#4a6f8a", skin=2, hair_tone=1),
    "realizer": RoleLook("tee", "short", "#f4f4f4", skin=1),
    "knower": RoleLook("tee", "short", "#f4f4f4", skin=1),
    "misjudger": RoleLook("tee", "short", "#3a3a46", skin=4),
    "confident": RoleLook("tee", "short", "#3a3a46", skin=1, hair_tone=1),
    "hopeful": RoleLook("dress", "long", "#7a5aa8", skin=0, hair_tone=1),
}
VARIANTS = (RoleLook("tee", "short"), RoleLook("dress", "long", skin=0, hair_tone=2), RoleLook("hoodie", "messy", skin=3, hair_tone=1))
_counter = itertools.count()


@dataclass
class Placed:
    """A figure placed in a scene (what a staging adds to its SVG)."""

    svg: str
    anchors: dict[str, tuple[float, float]] = field(default_factory=dict)


def draw(ch: Any, x: float, y: float, height: float, *, sch: Scheme | None = None, **_: Any) -> Placed:
    """Draw cast member ``ch`` (a ``kit.Character``) with its feet at (x, y), ``height`` tall."""
    role = str(getattr(ch, "label", "") or "")
    pose = POSE.get(ch.pose, "standing")
    expression = EXPRESSION.get(ch.expression, "neutral")
    facing = "left" if ch.facing == "left" else "right"
    if ch.kind == "ghost":
        colors = FigureColors.from_scheme(sch) if sch is not None else None
        sym = figure("ghost", pose, colors=colors, expression=expression, facing=facing, tag=f"g{next(_counter)}")
    else:
        look = ROLE_LOOKS.get(role) or VARIANTS[ch.variant % len(VARIANTS)]
        if look.pose and (ch.pose in ("point", "stand", "wave", "proud") or role in ("distracted", "shiny")):
            pose = look.pose
        facing = look.facing or facing
        if role == "chooser" and ch.pose == "point":
            pose = "yep"  # Drake's approving beat
        shirt = look.shirt or (sch.ramp[len(sch.ramp) // 2] if sch is not None else "#cf4446")
        colors = FigureColors(skin=SKIN_TONES[look.skin % len(SKIN_TONES)], hair=HAIR_TONES[look.hair_tone % len(HAIR_TONES)], shirt=shirt)
        sym = figure(
            "line", pose, colors=colors, expression=expression, facing=facing, outfit=look.outfit, hair=look.hair, tag=f"p{next(_counter)}"
        )
    placed = f"<defs>{sym.svg}</defs>{sym.use(x, y, height)}"
    return Placed(placed)

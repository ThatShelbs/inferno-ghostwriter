"""The cast of the staged memes: the casting vocabulary Claude picks from, drawn with the figure library.

Claude casts each role with a kind (``person``, ``ghost`` or ``robot``), an expression and, in comics, a pose; this
module is the only place that vocabulary is defined (``Character``, ``KINDS``, ``EXPRESSIONS``, ``POSES``, ``menu``)
and turns each pick into a figure (``images/figures``): people in clean line art by default, dressed the way the
original meme dresses that role (the plaid shirt and the red dress of Distracted Boyfriend, the orange puffer jacket
of Drake, the sweating man in blue of Two Buttons), and the house ghost or robot only when Claude casts them.

Older meme states may name kinds, accessories or hand props the earlier rigged kit drew; they still load: a dog or
cat becomes a person, and anything the figures cannot draw is ignored.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from inferno_ghostwriter.images.figures import SKIN_TONES, FigureColors, figure
from inferno_ghostwriter.images.figures.base import HAIR_TONES
from inferno_ghostwriter.images.palettes import Scheme

KINDS = ("person", "ghost", "robot")
KIND_HINTS = {
    "person": "a line-art person, dressed like the original meme's character (no likeness of anyone real)",
    "ghost": "the friendly Inferno Ghostwriter ghost (the house mascot)",
    "robot": "the friendly house robot with a glowing visor face",
}
LEGACY_KINDS = {"dog": "person", "cat": "person"}  # kinds older meme states may name
ACCESSORIES = ("none", "sunglasses")  # sunglasses draw the figures' `cool` shades; older accessories are ignored
PROPS = ("none",)  # hand props are part of each staging now; older picks are ignored


def kind_of(kind: object, default: str = "person") -> str:
    """A cast kind from a pick, mapping the older kinds (dog, cat) to a person."""
    k = str(kind or "")
    k = LEGACY_KINDS.get(k, k)
    return k if k in KINDS else default


@dataclass(frozen=True)
class Character:
    """One cast member in one beat: who, how they look and which way they face."""

    kind: str = "person"
    expression: str = "happy"
    pose: str = "stand"
    facing: str = "right"
    accessory: str = "none"
    prop: str = "none"
    variant: int = 0
    label: str = ""  # the role (picks the original meme's look, names it in alt text)


# The poses and expressions Claude may pick: name -> (the figure library's name, what a prompt reads).
POSES: dict[str, tuple[str, str]] = {
    "stand": ("standing", "standing, arms relaxed"),
    "wave": ("yep", "a cheerful hand up"),
    "point": ("pointing", "pointing ahead (toward what it faces)"),
    "point_up": ("yep", "pointing up, 'aha'"),
    "arms_up": ("shrug", "both arms out: celebrating or panicking"),
    "shrug": ("shrug", "shrugging, palms up"),
    "hold": ("standing", "standing, holding still"),
    "hold_both": ("standing", "standing firm, holding on"),
    "typing": ("laptop", "typing on a laptop at a small desk"),
    "facepalm": ("nervous", "a hand to the brow, under pressure"),
    "chin": ("arms_crossed", "arms folded, weighing it up"),
    "wipe": ("nervous", "wiping sweat off the brow with a cloth"),
    "block": ("nope", "turned away, palm raised: 'no thanks'"),
    "block_back": ("nope", "turned away with a palm up (the 'nope' panel)"),
    "reach": ("pointing", "reaching forward"),
    "present": ("pointing", "presenting something to the side it faces"),
    "proud": ("arms_crossed", "arms folded, chest out"),
    "sit": ("standing", "at rest"),
    "sit_hold": ("standing", "at rest, calm"),
    "sit_type": ("laptop", "working at a laptop"),
    "float": ("standing", "idle, arms down"),
}
EXPRESSIONS: dict[str, tuple[str, str]] = {
    "happy": ("happy", "big happy grin"),
    "beaming": ("happy", "overjoyed, eyes squeezed happy"),
    "smug": ("smug", "half-lidded, lopsided smirk"),
    "blank": ("neutral", "an expressionless stare"),
    "hopeful": ("happy", "hopeful, smiling"),
    "nervous": ("nervous", "forced wobbly smile, sweat drop"),
    "worried": ("nervous", "brows up, wobbly mouth, sweat"),
    "shocked": ("shocked", "wide eyes, O mouth"),
    "panic": ("panicked", "wide eyes, screaming, sweating"),
    "calm": ("calm", "eyes closed, serene smile"),
    "thinking": ("focused", "narrowed eyes, locked in"),
    "mind_blown": ("impressed", "brows up, an amazed 'ooh'"),
    "deadpan": ("neutral", "flat, unimpressed"),
    "sad": ("crying", "tears streaming"),
    "nope": ("disgusted", "eyes squeezed shut in disgust"),
    "grumpy": ("disgusted", "frowning, turning away"),
    "determined": ("focused", "focused brows, flat mouth"),
    "sweating": ("nervous", "worried, sweating"),
    "love": ("impressed", "starry-eyed admiration"),
    "sleepy": ("calm", "eyes closed"),
    "content": ("calm", "eyes closed, content smile"),
    "frozen_smile": ("smug", "still smiling, but the eyes have realized something (the 'right?' panel)"),
    "cool": ("cool", "dark sunglasses and a confident grin"),
}
POSE = {k: v[0] for k, v in POSES.items()}
EXPRESSION = {k: v[0] for k, v in EXPRESSIONS.items()}


def menu() -> str:
    """The cast, expressions and poses, as a prompt reads them."""
    kinds = "; ".join(f"`{k}` ({h})" for k, h in KIND_HINTS.items())
    exprs = ", ".join(f"`{k}` ({h})" for k, (_, h) in EXPRESSIONS.items())
    poses = ", ".join(f"`{k}` ({h})" for k, (_, h) in POSES.items())
    return (
        f"Characters: {kinds}.\nExpressions: {exprs}.\nPoses (comics): {poses}.\n"
        "Accessories: `none`, or `sunglasses`. Hand props are part of each staging (use `none`)."
    )


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
    # Two Buttons: the man in a blue suit wiping his brow (his own look; Claude still casts the role `chooser`).
    "sweater": RoleLook("tee", "short", "#3d6db5", skin=1, hair_tone=0),
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


def role_look(ch: Character) -> RoleLook:
    """How a person in this role is dressed (the original meme's look, else a variant)."""
    return ROLE_LOOKS.get(ch.label) or VARIANTS[ch.variant % len(VARIANTS)]


def colors_for(ch: Character, sch: Scheme | None = None) -> FigureColors:
    """The colors ``ch`` is drawn in, so a staging can draw a matching arm or hand of its own."""
    if kind_of(ch.kind) != "person":
        return FigureColors.from_scheme(sch) if sch is not None else FigureColors()
    look = role_look(ch)
    shirt = look.shirt or (sch.ramp[len(sch.ramp) // 2] if sch is not None else "#cf4446")
    return FigureColors(skin=SKIN_TONES[look.skin % len(SKIN_TONES)], hair=HAIR_TONES[look.hair_tone % len(HAIR_TONES)], shirt=shirt)


def draw(ch: Character, x: float, y: float, height: float, *, sch: Scheme | None = None, **_: Any) -> Placed:
    """Draw cast member ``ch`` with its feet at (x, y), ``height`` tall."""
    role = ch.label
    kind = kind_of(ch.kind)
    pose = POSE.get(ch.pose, "standing")
    expression = "cool" if ch.accessory == "sunglasses" else EXPRESSION.get(ch.expression, "neutral")
    facing = "left" if ch.facing == "left" else "right"
    colors = colors_for(ch, sch)
    if kind != "person":
        sym = figure(kind, pose, colors=colors if sch is not None else None, expression=expression, facing=facing, tag=f"g{next(_counter)}")
    else:
        look = role_look(ch)
        if look.pose and (ch.pose in ("point", "stand", "wave", "proud") or role in ("distracted", "shiny")):
            pose = look.pose
        facing = look.facing or facing
        if role == "chooser" and ch.pose == "point":
            pose = "yep"  # Drake's approving beat
        sym = figure(
            "line", pose, colors=colors, expression=expression, facing=facing, outfit=look.outfit, hair=look.hair, tag=f"p{next(_counter)}"
        )
    placed = f"<defs>{sym.svg}</defs>{sym.use(x, y, height)}"
    return Placed(placed)

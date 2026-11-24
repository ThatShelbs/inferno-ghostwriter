"""The ``ghost`` style: the house mascot, a friendly spectral ghost (never spooky). A soft dome with a scalloped tail
that floats just above its shadow, nubby arms, big oval eyes and rosy cheeks. Faces right in a 180 x 160 box."""

from __future__ import annotations

import math

from inferno_ghostwriter.images.figures.base import (
    LENS,
    Arm,
    FigureColors,
    Point,
    angle,
    desk_laptop,
    flashlight,
    fmt,
    limb,
    local_to_world,
    place,
    reach,
    shadow,
    towel,
)
from inferno_ghostwriter.images.figures.faces import face
from inferno_ghostwriter.images.palettes import mix

VIEW_BOX = (-90.0, -160.0, 180.0, 160.0)
W = 3.0
SHOULDER: Point = (30.0, -80.0)
REACH = 36.0  # ghost arms are soft, boneless nubs: one gentle curve, no elbow
ARM_W = 12.0

ARMS: dict[str, tuple[Arm | None, Arm]] = {
    "standing": (Arm((-44, -58), -1, "mitt"), Arm((44, -58), 1, "mitt")),
    "pointing": (Arm((-44, -58), -1, "mitt"), Arm((60, -88), 1, "point")),
    "looking_back": (Arm((-44, -58), -1, "mitt"), Arm((44, -58), 1, "mitt")),
    "nervous": (Arm((-44, -58), -1, "mitt"), Arm((24, -116), -1, "towel")),
    "flashlight": (Arm((-44, -58), -1, "mitt"), Arm((58, -84), 1, "flashlight")),
    "laptop": (Arm((-44, -58), -1, "mitt"), Arm((52, -70), 1, "mitt")),
    "shrug": (Arm((-54, -98), -1, "mitt"), Arm((54, -98), 1, "mitt")),
    "arms_crossed": (Arm((12, -60), 1, "mitt"), Arm((-12, -58), -1, "mitt")),
    "nope": (Arm((-44, -58), -1, "mitt"), Arm((48, -112), 1, "palm", -95)),
    "yep": (Arm((-44, -58), -1, "mitt"), Arm((58, -108), 1, "point", -40)),
    "walking": (Arm((-50, -70), -1, "mitt"), Arm((52, -72), 1, "mitt")),
}

# The mascot never scowls: its own defaults where the shared ones would read as cross.
DEFAULTS = {"pointing": "happy", "flashlight": "neutral", "laptop": "neutral", "yep": "happy", "arms_crossed": "smug"}

CROSSED = {"arms_crossed"}

_BODY = (
    "M-40 -100 C-40 -128 -22 -147 2 -147 C26 -147 44 -128 44 -100 C44 -72 45 -46 51 -28 "
    "Q55 -16 45 -15 Q37 -3 28 -15 Q19 -3 9 -15 Q-1 -3 -11 -15 Q-21 -3 -31 -15 Q-43 -10 -55 -17 "
    "Q-46 -27 -44 -44 C-42 -62 -40 -80 -40 -100 Z"
)
_GLIDE = (
    "M-38 -100 C-38 -128 -20 -147 4 -147 C28 -147 46 -128 46 -100 C46 -74 46 -52 44 -38 "
    "Q42 -24 32 -20 Q24 -10 15 -21 Q7 -11 -2 -23 Q-12 -15 -20 -27 Q-36 -26 -52 -32 Q-66 -36 -76 -28 "
    "Q-68 -46 -52 -52 Q-40 -58 -38 -72 C-38 -82 -38 -90 -38 -100 Z"
)


def _hand(kind: str, at: Point, rot: float, c: FigureColors) -> str:
    st = f'fill="{c.ghost}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    mitt = f'<circle cx="1" cy="0" r="7" {st}/>'
    if kind == "point":
        return place(at, rot, f'<rect x="1" y="-5.4" width="15" height="6.4" rx="3.2" {st}/>{mitt}')
    if kind == "palm":
        return place(at, rot, f'<ellipse cx="4" cy="0" rx="9.5" ry="8" {st}/><ellipse cx="2" cy="-8" rx="4" ry="3" {st}/>')
    return place(at, rot, mitt)


def _arm(shoulder: Point, arm: Arm, c: FigureColors) -> tuple[str, Point, Point]:
    hand = reach(shoulder, arm.to, REACH / 2, REACH / 2)
    mid = ((shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2)
    d = max(1e-6, math.dist(shoulder, hand))
    sag = 3.5 * arm.bend
    elbow = (mid[0] - (hand[1] - shoulder[1]) / d * sag, mid[1] + (hand[0] - shoulder[0]) / d * sag)
    rot = arm.hand_rot if arm.hand_rot is not None else angle(elbow, hand)
    parts = []
    if arm.hand == "flashlight":
        parts.append(place(hand, -8, flashlight(c, W * 0.8)))
    parts.append(limb([shoulder, elbow, hand], ARM_W, c.ghost, c.ink, W, radius=14))
    parts.append(_hand("mitt" if arm.hand in ("flashlight", "towel") else arm.hand, hand, rot, c))
    if arm.hand == "towel":
        parts.append(place(hand, rot, towel(c, W * 0.8), 0.9))
    lens = local_to_world(hand, -8, LENS) if arm.hand == "flashlight" else hand
    return "".join(parts), hand, lens


def draw(pose: str, c: FigureColors, expression: str, sid: str, *, f_head: int = 1) -> tuple[str, dict[str, Point]]:
    back_arm, front_arm = ARMS[pose]
    anchors: dict[str, Point] = {"head": (0.0, -108.0), "top": (0.0, -147.0)}
    prop = ""
    if pose == "laptop":
        prop, kb = desk_laptop(c, 32, -64, 50, W, lid=34)
        front_arm = Arm(kb, front_arm.bend, front_arm.hand)
        anchors["screen"] = (68.0, -84.0)
    back_m = ""
    if back_arm is not None:
        back_m, bh, _ = _arm((-SHOULDER[0], SHOULDER[1]), back_arm, c)
        anchors["back_hand"] = bh
    front_m, fh, lens = _arm(SHOULDER, front_arm, c)
    anchors["hand"] = fh
    if front_arm.hand == "flashlight":
        anchors["lens"] = lens
    st = f'stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    glide = pose == "walking"
    path = _GLIDE if glide else _BODY
    shade = mix(c.ghost, c.ink, 0.1)
    clip = f"{sid}-body"
    body = (
        f'<clipPath id="{clip}"><path d="{path}"/></clipPath>'
        f'<g clip-path="url(#{clip})"><path d="{path}" fill="{shade}"/>'
        # The lit body, nudged up and back, leaves a soft crescent of shade on the far side: volume without gradients.
        f'<path d="{path}" fill="{c.ghost}" transform="translate(-7 -6)"/></g>'
        f'<path d="{path}" fill="none" {st}/>'
        f'<path d="M-27 -117 C-25 -131 -15 -140 -3 -142" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round"/>'
    )
    trail = ""
    if glide:
        trail = (
            f'<path d="M-78 -62 H-58 M-84 -78 H-62 M-74 -46 H-60" stroke="{c.ink}" stroke-width="2.4" stroke-linecap="round" '
            'stroke-opacity="0.35"/>'
        )
    f = f_head
    feats = face(
        expression,
        cx=f * 8.0 + (2 if glide else 0),
        cy=-104.0,
        s=1.3,
        f=f,
        ink=c.ink,
        cheek=c.cheek,
        spread=9.5,
        cheeks=True,
        brows=expression not in ("neutral", "happy", "calm"),
    )
    out = [shadow(36, c.ink), trail]
    if pose not in CROSSED:
        out.append(back_m)
    out.append(body)
    out.append(feats)
    if pose in CROSSED:
        out.append(back_m)
    out += [prop, front_m]
    return "".join(out), anchors

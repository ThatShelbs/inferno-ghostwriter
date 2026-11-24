"""The ``robot`` style: the house robots (Nova and Byte in the author's character kit). A glossy white shell, a dark
visor where the face glows in cyan, a glowing core on the chest and jointed limbs. Faces right in a 160 x 200 box."""

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
    ik,
    limb,
    local_to_world,
    place,
    shadow,
    towel,
)
from inferno_ghostwriter.images.figures.faces import face
from inferno_ghostwriter.images.palettes import mix

VIEW_BOX = (-100.0, -200.0, 200.0, 200.0)
W = 3.0
GLOW = "#4fe3ff"
VISOR = "#1a1d36"
SHOULDER: Point = (30.0, -104.0)
UPPER, FORE = 24.0, 24.0
ARM_W = 11.0

ARMS: dict[str, tuple[Arm | None, Arm]] = {
    "standing": (Arm((-40, -60), -1, "mitt"), Arm((40, -60), 1, "mitt")),
    "pointing": (Arm((-40, -60), -1, "mitt"), Arm((76, -108), 1, "point")),
    "looking_back": (Arm((-40, -60), -1, "mitt"), Arm((40, -60), 1, "mitt")),
    "nervous": (Arm((-40, -60), -1, "mitt"), Arm((18, -150), -1, "towel")),
    "flashlight": (Arm((-40, -60), -1, "mitt"), Arm((72, -100), 1, "flashlight")),
    "laptop": (Arm((-40, -60), -1, "mitt"), Arm((56, -80), 1, "mitt")),
    "shrug": (Arm((-60, -112), -1, "palm"), Arm((60, -112), 1, "palm")),
    "arms_crossed": (Arm((14, -86), 1, "mitt"), Arm((-14, -84), -1, "mitt")),
    "nope": (Arm((-40, -60), -1, "mitt"), Arm((52, -146), 1, "palm", -95)),
    "yep": (Arm((-40, -60), -1, "mitt"), Arm((70, -140), 1, "point", -40)),
    "walking": (Arm((-46, -72), -1, "mitt"), Arm((46, -70), 1, "mitt")),
}
DEFAULTS = {"pointing": "happy", "flashlight": "neutral", "laptop": "neutral", "yep": "happy", "arms_crossed": "smug", "standing": "happy"}
CROSSED = {"arms_crossed"}


def _hand(kind: str, at: Point, rot: float, c: FigureColors) -> str:
    st = f'fill="{c.ghost}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    mitt = f'<circle cx="1" cy="0" r="7.5" {st}/>'
    if kind == "point":
        return place(at, rot, f'<rect x="1" y="-5" width="15" height="6" rx="3" {st}/>{mitt}')
    if kind == "palm":
        return place(at, rot, f'<ellipse cx="4" cy="0" rx="10" ry="8.5" {st}/><rect x="0" y="-12" width="5" height="9" rx="2.5" {st}/>')
    return place(at, rot, mitt)


def _arm(shoulder: Point, arm: Arm, c: FigureColors) -> tuple[str, Point, Point]:
    elbow = ik(shoulder, arm.to, UPPER, FORE, arm.bend)
    d = math.dist(shoulder, arm.to)
    hand = (
        arm.to
        if d <= UPPER + FORE
        else (
            shoulder[0] + (arm.to[0] - shoulder[0]) * (UPPER + FORE) / d,
            shoulder[1] + (arm.to[1] - shoulder[1]) * (UPPER + FORE) / d,
        )
    )
    rot = arm.hand_rot if arm.hand_rot is not None else angle(elbow, hand)
    joint = mix(c.ghost, c.ink, 0.55)
    parts = []
    if arm.hand == "flashlight":
        parts.append(place(hand, -8, flashlight(c, W * 0.8)))
    parts.append(limb([shoulder, elbow, hand], ARM_W, c.ghost, c.ink, W, radius=4))
    parts.append(f'<circle cx="{fmt(elbow[0])}" cy="{fmt(elbow[1])}" r="5" fill="{joint}"/>')
    parts.append(_hand("mitt" if arm.hand in ("flashlight", "towel") else arm.hand, hand, rot, c))
    if arm.hand == "towel":
        parts.append(place(hand, rot, towel(c, W * 0.8), 0.9))
    lens = local_to_world(hand, -8, LENS) if arm.hand == "flashlight" else hand
    return "".join(parts), hand, lens


def _legs(c: FigureColors, walking: bool) -> str:
    joint = mix(c.ghost, c.ink, 0.55)
    st = f'fill="{c.ghost}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    out = []
    for side in (-1, 1):
        hip = (side * 13.0, -46.0)
        foot = (side * 15.0 + (side * 10 if walking else 0), -10.0)
        out.append(limb([hip, ((hip[0] + foot[0]) / 2, -28.0), foot], 12, c.ghost, c.ink, W, radius=3))
        out.append(f'<circle cx="{fmt((hip[0] + foot[0]) / 2)}" cy="-28" r="4.5" fill="{joint}"/>')
        out.append(
            f'<path d="M{fmt(foot[0] - 11)} 0 V-8 Q{fmt(foot[0] - 11)} -14 {fmt(foot[0] - 4)} -14 H{fmt(foot[0] + 8)} '
            f'Q{fmt(foot[0] + 15)} -14 {fmt(foot[0] + 15)} -6 V0 Z" {st}/>'
        )
    return "".join(out)


def draw(pose: str, c: FigureColors, expression: str, sid: str, *, f_head: int = 1) -> tuple[str, dict[str, Point]]:
    back_arm, front_arm = ARMS[pose]
    anchors: dict[str, Point] = {"head": (0.0, -156.0), "top": (0.0, -194.0)}
    prop = ""
    if pose == "laptop":
        prop, kb = desk_laptop(c, 34, -78, 52, W, lid=34)
        front_arm = Arm(kb, front_arm.bend, front_arm.hand)
        anchors["screen"] = (72.0, -98.0)
    back_m = ""
    if back_arm is not None:
        back_m, bh, _ = _arm((-SHOULDER[0], SHOULDER[1]), back_arm, c)
        anchors["back_hand"] = bh
    front_m, fh, lens = _arm(SHOULDER, front_arm, c)
    anchors["hand"] = fh
    if front_arm.hand == "flashlight":
        anchors["lens"] = lens
    st = f'stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    shade = mix(c.ghost, "#8fa3c8", 0.35)
    torso = (
        f'<path d="M-30 -112 Q-34 -112 -34 -104 L-30 -54 Q-28 -44 -16 -44 H16 Q28 -44 30 -54 L34 -104 Q34 -112 30 -112 Z" '
        f'fill="{c.ghost}" {st}/>'
        f'<path d="M-26 -60 Q-24 -50 -14 -50 H14 Q24 -50 26 -60" fill="none" stroke="{shade}" stroke-width="5" stroke-linecap="round"/>'
        f'<circle cx="0" cy="-86" r="11" fill="{VISOR}" {st}/><circle cx="0" cy="-86" r="6.5" fill="{GLOW}"/>'
        f'<circle cx="0" cy="-86" r="13" fill="{GLOW}" fill-opacity="0.18"/>'
        f'<rect x="-9" y="-124" width="18" height="12" rx="3" fill="{mix(c.ghost, c.ink, 0.35)}" {st}/>'
    )
    f = f_head
    head = (
        f'<rect x="-40" y="-192" width="80" height="68" rx="30" fill="{c.ghost}" {st}/>'
        f'<circle cx="{fmt(-40)}" cy="-158" r="9" fill="{shade}" {st}/><circle cx="40" cy="-158" r="9" fill="{shade}" {st}/>'
        f'<rect x="{fmt(-31 + f * 3)}" y="-180" width="62" height="44" rx="20" fill="{VISOR}" {st}/>'
        f'<path d="M-24 -184 Q-6 -192 12 -188" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round" stroke-opacity="0.8"/>'
    )
    feats = face(
        expression, cx=f * 5.0, cy=-160.0, s=1.05, f=f, ink=GLOW, white=VISOR, cheek=GLOW, spread=11.0,
        cheeks=False, brows=expression in ("focused", "disgusted", "crying"),
    )  # fmt: skip
    glow = f'<g style="filter:drop-shadow(0 0 3px {GLOW})">{feats}</g>' if expression != "cool" else feats
    out = [shadow(40, c.ink), _legs(c, pose == "walking")]
    if pose not in CROSSED:
        out.append(back_m)
    out += [torso, head, glow]
    if pose in CROSSED:
        out.append(back_m)
    out += [prop, front_m]
    return "".join(out), anchors

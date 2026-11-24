"""The ``bean`` style: flat, outline-free rounded figures (a soft bell-shaped body, a round head, two white dot
eyes), for explainers and editorial scenes where the figure is a role, not a person. Faces right in a 120 x 100 box.
The body takes ``shirt``; held props take ``accent``."""

from __future__ import annotations

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
    reach,
    shadow,
    towel,
)
from inferno_ghostwriter.images.figures.faces import face
from inferno_ghostwriter.images.palettes import mix

VIEW_BOX = (-60.0, -100.0, 120.0, 100.0)
SHOULDER: Point = (10.0, -42.0)
UPPER, FORE = 10.0, 10.0
ARM_W = 8.5
HEAD: Point = (0.0, -76.0)
HEAD_R = 16.0

ARMS: dict[str, tuple[Arm | None, Arm]] = {
    "standing": (Arm((-20, -26), 1), Arm((20, -26), -1)),
    "pointing": (Arm((-20, -26), 1), Arm((40, -46), 1, "point")),
    "looking_back": (Arm((-20, -26), 1), Arm((19, -25), -1)),
    "nervous": (Arm((-20, -26), 1), Arm((14, -86), -1, "towel")),
    "flashlight": (Arm((-20, -26), 1), Arm((33, -46), 1, "flashlight")),
    "laptop": (Arm((-20, -26), 1), Arm((32, -38), 1)),
    "shrug": (Arm((-27, -56), 1), Arm((27, -56), -1)),
    "arms_crossed": (Arm((8, -34), -1), Arm((-7, -33), 1)),
    "nope": (Arm((-20, -26), 1), Arm((24, -74), 1, "palm")),
    "yep": (Arm((-20, -26), 1), Arm((36, -62), 1, "point", -40)),
    "walking": (Arm((-24, -32), 1), Arm((24, -34), -1)),
}

CROSSED = {"arms_crossed"}
# Bean faces stay quiet: two dots unless the pose is about a feeling.
DEFAULTS = {p: "neutral" for p in ARMS} | {
    "nervous": "nervous",
    "looking_back": "impressed",
    "nope": "disgusted",
    "yep": "happy",
    "shrug": "calm",
}
_BODY = "M-13 -58 C-6 -62 6 -62 13 -58 C19 -44 21 -20 20 -8 Q19 -1 11 -1 L-11 -1 Q-19 -1 -20 -8 C-21 -20 -19 -44 -13 -58 Z"


def _arm(shoulder: Point, arm: Arm, c: FigureColors, color: str) -> tuple[str, Point, Point]:
    hand = reach(shoulder, arm.to, UPPER, FORE)
    elbow = ik(shoulder, hand, UPPER, FORE, arm.bend)
    rot = arm.hand_rot if arm.hand_rot is not None else angle(elbow, hand)
    parts = []
    if arm.hand == "flashlight":
        parts.append(place(hand, -8, flashlight(c, 0), 0.62))
    parts.append(limb([shoulder, elbow, hand], ARM_W, color, None, 0, radius=4))
    if arm.hand == "point":
        parts.append(place(hand, rot, f'<rect x="0" y="-2.2" width="9" height="4.4" rx="2.2" fill="{color}"/>'))
    elif arm.hand == "palm":
        parts.append(place(hand, rot, f'<ellipse cx="3" cy="0" rx="6" ry="5.2" fill="{color}"/>'))
    elif arm.hand == "towel":
        parts.append(place(hand, rot, towel(c, 1.6), 0.55))
    lens = local_to_world(hand, -8, LENS, 0.62) if arm.hand == "flashlight" else hand
    return "".join(parts), hand, lens


def draw(pose: str, c: FigureColors, expression: str, sid: str, *, f_head: int = 1) -> tuple[str, dict[str, Point]]:
    back_arm, front_arm = ARMS[pose]
    anchors: dict[str, Point] = {"head": HEAD, "top": (0.0, -92.0)}
    body_c = c.shirt
    arm_c = mix(c.shirt, "#000000", 0.16)
    prop = ""
    if pose == "laptop":
        prop, kb = desk_laptop(c, 20, -38, 32, 1.6, lid=22)
        front_arm = Arm(kb, front_arm.bend, front_arm.hand)
        anchors["screen"] = (44.0, -50.0)
    back_m = ""
    if back_arm is not None:
        back_m, bh, _ = _arm((-SHOULDER[0], SHOULDER[1]), back_arm, c, arm_c)
        anchors["back_hand"] = bh
    front_m, fh, lens = _arm(SHOULDER, front_arm, c, arm_c)
    anchors["hand"] = fh
    if front_arm.hand == "flashlight":
        anchors["lens"] = lens
    walking = pose == "walking"
    tilt = ' transform="rotate(6 0 0)"' if walking else ""
    body = f'<path d="{_BODY}" fill="{body_c}"/>'
    head = f'<circle cx="{fmt(HEAD[0])}" cy="{fmt(HEAD[1])}" r="{fmt(HEAD_R)}" fill="{body_c}"/>'
    f = f_head
    feats = face(
        expression, cx=f * 4.5, cy=-77.0, s=0.62, f=f, ink="#ffffff", white=body_c, spread=8.0, mouth=False, brows=False, simple=True
    )
    trail = ""
    if walking:
        trail = (
            '<path d="M-44 -40 H-30 M-48 -26 H-32 M-42 -54 H-32" stroke="#9a96a6" stroke-width="2.2" '
            'stroke-linecap="round" stroke-opacity="0.6"/>'
        )
    if walking:
        anchors = {k: local_to_world((0.0, 0.0), 6, v) for k, v in anchors.items()}
    figure = [back_m if pose not in CROSSED else "", body, head, feats, back_m if pose in CROSSED else "", front_m]
    return shadow(24, c.ink) + trail + prop + f"<g{tilt}>{''.join(figure)}</g>", anchors

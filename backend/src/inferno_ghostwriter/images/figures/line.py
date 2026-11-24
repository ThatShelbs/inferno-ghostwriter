"""The ``line`` style: clean line-art people with expressive faces, for meme re-creations.

About four heads tall, a 2.8-unit ink outline on every shape, flat fills. The figure faces right in a 200 x 205 box
with its feet on y = 0.
"""

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

VIEW_BOX = (-100.0, -205.0, 200.0, 205.0)
OUTFITS = ("tee", "plaid", "dress", "hoodie", "jacket")
HAIRS = ("short", "long", "messy", "bun", "bald")

W = 2.8  # outline weight
HEAD: Point = (0.0, -160.0)
HEAD_RX, HEAD_RY = 22.0, 25.0
SHOULDER_Y = -121.0
SHOULDER_X = 21.0
UPPER, FORE = 27.0, 26.0
ARM_W = 11.0

# Hand targets per pose: (back arm, front arm). ``None`` hides the back arm behind the body.
ARMS: dict[str, tuple[Arm | None, Arm]] = {
    "standing": (Arm((-28, -70), elbow=(-27, -96)), Arm((28, -70), elbow=(27, -96))),
    "pointing": (Arm((-28, -70), elbow=(-27, -96)), Arm((72, -127), 1, "point")),
    "looking_back": (Arm((-28, -70), elbow=(-27, -96)), Arm((27, -70), elbow=(27, -96))),
    # The cloth dabs the upper corner of the forehead with the elbow out, so the worried face stays in view.
    "nervous": (Arm((-28, -70), elbow=(-27, -96)), Arm((24, -180), -1, "towel", elbow=(40, -146))),
    "flashlight": (Arm((-28, -70), elbow=(-27, -96)), Arm((56, -106), 1, "flashlight")),
    "laptop": (None, Arm((52, -101), 1, "fist", 10)),
    "shrug": (
        Arm((-50, -110), hand="palm", hand_rot=-165, elbow=(-32, -98)),
        Arm((50, -110), hand="palm", hand_rot=-15, elbow=(32, -98)),
    ),
    "arms_crossed": (Arm((15, -104), elbow=(-28, -97)), Arm((-15, -100), elbow=(28, -95))),
    "nope": (Arm((-28, -70), elbow=(-27, -96)), Arm((46, -140), hand="palm", hand_rot=-95, elbow=(40, -106))),
    "yep": (Arm((-28, -70), elbow=(-27, -96)), Arm((60, -150), 1, "point", -40)),
    "walking": (Arm((-39, -76), elbow=(-27, -97)), Arm((37, -75), elbow=(27, -97))),
}

STRIDE = {"walking"}
CROSSED = {"arms_crossed"}


def _sleeve(outfit: str) -> float:
    """How far down the arm the sleeve runs (0-1 of the arm)."""
    return {"tee": 0.33, "dress": 0.0}.get(outfit, 1.0)


def _cloth(c: FigureColors, outfit: str, sid: str) -> str:
    return f"url(#{sid}-plaid)" if outfit == "plaid" else c.shirt


def _defs(c: FigureColors, outfit: str, sid: str) -> str:
    if outfit != "plaid":
        return ""
    return (
        f'<defs><pattern id="{sid}-plaid" patternUnits="userSpaceOnUse" width="14" height="14">'
        f'<rect width="14" height="14" fill="{c.shirt}"/>'
        f'<rect y="5" width="14" height="4" fill="{c.plaid}" fill-opacity="0.45"/>'
        f'<rect x="5" width="4" height="14" fill="{c.plaid}" fill-opacity="0.45"/>'
        f'<path d="M0 12.5 H14 M12.5 0 V14" stroke="#ffffff" stroke-opacity="0.45" stroke-width="1"/>'
        "</pattern></defs>"
    )


def _hand(kind: str, at: Point, rot: float, c: FigureColors) -> str:
    sk = f'fill="{c.skin}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    thin = f'fill="{c.skin}" stroke="{c.ink}" stroke-width="{fmt(W * 0.7)}" stroke-linejoin="round"'
    fist = f'<ellipse cx="2" cy="0" rx="7.6" ry="7" {sk}/>'
    if kind == "point":
        body = f'<rect x="2" y="-6" width="18" height="6.4" rx="3.2" {sk}/>{fist}'
    elif kind == "palm":
        fingers = "".join(
            f'<rect x="6" y="{fmt(y - 1.9)}" width="{fmt(n)}" height="3.8" rx="1.9" {thin}/>'
            for y, n in ((-5.4, 12.5), (-1.8, 14), (1.8, 13), (5.2, 10.5))
        )
        body = (
            f"{fingers}"
            f'<rect x="-3" y="-7.6" width="13" height="15.2" rx="5.5" {sk}/>'
            f'<rect x="-1" y="-13" width="10" height="4.4" rx="2.2" transform="rotate(-28 4 -10)" {thin}/>'
        )
    else:
        body = fist
    return place(at, rot, body)


def _arm(shoulder: Point, arm: Arm, c: FigureColors, outfit: str, sid: str) -> tuple[str, Point, Point]:
    if arm.elbow is not None:
        hand, elbow = arm.to, arm.elbow
    else:
        hand = reach(shoulder, arm.to, UPPER, FORE)
        elbow = ik(shoulder, hand, UPPER, FORE, arm.bend)
    rot = arm.hand_rot if arm.hand_rot is not None else angle(elbow, hand)
    sleeve = _sleeve(outfit)
    cloth = _cloth(c, outfit, sid)
    parts: list[str] = []
    if arm.hand == "flashlight":
        parts.append(place(hand, -8, flashlight(c, W * 0.7), 1.3))
    if sleeve < 1:
        parts.append(limb([shoulder, elbow, hand], ARM_W - 1.5, c.skin, c.ink, W))
    if sleeve > 0:
        if sleeve < 1:
            end = (shoulder[0] + (elbow[0] - shoulder[0]) * sleeve * 2, shoulder[1] + (elbow[1] - shoulder[1]) * sleeve * 2)
            parts.append(limb([shoulder, end], ARM_W + 3, cloth, c.ink, W))
        else:
            parts.append(limb([shoulder, elbow, hand], ARM_W + 1, cloth, c.ink, W))
    hand_kind = "fist" if arm.hand in ("flashlight", "towel") else arm.hand
    parts.append(_hand(hand_kind, hand, rot if arm.hand != "flashlight" else -8, c))
    if arm.hand == "towel":
        parts.append(place(hand, rot, towel(c, W * 0.85)))
    lens = local_to_world(hand, -8, LENS, 1.3) if arm.hand == "flashlight" else hand
    return "".join(parts), hand, lens


def _legs(pose: str, c: FigureColors, outfit: str) -> str:
    stride = pose in STRIDE
    if stride:
        back = [(-7.0, -72.0), (-13.0, -40.0), (-24.0, -9.0)]
        front = [(7.0, -72.0), (16.0, -42.0), (21.0, -9.0)]
    else:
        back = [(-10.0, -72.0), (-12.0, -9.0)]
        front = [(10.0, -72.0), (12.0, -9.0)]
    if outfit == "dress":
        back[0] = (back[0][0], -52.0)
        front[0] = (front[0][0], -52.0)
        legs = limb(back, 10, c.skin, c.ink, W) + limb(front, 10, c.skin, c.ink, W)
    else:
        legs = limb(back, 17, c.pants, c.ink, W, radius=10) + limb(front, 17, c.pants, c.ink, W, radius=10)
    shoes = "".join(_shoe(p[-1][0], c) for p in (back, front))
    pelvis = ""
    if outfit != "dress":
        pelvis = f'<rect x="-22" y="-84" width="44" height="22" rx="8" fill="{c.pants}" stroke="{c.ink}" stroke-width="{fmt(W)}"/>'
    return legs + pelvis + shoes


def _shoe(x: float, c: FigureColors) -> str:
    y = -W / 2
    return (
        f'<path d="M{fmt(x - 8)} {fmt(y)} L{fmt(x + 12)} {fmt(y)} Q{fmt(x + 14)} {fmt(y - 8)} {fmt(x + 4)} {fmt(y - 10)} '
        f'L{fmt(x - 6)} {fmt(y - 10)} Q{fmt(x - 9)} {fmt(y - 9)} {fmt(x - 8)} {fmt(y)} Z" fill="{c.shoes}" stroke="{c.ink}" '
        f'stroke-width="{fmt(W)}" stroke-linejoin="round"/>'
    )


def _torso(c: FigureColors, outfit: str, sid: str) -> str:
    cloth = _cloth(c, outfit, sid)
    st = f'stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    if outfit == "dress":
        body = (
            f'<path d="M-9 -134 C-17 -133 -21 -128 -20 -118 L-17 -92 Q-17 -86 -20 -80 L-34 -46 Q0 -40 34 -46 L20 -80 '
            f'Q17 -86 17 -92 L20 -118 C21 -128 17 -133 9 -134 Q0 -126 -9 -134 Z" fill="{cloth}" {st}/>'
            f'<path d="M-17 -90 Q0 -86 17 -90" fill="none" stroke="{c.ink}" stroke-width="1.6" stroke-opacity="0.5"/>'
        )
        return body
    body = (
        f'<path d="M-9 -134 C-21 -133 -28 -127 -28 -114 L-25 -78 Q-24 -69 -15 -69 L15 -69 Q24 -69 25 -78 L28 -114 '
        f'C28 -127 21 -133 9 -134 Z" fill="{cloth}" {st}/>'
    )
    if outfit == "tee":
        body += f'<path d="M-9 -134 Q0 -126 9 -134" fill="{c.skin}" {st}/>'
    elif outfit == "plaid":
        body += (
            f'<path d="M-10 -134 L0 -122 L10 -134" fill="none" {st}/>'
            f'<path d="M0 -122 V-72" stroke="{c.ink}" stroke-width="1.6" stroke-opacity="0.6"/>'
            f'<path d="M-9 -134 L0 -122 L9 -134 Q0 -130 -9 -134 Z" fill="#ffffff" {st}/>'
        )
    elif outfit == "hoodie":
        body += (
            f'<path d="M-15 -96 L15 -96 L18 -78 L-18 -78 Z" fill="none" stroke="{c.ink}" stroke-width="1.8" stroke-opacity="0.55"/>'
            f'<path d="M-4 -131 L-5 -112 M4 -131 L5 -112" stroke="{c.ink}" stroke-width="1.8" stroke-linecap="round"/>'
        )
    elif outfit == "jacket":
        body += (
            f'<path d="M-26 -110 Q0 -104 26 -110 M-25 -95 Q0 -89 25 -95 M-25 -81 Q0 -76 25 -81" fill="none" '
            f'stroke="{c.ink}" stroke-width="1.8" stroke-opacity="0.5"/>'
            f'<path d="M-13 -138 Q0 -128 13 -138 L15 -128 Q0 -118 -15 -128 Z" fill="{cloth}" {st}/>'
        )
    return body


def _hair_back(hair: str, c: FigureColors) -> str:
    if hair != "long":
        return ""
    return (
        f'<path d="M-23 -168 C-26 -192 20 -196 25 -170 L27 -136 Q22 -127 12 -128 L-14 -128 Q-27 -128 -29 -140 Z" '
        f'fill="{c.hair}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"/>'
    )


def _hair_front(hair: str, c: FigureColors) -> str:
    st = f'fill="{c.hair}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    if hair == "bald":
        return (
            f'<path d="M-12 -178 Q-4 -181 4 -178 M-9 -173 Q-2 -175 5 -173" fill="none" stroke="{c.ink}" stroke-width="1.4" '
            'stroke-opacity="0.45" stroke-linecap="round"/>'
        )
    if hair == "messy":
        return (
            f'<path d="M-23 -156 C-28 -170 -24 -182 -18 -186 L-19 -195 L-10 -189 L-6 -199 L0 -190 L6 -199 L10 -189 '
            f'L19 -194 L18 -184 L26 -182 C25 -173 22 -168 18 -167 C10 -171 -2 -170 -10 -167 C-15 -164 -18 -160 -23 -156 Z" {st}/>'
        )
    if hair == "bun":
        return (
            f'<circle cx="-14" cy="-187" r="8.5" {st}/>'
            f'<path d="M-23 -156 C-27 -176 -12 -188 4 -187 C17 -186 25 -177 23 -165 C14 -172 2 -172 -8 -168 '
            f'C-14 -166 -18 -161 -23 -156 Z" {st}/>'
        )
    if hair == "long":
        return (
            f'<path d="M-23 -150 C-28 -176 -12 -189 4 -188 C17 -187 25 -177 23 -163 C15 -172 3 -173 -6 -169 '
            f'C-13 -166 -17 -158 -23 -150 Z" {st}/>'
        )
    # short
    return (
        f'<path d="M-23 -156 C-27 -177 -12 -189 4 -188 C17 -187 25 -177 23 -166 C17 -169 10 -170 4 -168 L6 -173 '
        f'C-2 -169 -10 -168 -15 -164 C-18 -161 -20 -158 -23 -156 Z" {st}/>'
    )


def _hood(c: FigureColors, sid: str, front: bool) -> str:
    cloth = _cloth(c, "hoodie", sid)
    st = f'fill="{cloth}" stroke="{c.ink}" stroke-width="{fmt(W)}" stroke-linejoin="round"'
    if not front:
        return f'<path d="M-30 -132 C-38 -170 -22 -197 2 -196 C24 -195 34 -176 30 -148 L24 -132 Z" {st}/>'
    return (
        f'<path d="M-28 -136 C-33 -170 -16 -194 4 -193 C23 -192 30 -178 28 -160 C25 -174 14 -181 0 -181 '
        f'C-14 -180 -21 -168 -20 -150 C-20 -144 -22 -139 -28 -136 Z" {st}/>'
    )


def _head(c: FigureColors, f: int, hair: str, outfit: str, expression: str, sid: str) -> str:
    hood = outfit == "hoodie"
    head = (
        f'<path d="M0 -185 C14 -185 22 -175 22 -160 C22 -145 13 -135 1 -135 C-12 -135 -22 -145 -22 -160 C-22 -175 -14 -185 0 -185 Z" '
        f'fill="{c.skin}" stroke="{c.ink}" stroke-width="{fmt(W)}"/>'
    )
    ear = f'<ellipse cx="-20" cy="-157" rx="5.2" ry="6.6" fill="{c.skin}" stroke="{c.ink}" stroke-width="{fmt(W)}"/>'
    back = _hood(c, sid, False) if hood else _hair_back(hair, c)
    top = _hood(c, sid, True) if hood else _hair_front(hair, c)
    mirror = ' transform="scale(-1 1)"' if f < 0 else ""
    feats = face(expression, cx=f * 5.0, cy=-156.5, s=1.0, f=f, ink=c.ink, cheek=c.cheek, spread=8.2, nose=True)
    return f"<g{mirror}>{back}{ear if not hood else ''}{head}{top}</g>{feats}"


def draw(
    pose: str, c: FigureColors, expression: str, sid: str, *, outfit: str = "tee", hair: str = "short", f_head: int = 1
) -> tuple[str, dict[str, Point]]:
    back_arm, front_arm = ARMS[pose]
    sb: Point = (-SHOULDER_X, SHOULDER_Y)
    sf: Point = (SHOULDER_X, SHOULDER_Y)
    anchors: dict[str, Point] = {"head": HEAD, "top": (0.0, -190.0)}
    out = [_defs(c, outfit, sid), shadow(34, c.ink)]
    prop = ""
    if pose == "laptop":
        prop, kb = desk_laptop(c, 28, -98, 64, W)
        front_arm = Arm(kb, front_arm.bend, front_arm.hand, front_arm.hand_rot)
        anchors["screen"] = (78.0, -120.0)
    back_markup = ""
    if back_arm is not None:
        back_markup, bh, _ = _arm(sb, back_arm, c, outfit, sid)
        anchors["back_hand"] = bh
    front_markup, fh, lens = _arm(sf, front_arm, c, outfit, sid)
    anchors["hand"] = fh
    if front_arm.hand == "flashlight":
        anchors["lens"] = lens
    out.append(_legs(pose, c, outfit))
    if pose not in CROSSED:
        out.append(back_markup)
    out.append(f'<rect x="-6" y="-142" width="12" height="13" fill="{c.skin}" stroke="{c.ink}" stroke-width="{fmt(W)}"/>')
    out.append(_torso(c, outfit, sid))
    out.append(_head(c, f_head, hair, outfit, expression, sid))
    if pose in CROSSED:
        out.append(back_markup)
    out.append(prop)
    out.append(front_markup)
    return "".join(out), anchors

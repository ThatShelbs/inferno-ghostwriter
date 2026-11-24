"""Code-staged meme formats: the famous layouts drawn faithfully, every time, with our own cast.

A staging fixes what makes a format recognizable (panels, camera framing, who stands where, each beat's pose and
expression, the setting and props). Claude only casts the roles (which of our characters plays each one) and writes
the words. So "Right? Right?" is always the two-shot in the meadow, then the hopeful close-up, then the blank stare,
then the frozen smile, and This is fine is always our dog in a hat at the table in a burning room.

Comics use the same machinery from Claude's per-panel choices (``PanelPick``): characters, expressions, poses and a
backdrop from the kit's catalog, never freehand art.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from inferno_ghostwriter.images.figures import FigureColors
from inferno_ghostwriter.images.figures.base import fmt as num
from inferno_ghostwriter.images.figures.base import limb
from inferno_ghostwriter.images.figures.line import W as LINE_W
from inferno_ghostwriter.images.kit import props as kp
from inferno_ghostwriter.images.kit.props import Stage
from inferno_ghostwriter.images.memes.cast import ACCESSORIES, EXPRESSIONS, POSES, PROPS, Character, colors_for, draw, kind_of
from inferno_ghostwriter.images.memes.formats import Box, MemeFormat

# One cast pick per role: kind plus optional expression / accessory overrides (validated).
Cast = dict[str, dict[str, str]]


@dataclass(frozen=True)
class CastRole:
    name: str
    default: str  # kind
    hint: str
    accessory: str = "none"


def _pick(cast: Cast, role: str, default: str) -> dict[str, str]:
    raw = cast.get(role) or {}
    # People play every role, as in the original meme; the ghost or robot only when cast on purpose.
    kind = kind_of(raw.get("kind"))
    out: dict[str, str] = {"kind": kind}
    if raw.get("expression") in EXPRESSIONS:
        out["expression"] = raw["expression"]
    if raw.get("accessory") in ACCESSORIES:
        out["accessory"] = raw["accessory"]
    return out


def ch(
    cast: Cast,
    role: str,
    default: str,
    expression: str,
    pose: str = "stand",
    facing: str = "right",
    accessory: str = "none",
    prop: str = "none",
    variant: int = 0,
    *,
    fixed_expression: bool = True,
) -> Character:
    """A cast member for one beat. The beat's expression is fixed (it is the joke) unless ``fixed_expression`` is
    False; an accessory the author or Claude picked replaces the beat's default."""
    pick = _pick(cast, role, default)
    expr = expression if fixed_expression else pick.get("expression", expression)
    return Character(pick["kind"], expr, pose, facing, pick.get("accessory", accessory), prop, variant, label=role)


def clip(box: Box, body: str, cid: str) -> str:
    x, y, w, h = box
    return f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath><g clip-path="url(#{cid})">{body}</g>'


def _panels_of(fmt: MemeFormat) -> list[Box]:
    from inferno_ghostwriter.images.memes.formats import _panels

    w, h = fmt.size
    if fmt.id in ("right_right", "comic_grid_4"):
        return _panels(w, h, 2, 2, 18)
    if fmt.id in ("comic_strip_3", "shocked_strip"):
        return _panels(w, h, 3, 1, 18)
    if fmt.id == "this_is_fine_2":
        return _panels(w, h, 2, 1, 18)
    return [(0, 0, w, h)]


# -- the classics ------------------------------------------------------------------------------------------------------


def right_right(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    p1, p2, p3, p4 = _panels_of(fmt)
    out = []
    # The confident one (left) and the hopeful one (right). Close-ups crop the character big, from the chest up.
    for i, (box, shots) in enumerate(
        (
            (
                p1,
                [
                    ("confident", "ghost", "smug", "stand", "right", 0.25, 1.0, 0.7, 0),
                    ("hopeful", "ghost", "beaming", "stand", "left", 0.75, 1.0, 0.7, 1),
                ],
            ),
            (p2, [("hopeful", "ghost", "hopeful", "stand", "left", 0.5, 1.42, 1.18, 1)]),
            (p3, [("confident", "ghost", "blank", "stand", "right", 0.5, 1.42, 1.18, 0)]),
            # The punchline: still smiling, but the eyes have understood.
            (p4, [("hopeful", "ghost", "frozen_smile", "stand", "left", 0.5, 1.42, 1.18, 1)]),
        )
    ):
        x, y, w, h = box
        body = [kp.meadow(st, box, horizon=0.66 if i == 0 else 0.8)]
        for role, kind, expr, pose, facing, fx, fy, fh, variant in shots:
            # The hopeful one wears a bow by default, so the two read as two people at a glance in every panel.
            c = ch(cast, role, kind, expr, pose, facing, accessory="bow" if role == "hopeful" else "none", variant=variant)
            body.append(draw(c, x + w * fx, y + h * fy, h * fh, sch=st.sch, look=st.look).svg)
        out.append(clip(box, "".join(body), f"{st.prefix}-rr{i}"))
    return "".join(out)


def this_is_fine(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.burning_room(st, box)]
    tx = w * 0.66
    # The golden pup (variant 1) reads like the original and stands out from the cream wall.
    dog = ch(cast, "calm_one", "dog", "content", "sit_hold", "left", accessory="bowler", prop="mug", variant=1)
    body.append(draw(dog, tx + 60, h * 0.86, h * 0.58, sch=st.sch, look=st.look).svg)
    if "burning_room" not in st.settings:  # the painted room has its own table, chair, mug and fire
        body.append(kp.table(st, tx - 110, h * 0.68, 230, h * 0.2))
        body.append(kp.flame(w * 0.5, h * 0.84, 90, 120, "#ed6925"))
    return clip(box, "".join(body), f"{st.prefix}-tif")


def this_is_fine_2(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    a, b = _panels_of(fmt)
    out = []
    x, y, w, h = a
    body = [kp.burning_room(st, a)]
    body.append(kp.chair(st, x + w * 0.66, y + h * 0.7))
    dog = ch(cast, "calm_one", "dog", "content", "sit_hold", "left", accessory="bowler", prop="mug", variant=1)
    body.append(draw(dog, x + w * 0.62, y + h * 0.82, h * 0.48, sch=st.sch, look=st.look).svg)
    body.append(kp.table(st, x + w * 0.34, y + h * 0.66, w * 0.34, h * 0.2))
    out.append(clip(a, "".join(body), f"{st.prefix}-tf1"))
    x, y, w, h = b
    body = [kp.burning_room(st, b, intensity=0.8)]
    dog = ch(cast, "calm_one", "dog", "content", "sit_hold", "left", accessory="bowler", prop="mug", variant=1)
    body.append(draw(dog, x + w * 0.55, y + h * 1.45, h * 1.25, sch=st.sch, look=st.look).svg)
    out.append(clip(b, "".join(body), f"{st.prefix}-tf2"))
    return "".join(out)


def expanding_brain(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    return "".join(kp.head_profile(st, (540, i * 330, 540, 330), i + 1) for i in range(4))


def nope_yep(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    yellow = "#fbd34a"
    out = []
    for i, (expr, pose, facing) in enumerate((("nope", "block_back", "left"), ("smug", "point", "right"))):
        box = (0, i * 540, 540, 540)
        body = [kp.wash(st, box, kp.gradient_rect(st, box, mix_hex(yellow, "#ffffff", 0.2), yellow))]
        c = ch(cast, "chooser", "ghost", expr, pose, facing, accessory="jacket")
        # Turned away (hand up toward the text on the right), then facing the text and pointing at it.
        body.append(draw(c, 250 if facing == "left" else 230, i * 540 + 600, 580, sch=st.sch, look=st.look).svg)
        out.append(clip(box, "".join(body), f"{st.prefix}-ny{i}"))
    return "".join(out)


def mix_hex(a: str, b: str, t: float) -> str:
    from inferno_ghostwriter.images.palettes import mix

    return mix(a, b, t)


def pointing_twins(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.basement(st, box)]
    for fx, facing in ((0.3, "right"), (0.7, "left")):
        c = ch(cast, "twin", "ghost", "shocked", "point", facing, accessory="scarf")
        body.append(draw(c, w * fx, h * 0.88, h * 0.56, sch=st.sch, look=st.look).svg)
    return clip(box, "".join(body), f"{st.prefix}-pt")


def distracted(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.street(st, box)]
    body.append(
        draw(
            ch(cast, "shiny", "ghost", "beaming", "wave", "right", variant=2),
            w * 0.17,
            h * 0.93,
            h * 0.6,
            sch=st.sch,
            look=st.look,
        ).svg
    )
    body.append(
        draw(ch(cast, "partner", "ghost", "grumpy", "proud", "left", variant=1), w * 0.82, h * 0.93, h * 0.6, sch=st.sch, look=st.look).svg
    )
    body.append(draw(ch(cast, "distracted", "ghost", "love", "point", "left"), w * 0.53, h * 0.95, h * 0.64, sch=st.sch, look=st.look).svg)
    return clip(box, "".join(body), f"{st.prefix}-ds")


def two_buttons(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    top = (0, 0, 1080, 700)
    panel = "#6f7d93"
    out = [kp.wash(st, top, kp.gradient_rect(st, top, "#8a97ab", panel))]
    out.append(kp.big_button(st, 300, 305))
    out.append(kp.big_button(st, 780, 275))
    c = ch(cast, "chooser", "person", "sweating", "wipe")
    # The man in blue is his own look (a person cast as the chooser); a ghost or robot keeps its own colors.
    man = Character(
        c.kind, "sweating", "wipe", "left", c.accessory, "none", c.variant, "sweater" if kind_of(c.kind) == "person" else c.label
    )
    out.append(clip(top, _reaching_hand(colors_for(man, st.sch), kind_of(c.kind)), f"{st.prefix}-tbh"))
    bottom = (0, 700, 1080, 600)
    body = [kp.wash(st, bottom, kp.gradient_rect(st, bottom, "#fde2b8", "#f7c98a"))]
    # Chest up, a little off centre, facing left so the cloth hand is on the far side and his worried face reads.
    body.append(draw(man, 560, 700 + 1080, 1060, sch=st.sch, look=st.look).svg)
    out.append(clip(bottom, "".join(body), f"{st.prefix}-tbs"))
    return "".join(out)


def _reaching_hand(colors: FigureColors, kind: str) -> str:
    """The Two Buttons hand reaching up from the bottom edge, finger hovering between the buttons, drawn in figure
    units at the same scale and in the same colors as the sweating man below, so the arm is visibly his."""
    s = 1060 / 205  # the bottom panel's figure scale
    ink, w = colors.ink, LINE_W
    skin = colors.skin if kind == "person" else (colors.ghost if kind == "ghost" else "#eef0f6")
    sleeve = colors.shirt if kind == "person" else skin
    # Local units: x = 0 at the hand, y up is negative; the arm enters from the bottom edge (y ~ +44 at 700 px).
    arm = [(10.0, 50.0), (6.0, 24.0), (0.0, 0.0)]
    parts = [limb(arm, 10.5, skin, ink, w)]
    if kind == "person":
        parts.append(limb([(10.0, 50.0), (8.6, 40.0)], 14, sleeve, ink, w))  # the blue cuff at the frame edge
    st_ = f'stroke="{ink}" stroke-width="{num(w)}" stroke-linejoin="round"'
    parts.append(f'<rect x="-3.2" y="-22" width="6.4" height="18" rx="3.2" fill="{skin}" {st_}/>')  # the finger
    parts.append(f'<ellipse cx="0" cy="-2" rx="7.8" ry="8.4" fill="{skin}" {st_}/>')  # the fist
    parts.append(f'<path d="M-6 -4 Q-1 -1 5 -4" fill="none" stroke="{ink}" stroke-width="1.2" stroke-opacity="0.5"/>')
    hand = f'<g transform="translate(548 470) scale({num(s)})">{"".join(parts)}</g>'
    drops = "".join(
        f'<path d="M{dx},{dy} c8,12 9,22 0,25 c-9,-3 -8,-13 0,-25 z" fill="#9bd8ff" stroke="#3a86c8" stroke-width="2"/>'
        for dx, dy in ((470, 430), (626, 420), (500, 520))
    )
    return hand + drops


def midwit(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    out = []
    for role, expr, pose, acc, (x, y, w, h), variant in (
        ("beginner", "beaming", "wave", "none", (60, 440, 280, 300), 0),
        ("midwit", "panic", "facepalm", "glasses", (540, 280, 320, 300), 1),
        ("expert", "calm", "stand", "hood", (1060, 440, 280, 300), 2),
    ):
        out.append(
            draw(
                ch(cast, role, "ghost", expr, pose, accessory=acc, variant=variant), x + w / 2, y + h, h * 0.95, sch=st.sch, look=st.look
            ).svg
        )
    return "".join(out)


def gru_plan(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    from inferno_ghostwriter.images.memes.formats import _panels

    out = []
    for i, (x, y, _w, h) in enumerate(_panels(1200, 900, 2, 2, 12)):
        expr, pose = (("determined", "point"), ("beaming", "point"), ("smug", "point"), ("shocked", "stand"))[i]
        out.append(
            draw(
                ch(cast, "planner", "ghost", expr, pose, "right", accessory="none"), x + 135, y + h - 30, h * 0.78, sch=st.sch, look=st.look
            ).svg
        )
    return "".join(out)


def always_has_been(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.space(st, box)]
    body.append(kp.planet(st, 290, h + 120, 380))
    body.append(
        draw(
            ch(cast, "realizer", "ghost", "shocked", "float", "left", accessory="astronaut"),
            w * 0.64,
            h * 0.97,
            h * 0.42,
            sch=st.sch,
            look=st.look,
        ).svg
    )
    body.append(
        draw(
            ch(cast, "knower", "ghost", "deadpan", "point", "left", accessory="astronaut", variant=1),
            w * 0.86,
            h * 0.84,
            h * 0.42,
            sch=st.sch,
            look=st.look,
        ).svg
    )
    return clip(box, "".join(body), f"{st.prefix}-ahb")


def change_my_mind(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.meadow(st, box, horizon=0.5)]
    body.append(draw(ch(cast, "debater", "ghost", "smug", "sit_hold", "right", prop="mug"), 610, 560, 380, sch=st.sch, look=st.look).svg)
    body.append(kp.folding_table(st, 610, 440, 620))
    body.append(kp.sign_board(st, (340, 470, 540, 220)))
    return clip(box, "".join(body), f"{st.prefix}-cmm")


def is_this_a(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    body = [kp.garden(st, box)]
    body.append(
        draw(
            ch(cast, "misjudger", "ghost", "hopeful", "present", "right", accessory="glasses"),
            270,
            h * 0.82,
            h * 0.6,
            sch=st.sch,
            look=st.look,
        ).svg
    )
    body.append(kp.butterfly(st, 950, 330, 110))
    return clip(box, "".join(body), f"{st.prefix}-ita")


def shocked_strip(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    a, b, c3 = _panels_of(fmt)
    out = []
    x, y, w, h = a
    body = [
        kp.office(st, a),
        draw(ch(cast, "decider", "ghost", "beaming", "proud"), x + w * 0.5, y + h * 0.98, h * 0.62, sch=st.sch, look=st.look).svg,
    ]
    out.append(clip(a, "".join(body), f"{st.prefix}-ss1"))
    x, y, w, h = b
    body = [
        kp.office(st, b),
        kp.screen(st, (x + w * 0.08, y + h * 0.45, w * 0.38, h * 0.28), "down"),
        kp.object_(st, "fire", (x + w * 0.1, y + h * 0.78, 90, 80)),
    ]
    body.append(draw(ch(cast, "decider", "ghost", "happy", "sit_type"), x + w * 0.68, y + h * 0.98, h * 0.58, sch=st.sch, look=st.look).svg)
    out.append(clip(b, "".join(body), f"{st.prefix}-ss2"))
    x, y, w, h = c3
    body = [
        kp.plain(st, c3, tone=0.35),
        draw(ch(cast, "decider", "ghost", "shocked", "stand"), x + w * 0.5, y + h * 1.55, h * 1.4, sch=st.sch, look=st.look).svg,
    ]
    out.append(clip(c3, "".join(body), f"{st.prefix}-ss3"))
    return "".join(out)


def classic_caption(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    box = (0, 0, w, h)
    star = _pick(cast, "star", "ghost")
    c = Character(star["kind"], star.get("expression", "deadpan"), "stand", "right", star.get("accessory", "none"))
    body = [kp.plain(st, box, tone=0.25), draw(c, w / 2, h * 0.84, h * 0.6, sch=st.sch, look=st.look).svg]
    return clip(box, "".join(body), f"{st.prefix}-cc")


def panik_kalm_panik(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    out = []
    for i, expr in enumerate(("panic", "calm", "panic")):
        box = (540, i * 360, 540, 360)
        x, y, w, h = box
        body = [kp.plain(st, box, tone=0.15 if i != 1 else 0.0)]
        body.append(
            draw(
                ch(cast, "reactor", "ghost", expr, "arms_up" if expr == "panic" else "stand"),
                x + w / 2,
                y + h * 1.32,  # low enough that the tail's tip is below the frame, not a stray mark at its edge
                h * 1.15,
                sch=st.sch,
                look=st.look,
            ).svg
        )
        out.append(clip(box, "".join(body), f"{st.prefix}-pkp{i}"))
    return "".join(out)


def running_away_balloon(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage) -> str:
    w, h = fmt.size
    a = (0, 0, w // 2 - 9, h)
    b = (w // 2 + 9, 0, w // 2 - 9, h)
    out = []
    x, y, pw, ph = a
    body = [kp.meadow(st, a, horizon=0.7), kp.object_(st, "balloon", (x + pw * 0.62, y + ph * 0.05, 140, 300))]
    body.append(
        draw(
            ch(cast, "chaser", "ghost", "hopeful", "reach", "right"), x + pw * 0.32, y + ph * 0.95, ph * 0.55, sch=st.sch, look=st.look
        ).svg
    )
    out.append(clip(a, "".join(body), f"{st.prefix}-rb1"))
    x, y, pw, ph = b
    body = [kp.meadow(st, b, horizon=0.7), kp.object_(st, "balloon", (x + pw * 0.75, y - ph * 0.05, 120, 260))]
    body.append(
        draw(ch(cast, "chaser", "ghost", "sad", "reach", "right"), x + pw * 0.48, y + ph * 0.95, ph * 0.55, sch=st.sch, look=st.look).svg
    )
    body.append(
        draw(
            ch(cast, "holder", "ghost", "determined", "hold_both", "right", variant=1),
            x + pw * 0.22,
            y + ph * 0.95,
            ph * 0.55,
            sch=st.sch,
            look=st.look,
        ).svg
    )
    out.append(clip(b, "".join(body), f"{st.prefix}-rb2"))
    return "".join(out)


# -- comics: drawn from Claude's per-panel picks -------------------------------------------------------------------------

POSITIONS = {"left": 0.26, "center": 0.5, "right": 0.74, "far_left": 0.16, "far_right": 0.84}


def _id(value: object, allowed: object, default: str) -> str:
    """A catalog id from Claude's pick, or the default when it is not one."""
    return value if isinstance(value, str) and value in allowed else default  # type: ignore[operator]


def comic(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage, panels: list[dict] | None = None) -> str:
    out = []
    picks = panels or []
    for i, box in enumerate(_panels_of(fmt)):
        x, y, w, h = box
        pick = picks[i] if i < len(picks) and isinstance(picks[i], dict) else {}
        backdrop = _id(pick.get("backdrop"), kp.BACKDROPS, "office")
        fn = kp.BACKDROPS[backdrop]
        body = [fn(st, box)]
        for prop in (pick.get("props") or [])[:2]:
            name = prop.get("name", "") if isinstance(prop, dict) else ""
            if name in kp.PROP_HINTS:
                px = POSITIONS.get(prop.get("position", "center"), 0.5)
                body.append(kp.object_(st, name, (x + w * px - w * 0.14, y + h * 0.6, w * 0.28, h * 0.32)))
        chars = [c for c in (pick.get("characters") or []) if isinstance(c, dict)][:3] or [
            {"kind": "robot" if st.look == "inferno_robots" else "ghost", "expression": "happy"}
        ]
        close = pick.get("shot") == "close_up" and len(chars) == 1
        for k, c in enumerate(chars):
            kind = kind_of(c.get("kind"), "ghost")
            role = c.get("role") or kind
            # The same role keeps the same variant in every panel, so a character looks the same throughout.
            variant = int(c.get("variant", 0)) if str(c.get("variant", "0")).isdigit() else 0
            default_pos = ("left", "right", "center")[k] if len(chars) > 1 else "center"
            pos = POSITIONS.get(c.get("position", default_pos), 0.5)
            facing = _id(c.get("facing"), ("left", "right"), "right" if pos < 0.5 else "left")
            character = Character(
                kind,
                _id(c.get("expression"), EXPRESSIONS, "happy"),
                _id(c.get("pose"), POSES, "stand"),
                facing,
                _id(c.get("accessory"), ACCESSORIES, "none"),
                _id(c.get("prop"), PROPS, "none"),
                variant,
                str(role),
            )
            if close:
                body.append(draw(character, x + w * 0.5, y + h * 1.42, h * 1.18, sch=st.sch, look=st.look).svg)
            else:
                body.append(draw(character, x + w * pos, y + h * 0.97, h * (0.6 if len(chars) > 1 else 0.64), sch=st.sch, look=st.look).svg)
        out.append(clip(box, "".join(body), f"{st.prefix}-cm{i}"))
    return "".join(out)


Staging = Callable[[MemeFormat, dict[str, str], Cast, Stage], str]

STAGINGS: dict[str, Staging] = {
    "right_right": right_right,
    "this_is_fine": this_is_fine,
    "this_is_fine_2": this_is_fine_2,
    "expanding_brain": expanding_brain,
    "nope_yep": nope_yep,
    "pointing_twins": pointing_twins,
    "distracted": distracted,
    "two_buttons": two_buttons,
    "midwit_bell_curve": midwit,
    "gru_plan": gru_plan,
    "always_has_been": always_has_been,
    "change_my_mind": change_my_mind,
    "is_this_a": is_this_a,
    "shocked_strip": shocked_strip,
    "classic_caption": classic_caption,
    "panik_kalm_panik": panik_kalm_panik,
    "running_away_balloon": running_away_balloon,
}
COMICS = ("comic_strip_3", "comic_grid_4")

# Who can be cast in each format (role -> default kind, hint). Formats not listed have one role, "star".
ROLES: dict[str, tuple[CastRole, ...]] = {
    "right_right": (
        CastRole("confident", "person", "makes the grand claim (left)"),
        CastRole("hopeful", "person", "asks 'right?' (right)"),
    ),
    "this_is_fine": (CastRole("calm_one", "person", "sits calmly in the fire"),),
    "this_is_fine_2": (CastRole("calm_one", "person", "sits calmly in the fire"),),
    "nope_yep": (CastRole("chooser", "person", "rejects, then approves"),),
    "pointing_twins": (CastRole("twin", "person", "both identical twins"),),
    "distracted": (
        CastRole("distracted", "person", "the one turning to look"),
        CastRole("shiny", "person", "the shiny passer-by"),
        CastRole("partner", "person", "the outraged partner"),
    ),
    "two_buttons": (CastRole("chooser", "person", "sweats over the choice"),),
    "midwit_bell_curve": (
        CastRole("beginner", "person", "left tail"),
        CastRole("midwit", "person", "the overthinker at the peak"),
        CastRole("expert", "person", "the serene expert"),
    ),
    "gru_plan": (CastRole("planner", "person", "presents the plan"),),
    "always_has_been": (CastRole("realizer", "person", "the shocked astronaut"), CastRole("knower", "person", "the calm astronaut behind")),
    "change_my_mind": (CastRole("debater", "person", "sits behind the sign"),),
    "is_this_a": (CastRole("misjudger", "person", "mislabels the butterfly"),),
    "shocked_strip": (CastRole("decider", "person", "makes the choice, then is shocked"),),
    "classic_caption": (CastRole("star", "person", "the reaction (pick an expression)"),),
    "panik_kalm_panik": (CastRole("reactor", "person", "panics, calms, panics"),),
    "running_away_balloon": (CastRole("chaser", "person", "reaches for the balloon"), CastRole("holder", "person", "holds them back")),
}


def is_staged(format_id: str) -> bool:
    return format_id in STAGINGS or format_id in COMICS


def stage_art(fmt: MemeFormat, words: dict[str, str], cast: Cast, st: Stage, panels: list[dict] | None = None) -> str:
    """The art layer for a staged format, with its defs; '' for formats with no staging."""
    if st.look == "inferno_robots":
        # The robots look casts robots wherever Claude kept the default cast (the ghost is the default elsewhere).
        cast = {**{r.name: {"kind": "robot"} for r in ROLES.get(fmt.id, (CastRole("star", "ghost", ""),))}, **cast}
        panels = [
            {
                **p,
                "characters": [
                    {**c, "kind": "robot"} if c.get("kind") == "ghost" and (k > 0 or len(p.get("characters") or []) == 1) else c
                    for k, c in enumerate(p.get("characters") or [])
                ],
            }
            for p in (panels or [])
        ]
    if fmt.id in COMICS:
        art = comic(fmt, words, cast, st, panels)
    elif fmt.id in STAGINGS:
        art = STAGINGS[fmt.id](fmt, words, cast, st)
    else:
        return ""
    return st.defs() + art


def roles_menu(format_id: str) -> str:
    roles = ROLES.get(format_id)
    if not roles:
        return ""
    return "; ".join(f"`{r.name}` ({r.hint}, default {r.default})" for r in roles)

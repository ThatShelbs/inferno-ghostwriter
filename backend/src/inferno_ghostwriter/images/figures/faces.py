"""Faces shared by every style: an expression is brows + eyes + mouth + extras, drawn at any size.

``f`` is the direction the face looks (+1 right, -1 left). Shapes are drawn in face units (a line-art head is about
46 units wide) and scaled by ``s``.
"""

from __future__ import annotations

from dataclasses import dataclass

from inferno_ghostwriter.images.figures.base import fmt

TEAR = "#8fd3ff"
SWEAT = "#a8dcff"
MOUTH = "#5b1f2e"


@dataclass(frozen=True)
class Expression:
    label: str
    eyes: str  # dot | open | wide | happy | calm | lidded | tight | focused
    mouth: str  # smile | flat | frown | grin | smirk | o | grimace | wobble | scream | none
    brows: tuple[float, float] | None = (0.0, 0.0)  # (inner, outer) raise; negative = up
    tears: bool = False
    sweat: bool = False
    blush: bool = False


EXPRESSIONS: dict[str, Expression] = {
    "neutral": Expression("calm, pleasant default", "dot", "smile"),
    "happy": Expression("big open grin, eyes closed with joy", "happy", "grin", (-2.5, -2.5), blush=True),
    "smug": Expression("lidded eyes and a sideways smirk, very pleased with itself", "lidded", "smirk", (1.0, -3.5)),
    "calm": Expression("serene, eyes gently closed, faint smile (the enlightened one)", "calm", "smile", (0.5, 0.5)),
    "focused": Expression("brows down, narrowed eyes, flat mouth: locked in", "focused", "flat", (2.2, -0.5)),
    "crying": Expression("tears streaming, teeth gritted (the bell-curve middle)", "tight", "grimace", (-4.0, 1.5), tears=True),
    "panicked": Expression("wide eyes, tiny pupils, screaming, sweat flying", "wide", "scream", (-5.0, 0.0), sweat=True),
    "nervous": Expression("worried brows, wobbly mouth, sweat drop (the two-buttons sweat)", "open", "wobble", (-3.5, 1.0), sweat=True),
    "disgusted": Expression("eyes squeezed shut, frown, turning away (Drake 'nope')", "tight", "frown", (3.0, 0.0)),
    "shocked": Expression("eyes wide, brows up, mouth a small o", "wide", "o", (-4.5, -4.5)),
    "impressed": Expression("brows up, eyes on the prize, an appreciative 'ooh' (the distracted look)", "open", "o", (-3.5, -3.0)),
    "cool": Expression("dark sunglasses and a confident grin (the house ghost Specter's signature look)", "shades", "smirk", None),
}


def _eye(kind: str, x: float, y: float, side: int, f: int, ink: str, white: str, s: float) -> str:
    sw = fmt(2.4 * s)
    stroke = f'fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "dot":
        return f'<ellipse cx="{fmt(x)}" cy="{fmt(y)}" rx="{fmt(2.7 * s)}" ry="{fmt(3.4 * s)}" fill="{ink}"/>'
    if kind in ("open", "wide"):
        rx, ry, pr = (4.6, 5.0, 2.4) if kind == "open" else (5.6, 6.4, 1.7)
        return (
            f'<ellipse cx="{fmt(x)}" cy="{fmt(y)}" rx="{fmt(rx * s)}" ry="{fmt(ry * s)}" fill="{white}" stroke="{ink}" '
            f'stroke-width="{fmt(1.8 * s)}"/>'
            f'<circle cx="{fmt(x + f * (1.4 if kind == "open" else 0.4) * s)}" cy="{fmt(y + 0.6 * s)}" r="{fmt(pr * s)}" fill="{ink}"/>'
        )
    if kind == "happy":
        return (
            f'<path d="M{fmt(x - 4.2 * s)} {fmt(y + 1.5 * s)} Q{fmt(x)} {fmt(y - 5 * s)} {fmt(x + 4.2 * s)} {fmt(y + 1.5 * s)}" {stroke}/>'
        )
    if kind == "calm":
        return f'<path d="M{fmt(x - 4.2 * s)} {fmt(y)} Q{fmt(x)} {fmt(y + 4 * s)} {fmt(x + 4.2 * s)} {fmt(y)}" {stroke}/>'
    if kind == "lidded":
        return (
            f'<path d="M{fmt(x - 4.4 * s)} {fmt(y + 0.5 * s)} Q{fmt(x)} {fmt(y + 6 * s)} {fmt(x + 4.4 * s)} {fmt(y + 0.5 * s)} Z" '
            f'fill="{ink}"/>'
            f'<path d="M{fmt(x - 5.2 * s)} {fmt(y + 0.2 * s)} L{fmt(x + 5.2 * s)} {fmt(y - 0.6 * s)}" {stroke}/>'
        )
    if kind == "tight":
        # A squeezed-shut eye: a chevron pointing at the nose.
        tip = x - side * 3.8 * s
        back = x + side * 4.0 * s
        return f'<path d="M{fmt(back)} {fmt(y - 3.4 * s)} L{fmt(tip)} {fmt(y)} L{fmt(back)} {fmt(y + 3.0 * s)}" {stroke}/>'
    if kind == "focused":
        return (
            f'<ellipse cx="{fmt(x + f * 0.6 * s)}" cy="{fmt(y + 0.6 * s)}" rx="{fmt(2.8 * s)}" ry="{fmt(2.4 * s)}" fill="{ink}"/>'
            f'<path d="M{fmt(x - 4.4 * s)} {fmt(y - 2.2 * s)} L{fmt(x + 4.4 * s)} {fmt(y - 2.2 * s)}" {stroke}/>'
        )
    return ""


def _mouth(kind: str, x: float, y: float, f: int, ink: str, white: str, s: float) -> str:
    sw = fmt(2.4 * s)
    stroke = f'fill="none" stroke="{ink}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
    filled = f'stroke="{ink}" stroke-width="{fmt(2 * s)}" stroke-linejoin="round"'

    def p(dx: float, dy: float) -> str:
        return f"{fmt(x + dx * s)} {fmt(y + dy * s)}"

    if kind == "smile":
        return f'<path d="M{p(-5.5, -0.5)} Q{p(0, 4.5)} {p(5.5, -0.5)}" {stroke}/>'
    if kind == "flat":
        return f'<path d="M{p(-4.5, 0.5)} L{p(4.5, 0)}" {stroke}/>'
    if kind == "frown":
        return f'<path d="M{p(-6, 3)} Q{p(0, -3)} {p(6, 3)}" {stroke}/>'
    if kind == "grin":
        return (
            f'<path d="M{p(-8, -2)} Q{p(0, -0.5)} {p(8, -2)} Q{p(7, 9)} {p(0, 9.5)} Q{p(-7, 9)} {p(-8, -2)} Z" fill="{MOUTH}" {filled}/>'
            f'<path d="M{p(-6.6, -1.2)} Q{p(0, 0)} {p(6.6, -1.2)} L{p(6, 2)} Q{p(0, 3)} {p(-6, 2)} Z" fill="{white}"/>'
        )
    if kind == "smirk":
        return f'<path d="M{p(-5 * f, 1)} Q{p(1 * f, 3.5)} {p(6 * f, -2.5)}" {stroke}/>'
    if kind == "o":
        return f'<ellipse cx="{fmt(x)}" cy="{fmt(y + 1 * s)}" rx="{fmt(2.8 * s)}" ry="{fmt(3.4 * s)}" fill="{MOUTH}" {filled}/>'
    if kind == "scream":
        return f'<ellipse cx="{fmt(x)}" cy="{fmt(y + 2.5 * s)}" rx="{fmt(4.6 * s)}" ry="{fmt(6.2 * s)}" fill="{MOUTH}" {filled}/>'
    if kind == "grimace":
        thin = f'fill="none" stroke="{ink}" stroke-width="{fmt(1.3 * s)}" stroke-linecap="round"'
        teeth = "".join(f'<path d="M{p(dx, -2.6)} L{p(dx, 2.6)}" {thin}/>' for dx in (-3.4, 0, 3.4))
        return (
            f'<rect x="{fmt(x - 8.5 * s)}" y="{fmt(y - 3.8 * s)}" width="{fmt(17 * s)}" height="{fmt(7.6 * s)}" rx="{fmt(3 * s)}" '
            f'fill="{white}" {filled}/>'
            f'<path d="M{p(-8, 0)} L{p(8, 0)}" {thin}/>{teeth}'
        )
    if kind == "wobble":
        return f'<path d="M{p(-7, 1)} Q{p(-5.2, -2)} {p(-3.5, 1)} T{p(0, 1)} T{p(3.5, 1)} T{p(7, 1)}" {stroke}/>'
    return ""


def _sweat(x: float, y: float, s: float, ink: str) -> str:
    def drop(cx: float, cy: float, k: float) -> str:
        k *= s
        return (
            f'<path d="M{fmt(cx)} {fmt(cy - 5 * k)} Q{fmt(cx + 4 * k)} {fmt(cy + 1 * k)} {fmt(cx)} {fmt(cy + 2.6 * k)} '
            f'Q{fmt(cx - 4 * k)} {fmt(cy + 1 * k)} {fmt(cx)} {fmt(cy - 5 * k)} Z" fill="{SWEAT}" stroke="{ink}" '
            f'stroke-width="{fmt(1.4 * s)}" stroke-linejoin="round"/>'
        )

    return drop(x, y, 1.0) + drop(x + 6 * s, y + 7 * s, 0.75)


def _shades(cx: float, cy: float, spread: float, s: float, ink: str) -> str:
    """Wraparound sunglasses: two rounded dark lenses with a bridge and a glint."""
    lens_w, lens_h = 10.5 * s, 7.2 * s
    out = [
        f'<path d="M{fmt(cx - spread * s + lens_w * 0.7)} {fmt(cy - 2 * s)} H{fmt(cx + spread * s - lens_w * 0.7)}" '
        f'stroke="{ink}" stroke-width="{fmt(2.6 * s)}" stroke-linecap="round"/>'
    ]
    for side in (-1, 1):
        x = cx + side * spread * s
        out.append(
            f'<rect x="{fmt(x - lens_w)}" y="{fmt(cy - lens_h)}" width="{fmt(2 * lens_w)}" height="{fmt(1.7 * lens_h)}" '
            f'rx="{fmt(4.5 * s)}" fill="#14101f" stroke="{ink}" stroke-width="{fmt(1.6 * s)}"/>'
            f'<path d="M{fmt(x - lens_w * 0.55)} {fmt(cy - lens_h * 0.45)} L{fmt(x - lens_w * 0.1)} {fmt(cy - lens_h * 0.45)}" '
            f'stroke="#ffffff" stroke-opacity="0.75" stroke-width="{fmt(1.8 * s)}" stroke-linecap="round"/>'
        )
    return "".join(out)


def face(
    expression: str,
    *,
    cx: float,
    cy: float,
    s: float = 1.0,
    f: int = 1,
    ink: str,
    white: str = "#ffffff",
    cheek: str = "#ff8fa3",
    spread: float = 9.0,
    nose: bool = False,
    mouth: bool = True,
    brows: bool = True,
    cheeks: bool = False,
    simple: bool = False,
) -> str:
    """The face for ``expression`` centred on (cx, cy): eyes on the centre line, mouth below."""
    ex = EXPRESSIONS.get(expression, EXPRESSIONS["neutral"])
    out: list[str] = []
    eyes = [(-1, cx - spread * s), (1, cx + spread * s)]
    if ex.tears:
        for side, x in eyes:
            ox = x + side * 1.5 * s
            out.append(
                f'<path d="M{fmt(ox - 2.6 * s)} {fmt(cy + 1.5 * s)} Q{fmt(ox - 3.4 * s)} {fmt(cy + 12 * s)} {fmt(ox - 1.2 * s)} '
                f"{fmt(cy + 22 * s)} L{fmt(ox + 2.4 * s)} {fmt(cy + 22 * s)} Q{fmt(ox + 1.4 * s)} {fmt(cy + 12 * s)} "
                f'{fmt(ox + 2.6 * s)} {fmt(cy + 1.5 * s)} Z" fill="{TEAR}" stroke="{ink}" stroke-width="{fmt(1.3 * s)}" '
                'stroke-linejoin="round"/>'
            )
    if ex.blush or cheeks:
        for side, x in eyes:
            out.append(
                f'<ellipse cx="{fmt(x + side * 2.5 * s)}" cy="{fmt(cy + 8.5 * s)}" rx="{fmt(4.2 * s)}" ry="{fmt(2.4 * s)}" '
                f'fill="{cheek}" fill-opacity="0.55"/>'
            )
    eye_kind = ex.eyes
    if simple and eye_kind in ("open", "wide", "focused", "lidded"):
        eye_kind = "dot"
    if eye_kind == "shades":
        out.append(_shades(cx, cy, spread, s, ink))
    else:
        for side, x in eyes:
            out.append(_eye(eye_kind, x, cy, side, f, ink, white, s))
    if brows and ex.brows is not None:
        inner, outer = ex.brows
        by = cy - 8.5 * s
        for side, x in eyes:
            x_in, x_out = x - side * 4.2 * s, x + side * 4.6 * s
            out.append(
                f'<path d="M{fmt(x_in)} {fmt(by + inner * s)} L{fmt(x_out)} {fmt(by + outer * s)}" fill="none" stroke="{ink}" '
                f'stroke-width="{fmt(2.6 * s)}" stroke-linecap="round"/>'
            )
    if nose:
        nx = cx + f * 2.5 * s
        out.append(
            f'<path d="M{fmt(nx)} {fmt(cy + 2 * s)} Q{fmt(nx + f * 4 * s)} {fmt(cy + 7 * s)} {fmt(nx)} {fmt(cy + 8 * s)}" '
            f'fill="none" stroke="{ink}" stroke-width="{fmt(1.8 * s)}" stroke-linecap="round"/>'
        )
    if mouth or (simple and ex.mouth in ("o", "scream", "grin", "frown")) or (not simple and ex.mouth != "smile"):
        out.append(_mouth(ex.mouth, cx + f * 1.0 * s, cy + 14 * s, f, ink, white, s))
    if ex.sweat:
        out.append(_sweat(cx - f * 17 * s, cy - 14 * s, s, ink))
    return "".join(out)

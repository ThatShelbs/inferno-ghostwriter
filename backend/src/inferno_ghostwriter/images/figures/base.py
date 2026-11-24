"""Shared pieces of the figure library: colors, the symbol type, limb geometry and the small props figures hold.

Every figure is drawn in its own frame: x = 0 is the figure's centre line, y = 0 is the ground under its feet and
the figure stands in negative y. A figure faces right; facing left mirrors the whole drawing about x = 0.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inferno_ghostwriter.images.palettes import Scheme

Point = tuple[float, float]

# Natural skin tones, light to deep. Figures never take skin from the palette ramp.
SKIN_TONES = ("#fde3cf", "#f3cfb3", "#e2ab84", "#c68863", "#8d5a3b", "#5e3a26")
HAIR_TONES = ("#2b2024", "#4a3227", "#7a4a2a", "#c98b3c", "#e8c77e", "#9a9aa6")


@dataclass(frozen=True)
class FigureColors:
    """The colors a figure is painted with. Defaults are a warm inferno-friendly cast; any field can be overridden
    (a red dress, a plaid shirt, an orange puffer jacket) or the whole set taken from a palette scheme."""

    skin: str = SKIN_TONES[1]
    hair: str = HAIR_TONES[0]
    shirt: str = "#ed6925"
    pants: str = "#2f3447"
    shoes: str = "#2a2230"
    accent: str = "#fb9b06"
    ink: str = "#1d1726"
    ghost: str = "#f8f5ff"
    plaid: str = "#1b0c41"  # the crossing stripes of a plaid shirt
    cheek: str = "#ff8fa3"

    def with_(self, **changes: str) -> FigureColors:
        return replace(self, **changes)

    @classmethod
    def from_scheme(cls, sch: Scheme, index: int = 0, *, skin: int = 1, hair: int = 0) -> FigureColors:
        """A cast member colored from a palette scheme: clothes and props from the ramp, skin and hair natural.
        ``index`` rotates through the scheme's accents so neighbours in one picture differ."""
        from inferno_ghostwriter.images.palettes import mix

        shirt = sch.accent(index)
        accent = sch.accent(index + 2)
        pants = mix(sch.ramp[1], "#3a3f55", 0.5)
        ink = "#1d1726"
        return cls(
            skin=SKIN_TONES[skin % len(SKIN_TONES)],
            hair=HAIR_TONES[hair % len(HAIR_TONES)],
            shirt=shirt,
            pants=pants,
            shoes=mix(pants, "#000000", 0.35),
            accent=accent,
            ink=ink,
            ghost=mix("#ffffff", sch.ramp[3], 0.035),
            plaid=sch.ramp[1],
        )

    def values(self) -> tuple[str, ...]:
        return (self.skin, self.hair, self.shirt, self.pants, self.shoes, self.accent, self.ink, self.ghost, self.plaid)


@dataclass(frozen=True)
class SvgSymbol:
    """One figure as an SVG ``<symbol>``. ``view_box`` is (x, y, width, height) with y + height = 0: the bottom edge of
    the box is the ground under the feet and x = 0 is the figure's centre line. ``anchors`` name useful points
    (hands, the flashlight lens, the head) in the same units, already mirrored for a left-facing figure."""

    id: str
    view_box: tuple[float, float, float, float]
    body: str
    anchors: dict[str, Point] = field(default_factory=dict)

    @property
    def width(self) -> float:
        return self.view_box[2]

    @property
    def height(self) -> float:
        return self.view_box[3]

    @property
    def svg(self) -> str:
        vb = " ".join(fmt(v) for v in self.view_box)
        return f'<symbol id="{self.id}" viewBox="{vb}" overflow="visible">{self.body}</symbol>'

    def use(self, x: float, ground: float, height: float) -> str:
        """A ``<use>`` that stands this figure with its feet at (x, ground), ``height`` tall."""
        scale = height / self.height
        w = self.width * scale
        left = x + self.view_box[0] * scale
        return f'<use href="#{self.id}" x="{fmt(left)}" y="{fmt(ground - height)}" width="{fmt(w)}" height="{fmt(height)}"/>'

    def anchor(self, name: str, x: float, ground: float, height: float) -> Point:
        """Where anchor ``name`` lands when the figure is placed with :meth:`use`."""
        scale = height / self.height
        ax, ay = self.anchors[name]
        return x + ax * scale, ground + ay * scale


# -- geometry ---------------------------------------------------------------------------------------------------------


def fmt(v: float) -> str:
    text = f"{v:.1f}"
    return text[:-2] if text.endswith(".0") else ("0" if text == "-0" else text)


def pts(*points: Point) -> str:
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in points)


def ik(shoulder: Point, target: Point, upper: float, fore: float, bend: int) -> Point:
    """The elbow of a two-bone arm reaching ``target``; ``bend`` (+1 / -1) picks which side the elbow goes."""
    sx, sy = shoulder
    dx, dy = target[0] - sx, target[1] - sy
    d = max(1e-6, math.hypot(dx, dy))
    d_eff = min(d, upper + fore - 0.01)
    a = (upper**2 - fore**2 + d_eff**2) / (2 * d_eff)
    h = math.sqrt(max(0.0, upper**2 - a**2))
    ux, uy = dx / d, dy / d
    px, py = sx + ux * a, sy + uy * a
    return px - uy * h * bend, py + ux * h * bend


def reach(shoulder: Point, target: Point, upper: float, fore: float) -> Point:
    """``target`` pulled in to what an arm of these lengths can reach."""
    sx, sy = shoulder
    dx, dy = target[0] - sx, target[1] - sy
    d = math.hypot(dx, dy)
    limit = upper + fore - 0.02
    if d <= limit:
        return target
    return sx + dx / d * limit, sy + dy / d * limit


def angle(a: Point, b: Point) -> float:
    """Degrees of the direction from ``a`` to ``b`` (0 = +x, clockwise in SVG's y-down frame)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def smooth(points: Sequence[Point], radius: float = 6.0) -> str:
    """A polyline with its corners rounded, as path data."""
    if len(points) < 3:
        return "M" + " L".join(pts(p) for p in points)
    out = [f"M{pts(points[0])}"]
    for prev, cur, nxt in zip(points, points[1:], points[2:], strict=False):
        l1 = math.dist(prev, cur)
        l2 = math.dist(cur, nxt)
        r = min(radius, l1 / 2, l2 / 2)
        if r < 0.5:
            out.append(f"L{pts(cur)}")
            continue
        a = (cur[0] + (prev[0] - cur[0]) / l1 * r, cur[1] + (prev[1] - cur[1]) / l1 * r)
        b = (cur[0] + (nxt[0] - cur[0]) / l2 * r, cur[1] + (nxt[1] - cur[1]) / l2 * r)
        out.append(f"L{pts(a)} Q{pts(cur)} {pts(b)}")
    out.append(f"L{pts(points[-1])}")
    return " ".join(out)


def limb(points: Sequence[Point], width: float, color: str, ink: str | None, outline: float, *, radius: float = 6.0) -> str:
    """A rounded limb: an ink stroke under a colored one, so it reads as an outlined tube."""
    d = smooth(points, radius)
    base = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    under = f'<path d="{d}" {base} stroke="{ink}" stroke-width="{fmt(width + 2 * outline)}"/>' if ink and outline else ""
    return f'{under}<path d="{d}" {base} stroke="{color}" stroke-width="{fmt(width)}"/>'


def place(at: Point, rot: float, markup: str, scale: float = 1.0) -> str:
    s = f" scale({fmt(scale)})" if scale != 1 else ""
    return f'<g transform="translate({fmt(at[0])} {fmt(at[1])}) rotate({fmt(rot)}){s}">{markup}</g>'


def local_to_world(at: Point, rot: float, p: Point, scale: float = 1.0) -> Point:
    r = math.radians(rot)
    x, y = p[0] * scale, p[1] * scale
    return at[0] + x * math.cos(r) - y * math.sin(r), at[1] + x * math.sin(r) + y * math.cos(r)


@dataclass(frozen=True)
class Arm:
    """One arm of a pose: where the hand goes, which way the elbow bends, what the hand does."""

    to: Point
    bend: int = 1
    hand: str = "fist"  # fist | point | palm | hold | mitt
    hand_rot: float | None = None  # hand direction in degrees; None follows the forearm
    elbow: Point | None = None  # an explicit elbow (crossed arms, forearms longer than the arm can reach)


# -- props ------------------------------------------------------------------------------------------------------------

LENS = (25.0, 0.0)


def flashlight(c: FigureColors, outline: float = 2.4) -> str:
    """A flashlight along +x, handle at the origin (under the hand), lens at :data:`LENS`."""
    body = "#3b3347"
    return (
        f'<rect x="-6" y="-4.2" width="21" height="8.4" rx="2.6" fill="{body}" stroke="{c.ink}" stroke-width="{fmt(outline)}"/>'
        f'<path d="M14 -4.6 L22 -7 Q25 -7 25 -4 L25 4 Q25 7 22 7 L14 4.6 Z" fill="{c.accent}" stroke="{c.ink}" '
        f'stroke-width="{fmt(outline)}" stroke-linejoin="round"/>'
        f'<rect x="23.4" y="-5" width="2.4" height="10" rx="1.2" fill="#fff6c8"/>'
    )


def towel(c: FigureColors, outline: float = 2.4) -> str:
    """A crumpled white cloth held over the knuckles (local +x = forearm direction)."""
    return (
        f'<path d="M-6 -9 Q4 -14 14 -8 Q19 -1 13 6 Q16 13 6 15 Q-3 17 -6 9 Q-11 0 -6 -9 Z" fill="#ffffff" '
        f'stroke="{c.ink}" stroke-width="{fmt(outline)}" stroke-linejoin="round"/>'
        f'<path d="M0 -6 Q5 0 2 8 M8 -7 Q12 0 9 9" fill="none" stroke="{c.ink}" stroke-width="1.3" stroke-opacity="0.45" '
        f'stroke-linecap="round"/>'
    )


def desk_laptop(c: FigureColors, x0: float, top: float, width: float, outline: float, *, lid: float = 36) -> tuple[str, Point]:
    """A small side-view standing desk from ``x0`` with its top at ``top``, a laptop open on it facing left (toward the
    figure). Returns the markup and the keyboard point hands rest on."""
    desk = "#4b4458"
    leg_x = x0 + width - 12
    kb_x0, kb_x1 = x0 + 6, x0 + width * 0.72
    hinge = (kb_x1, top - 3.5)
    lid_top = (kb_x1 - lid * 0.22, top - 3.5 - lid)
    o = fmt(outline)
    markup = (
        f'<rect x="{fmt(leg_x)}" y="{fmt(top)}" width="7" height="{fmt(-top)}" fill="{desk}" stroke="{c.ink}" stroke-width="{o}"/>'
        f'<rect x="{fmt(leg_x - 7.5)}" y="-4" width="22" height="4" rx="2" fill="{desk}" stroke="{c.ink}" stroke-width="{o}"/>'
        f'<rect x="{fmt(x0)}" y="{fmt(top)}" width="{fmt(width)}" height="6" rx="2" fill="{desk}" stroke="{c.ink}" stroke-width="{o}"/>'
        f'<rect x="{fmt(kb_x0)}" y="{fmt(top - 3.5)}" width="{fmt(kb_x1 - kb_x0 + 2)}" height="3.5" rx="1.5" fill="#d9d4e4" '
        f'stroke="{c.ink}" stroke-width="{o}"/>'
        f'<path d="M{pts(hinge)} L{pts(lid_top)} L{pts((lid_top[0] + 5, lid_top[1] + 1))} L{pts((hinge[0] + 4, hinge[1]))} Z" '
        f'fill="{c.accent}" stroke="{c.ink}" stroke-width="{o}" stroke-linejoin="round"/>'
        f'<circle cx="{fmt(hinge[0] - lid * 0.11 + 2.5)}" cy="{fmt(hinge[1] - lid * 0.5)}" r="2.2" fill="#ffffff" fill-opacity="0.8"/>'
    )
    return markup, ((kb_x0 + kb_x1) / 2 - 4, top - 5)


def shadow(rx: float, color: str = "#1d1726", opacity: float = 0.12) -> str:
    return f'<ellipse cx="0" cy="{fmt(-rx * 0.12)}" rx="{fmt(rx)}" ry="{fmt(rx * 0.12)}" fill="{color}" fill-opacity="{opacity}"/>'

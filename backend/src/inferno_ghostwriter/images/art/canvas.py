"""Shared drawing helpers for the data-art engines: the art palette, filters and a small SVG builder.

Every color an engine writes comes from :class:`ArtPalette`, which only knows the scheme's ramp (sampled at fixed
steps), its background and the background's far end, so a finished piece can never leave the scheme.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from inferno_ghostwriter.images.palettes import Scheme

STEPS = 40
"""The ramp is sampled at ``STEPS + 1`` fixed points; engines snap to them."""

W, H = 1600, 900


def band(width: int = W, height: int = H) -> tuple[float, float]:
    """The centre 5:2 crop band's top and bottom (the part every crop keeps)."""
    h = min(height, width * 2 / 5)
    return (height - h) / 2, (height + h) / 2


@dataclass(frozen=True)
class ArtPalette:
    """The colors a piece may use: the ramp at fixed steps, the background and its far end."""

    scheme: Scheme

    @property
    def dark(self) -> bool:
        return self.scheme.dark

    @property
    def bg(self) -> str:
        return self.scheme.bg

    @property
    def bg2(self) -> str:
        return self.scheme.bg2

    def ramp(self, t: float) -> str:
        """The ramp at ``t`` (0 dark end, 1 light end), snapped to a fixed step."""
        t = max(0.0, min(1.0, t))
        return self.scheme.at(round(t * STEPS) / STEPS)

    def tone(self, u: float) -> str:
        """The ramp's visible part at ``u`` (0 = quiet, 1 = most vivid on this background)."""
        lo, hi = self.span
        return self.ramp(lo + (hi - lo) * max(0.0, min(1.0, u)))

    @property
    def span(self) -> tuple[float, float]:
        """The ramp range that reads on the background: the bright end on dark, the deep end on light."""
        if self.dark:
            return (0.32, 0.97) if self.scheme.ramp_id != "viridis" else (0.22, 1.0)
        return (0.0, 0.78) if self.scheme.ramp_id != "viridis" else (0.0, 0.7)

    def glow(self) -> str:
        return self.tone(1.0)

    def colors(self) -> set[str]:
        """Every color this palette can write (tests check pieces against it)."""
        out = {self.scheme.at(i / STEPS).lower() for i in range(STEPS + 1)}
        out |= {self.bg.lower(), self.bg2.lower(), "#ffffff", "#000000"}
        return out


# -- SVG building ---------------------------------------------------------------------------------------------------


def f(v: float) -> str:
    """A coordinate with one decimal (keeps the SVG small)."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def pts(points: Iterable[tuple[float, float]]) -> str:
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


def path_d(points: Sequence[tuple[float, float]], *, smooth: bool = True, closed: bool = False) -> str:
    """A path through ``points``: straight segments, or Catmull-Rom curves converted to cubic Beziers."""
    if len(points) < 2:
        return ""
    if not smooth or len(points) < 3:
        d = f"M{f(points[0][0])},{f(points[0][1])}L" + pts(points[1:])
        return d + ("Z" if closed else "")
    out = [f"M{f(points[0][0])},{f(points[0][1])}"]
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(p2[0])},{f(p2[1])}")
    return "".join(out) + ("Z" if closed else "")


@dataclass
class Svg:
    """A tiny SVG document builder: defs plus layered groups."""

    width: int = W
    height: int = H
    defs: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    _ids: set[str] = field(default_factory=set)

    def blur(self, std: float, *, name: str | None = None) -> str:
        """A plain Gaussian blur filter (depth of field); returns its id."""
        fid = name or f"b{f(std).replace('.', '_')}"
        if fid not in self._ids:
            self._ids.add(fid)
            self.defs.append(
                f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB">'
                f'<feGaussianBlur stdDeviation="{f(std)}"/></filter>'
            )
        return fid

    def glow(self, std: float, *, strength: float = 1.0, name: str | None = None) -> str:
        """A bloom filter: the shape over its own blurred halo; returns its id."""
        fid = name or f"g{f(std).replace('.', '_')}_{f(strength).replace('.', '_')}"
        if fid not in self._ids:
            self._ids.add(fid)
            self.defs.append(
                f'<filter id="{fid}" x="-50%" y="-50%" width="200%" height="200%" color-interpolation-filters="sRGB">'
                f'<feGaussianBlur in="SourceGraphic" stdDeviation="{f(std * 2.4)}" result="wide"/>'
                f'<feGaussianBlur in="SourceGraphic" stdDeviation="{f(std)}" result="near"/>'
                f'<feComponentTransfer in="wide" result="wide2"><feFuncA type="linear" slope="{f(strength)}"/></feComponentTransfer>'
                '<feMerge><feMergeNode in="wide2"/><feMergeNode in="near"/><feMergeNode in="SourceGraphic"/></feMerge>'
                "</filter>"
            )
        return fid

    def linear(self, gid: str, stops: Sequence[tuple[float, str, float]], *, x1=0.0, y1=0.0, x2=0.0, y2=1.0) -> str:
        self.defs.append(
            f'<linearGradient id="{gid}" x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}">'
            + "".join(f'<stop offset="{f(o)}" stop-color="{c}" stop-opacity="{op:.2f}"/>' for o, c, op in stops)
            + "</linearGradient>"
        )
        return gid

    def radial(self, gid: str, stops: Sequence[tuple[float, str, float]], *, cx=0.5, cy=0.5, r=0.5) -> str:
        self.defs.append(
            f'<radialGradient id="{gid}" cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}">'
            + "".join(f'<stop offset="{o:.3f}" stop-color="{c}" stop-opacity="{op:.2f}"/>' for o, c, op in stops)
            + "</radialGradient>"
        )
        return gid

    def add(self, *parts: str) -> None:
        self.body.extend(parts)

    def group(self, parts: Iterable[str], *, filter_id: str | None = None, opacity: float | None = None, extra: str = "") -> None:
        items = list(parts)
        if not items:
            return
        attrs = ""
        if filter_id:
            attrs += f' filter="url(#{filter_id})"'
        if opacity is not None:
            attrs += f' opacity="{opacity:.2f}"'
        if extra:
            attrs += " " + extra
        self.body.append(f"<g{attrs}>" + "".join(items) + "</g>")

    def render(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}">'
            f"<defs>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )


def backdrop(svg: Svg, pal: ArtPalette, *, cx: float = 0.5, cy: float = 0.5, tint: float = 0.0, tint_t: float = 0.1) -> None:
    """The background: the surface, a soft vignette to its far end and an optional glow of ramp color."""
    svg.add(f'<rect width="{svg.width}" height="{svg.height}" fill="{pal.bg}"/>')
    svg.radial("vignette", [(0.0, pal.bg, 0.0), (0.55, pal.bg, 0.0), (1.0, pal.bg2, 0.9 if pal.dark else 0.6)], cx=cx, cy=cy, r=0.85)
    svg.add(f'<rect width="{svg.width}" height="{svg.height}" fill="url(#vignette)"/>')
    if tint > 0:
        svg.radial("tint", [(0.0, pal.tone(tint_t), tint), (1.0, pal.tone(tint_t), 0.0)], cx=cx, cy=cy, r=0.6)
        svg.add(f'<rect width="{svg.width}" height="{svg.height}" fill="url(#tint)"/>')


# -- maths ----------------------------------------------------------------------------------------------------------


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


class Noise:
    """Smooth 2D value noise from summed random sines (deterministic per rng, no numpy)."""

    def __init__(self, rng: random.Random, octaves: int = 4, scale: float = 1.0) -> None:
        self.waves = []
        for i in range(octaves):
            freq = scale * (1.6**i)
            for _ in range(2):
                ang = rng.uniform(0, math.tau)
                self.waves.append((math.cos(ang) * freq, math.sin(ang) * freq, rng.uniform(0, math.tau), 1 / (1.7**i)))
        self.norm = sum(w[3] for w in self.waves)

    def __call__(self, x: float, y: float) -> float:
        return sum(a * math.sin(kx * x + ky * y + p) for kx, ky, p, a in self.waves) / self.norm

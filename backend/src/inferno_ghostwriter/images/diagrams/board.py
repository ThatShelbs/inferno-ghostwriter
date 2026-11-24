"""The drawing surface for code-drawn diagrams: SVG shapes plus text that is measured before it is written.

Every string is fitted to its box with Pillow in the bundled Inter fonts (``memes.text.fit_text``: largest size that
fits, wrapping by measured width, an ellipsis only at the minimum size), then written as SVG ``<text>`` in the same
font, which resvg renders from the same files, so what was measured is what is drawn. Parallel texts share one size
through ``group``. Colors come only from the image's ``Scheme`` (``Colors``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import cached_property

from PIL import Image, ImageDraw

from inferno_ghostwriter.images.memes.text import Fitted, Style, fit_text
from inferno_ghostwriter.images.palettes import INK_DARK, Scheme, contrast, luminance, mix
from inferno_ghostwriter.images.render import SVG_NS, svg_to_png

Box = tuple[float, float, float, float]

W = 1400
MARGIN = 64
MIN_TEXT = 16  # px at 1400 wide: 8px on a 700px Medium column, the floor for anything readable
WHITE = "#ffffff"
BLACK = "#000000"

_FONTS = {"heavy": ("Inter", 900), "bold": ("Inter", 700), "regular": ("Inter", 400), "mono": ("JetBrains Mono", 400)}
_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def readable(background: str, dark: str, light: str = WHITE) -> str:
    return dark if contrast(background, dark) >= contrast(background, light) else light


@dataclass(frozen=True)
class Colors:
    """Every color a diagram uses, derived from one scheme: ramp stops, their mixes toward the surface, white or
    black, and neutrals between the ink and the surface."""

    sch: Scheme

    @property
    def dark(self) -> bool:
        return self.sch.dark

    @property
    def bg(self) -> str:
        return self.sch.bg

    @property
    def ink(self) -> str:
        return self.sch.ink

    @cached_property
    def muted(self) -> str:
        return mix(self.ink, self.bg, 0.38)

    @cached_property
    def faint(self) -> str:
        return mix(self.ink, self.bg, 0.58)

    @cached_property
    def card(self) -> str:
        return mix(self.bg, WHITE, 0.08) if self.dark else WHITE

    @cached_property
    def edge(self) -> str:
        return mix(self.card, self.ink, 0.1 if self.dark else 0.07)

    @cached_property
    def track(self) -> str:
        """Empty tracks and rails: a hair darker (or lighter) than a card."""
        return mix(self.card, self.ink, 0.12 if self.dark else 0.075)

    @cached_property
    def grey(self) -> str:
        """Fills of things that lost or are set aside."""
        return mix(self.card, self.ink, 0.28 if self.dark else 0.3)

    @property
    def shadow(self) -> str:
        return BLACK

    def _span(self) -> tuple[float, float]:
        if self.sch.ramp_id == "viridis":
            return (0.48, 1.0) if self.dark else (0.04, 0.84)
        if self.sch.ramp_id in ("inferno", "magma"):
            return (0.42, 0.95) if self.dark else (0.14, 0.82)
        return (0.3, 1.0) if self.dark else (0.0, 0.85)

    def at(self, t: float) -> str:
        """A ramp color at ``t`` of the span that reads on this surface (0 = the end furthest from the surface)."""
        lo, hi = self._span()
        return self.sch.at(lo + (hi - lo) * max(0.0, min(1.0, t)))

    def seq(self, n: int, *, reverse: bool = False) -> list[str]:
        """``n`` ramp colors in order, deep (or, on dark, dim) first."""
        if n <= 1:
            return [self.at(0.35)]
        out = [self.at(i / (n - 1)) for i in range(n)]
        return out[::-1] if reverse else out

    def solid(self, color: str) -> str:
        """``color`` moved toward the ink until it reads as text or a stroke on a card."""
        out = color
        for _ in range(6):
            if contrast(out, self.card) >= 3.0:
                return out
            out = mix(out, self.ink, 0.22)
        return out

    def tint(self, color: str, t: float = 0.82) -> str:
        """``color`` washed toward the card (a pale fill behind dark text)."""
        return mix(color, self.card, t)

    def on(self, fill: str) -> str:
        """Ink or white, whichever reads on ``fill``."""
        return readable(fill, INK_DARK, WHITE)


@dataclass
class Placed:
    """One string after fitting: its box, the size it got and its lines."""

    box: Box
    text: str
    style: Style
    fitted: Fitted
    align: str
    valign: str
    rotate: float = 0


@dataclass
class _Pending:
    box: Box
    text: str
    style: Style
    align: str
    valign: str
    group: str
    rotate: float


@dataclass
class Board:
    colors: Colors
    height: int
    width: int = W
    shapes: list[str] = field(default_factory=list)
    _pending: list[_Pending] = field(default_factory=list)
    placed: list[Placed] = field(default_factory=list)

    # -- shapes ------------------------------------------------------------------------------------------------------

    def add(self, svg: str) -> None:
        self.shapes.append(svg)

    def rect(
        self,
        box: Box,
        fill: str,
        *,
        rx: float = 0,
        stroke: str = "",
        stroke_width: float = 0,
        shadow: str = "",
        opacity: float = 1.0,
        dash: str = "",
    ) -> None:
        x, y, w, h = box
        extra = f' stroke="{stroke}" stroke-width="{stroke_width:g}"' if stroke else ""
        extra += f' stroke-dasharray="{dash}"' if dash else ""
        extra += f' filter="url(#{shadow})"' if shadow else ""
        extra += f' opacity="{opacity:.3g}"' if opacity < 1 else ""
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(0, w):.1f}" height="{max(0, h):.1f}" rx="{rx:.1f}" fill="{fill}"{extra}/>')

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: str,
        *,
        stroke: str = "",
        stroke_width: float = 0,
        shadow: str = "",
        opacity: float = 1.0,
    ) -> None:
        extra = f' stroke="{stroke}" stroke-width="{stroke_width:g}"' if stroke else ""
        extra += f' filter="url(#{shadow})"' if shadow else ""
        extra += f' fill-opacity="{opacity:.3g}"' if opacity < 1 else ""
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{fill}"{extra}/>')

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str, width: float = 3, *, dash: str = "") -> None:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
            f'stroke-width="{width:g}" stroke-linecap="round"{d}/>'
        )

    def path(
        self, d: str, *, fill: str = "none", stroke: str = "", width: float = 0, cap: str = "round", shadow: str = "", opacity: float = 1.0
    ) -> None:
        extra = f' stroke="{stroke}" stroke-width="{width:g}" stroke-linecap="{cap}" stroke-linejoin="round"' if stroke else ""
        extra += f' filter="url(#{shadow})"' if shadow else ""
        extra += f' opacity="{opacity:.3g}"' if opacity < 1 else ""
        self.add(f'<path d="{d}" fill="{fill}"{extra}/>')

    def polygon(self, points: list[tuple[float, float]], fill: str, *, stroke: str = "", width: float = 0, shadow: str = "") -> None:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        extra = f' stroke="{stroke}" stroke-width="{width:g}" stroke-linejoin="round"' if stroke else ""
        extra += f' filter="url(#{shadow})"' if shadow else ""
        self.add(f'<polygon points="{pts}" fill="{fill}"{extra}/>')

    def arc(self, cx: float, cy: float, r: float, start: float, end: float, color: str, width: float, *, cap: str = "round") -> None:
        """An arc stroke from ``start`` to ``end`` degrees (0 = 12 o'clock, clockwise)."""
        sweep = end - start
        if sweep <= 0.01:
            return
        if sweep >= 359.99:
            self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" stroke="{color}" stroke-width="{width:g}"/>')
            return
        x0, y0 = polar(cx, cy, r, start)
        x1, y1 = polar(cx, cy, r, end)
        large = 1 if sweep > 180 else 0
        self.path(f"M{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x1:.1f},{y1:.1f}", stroke=color, width=width, cap=cap)

    def arrow(self, x1: float, y1: float, x2: float, y2: float, color: str, width: float = 4) -> None:
        """A straight arrow with a drawn head."""
        angle = math.atan2(y2 - y1, x2 - x1)
        head = width * 3.4
        bx, by = x2 - head * 0.8 * math.cos(angle), y2 - head * 0.8 * math.sin(angle)
        self.line(x1, y1, bx, by, color, width)
        left = (x2 - head * math.cos(angle) + head * 0.62 * math.sin(angle), y2 - head * math.sin(angle) - head * 0.62 * math.cos(angle))
        right = (x2 - head * math.cos(angle) - head * 0.62 * math.sin(angle), y2 - head * math.sin(angle) + head * 0.62 * math.cos(angle))
        self.polygon([(x2, y2), left, right], color, stroke=color, width=width * 0.5)

    def badge(self, cx: float, cy: float, r: float, *, ok: bool, fill: str) -> None:
        """A round check or cross badge with a white ring, like a status sticker."""
        self.circle(cx, cy, r + r * 0.16, self.colors.card, shadow="lift")
        self.circle(cx, cy, r, fill)
        mark = WHITE if luminance(fill) < 0.45 else "#14101f"
        w = r * 0.24
        if ok:
            self.path(
                f"M{cx - r * 0.42:.1f},{cy + r * 0.02:.1f} L{cx - r * 0.1:.1f},{cy + r * 0.32:.1f} L{cx + r * 0.44:.1f},{cy - r * 0.3:.1f}",
                stroke=mark,
                width=w,
            )
        else:
            k = r * 0.34
            self.line(cx - k, cy - k, cx + k, cy + k, mark, w)
            self.line(cx - k, cy + k, cx + k, cy - k, mark, w)

    # -- text --------------------------------------------------------------------------------------------------------

    def text(
        self,
        box: Box,
        text: str,
        style: Style,
        *,
        align: str = "center",
        valign: str = "center",
        group: str = "",
        rotate: float = 0,
    ) -> None:
        if text.strip():
            self._pending.append(_Pending(box, " ".join(text.split()), style, align, valign, group, rotate))

    def fit(self, text: str, w: float, h: float, s: Style) -> Fitted:
        """How ``text`` would fit a ``w`` x ``h`` box (for layouts that size boxes to their words)."""
        return fit_text(_MEASURE, " ".join(text.split()), max(1, int(w)), max(1, int(h)), s, min_size=MIN_TEXT)

    def fit_many(self, texts: list[str], w: float, h: float, s: Style) -> tuple[int, int]:
        """The shared size at which every text fits ``w`` x ``h``, and the tallest block at that size."""
        texts = [t for t in texts if t.strip()]
        if not texts:
            return s.max_size, 0
        size = min(self.fit(t, w, h, s).size for t in texts)
        capped = replace(s, max_size=size)
        return size, max(self.fit(t, w, h, capped).height for t in texts)

    def _fit(self, item: _Pending, cap: int | None = None) -> Fitted:
        w, h = int(item.box[2]), int(item.box[3])
        return fit_text(_MEASURE, item.text, max(1, w), max(1, h), item.style, min_size=MIN_TEXT, max_size=cap)

    def _write_text(self) -> str:
        caps: dict[str, int] = {}
        for item in self._pending:
            if item.group:
                size = self._fit(item).size
                caps[item.group] = min(size, caps.get(item.group, size))
        out = []
        self.placed = []
        for item in self._pending:
            fitted = self._fit(item, caps.get(item.group))
            self.placed.append(Placed(item.box, item.text, item.style, fitted, item.align, item.valign, item.rotate))
            out.append(_svg_text(item, fitted))
        return "".join(out)

    # -- output ------------------------------------------------------------------------------------------------------

    def svg(self) -> str:
        c = self.colors
        shade = 0.42 if c.dark else 0.1
        lift = 0.5 if c.dark else 0.16
        defs = (
            "<defs>"
            f'<filter id="soft" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="18" '
            f'flood-color="{c.shadow}" flood-opacity="{shade}"/></filter>'
            f'<filter id="lift" x="-40%" y="-40%" width="180%" height="190%"><feDropShadow dx="0" dy="4" stdDeviation="5" '
            f'flood-color="{c.shadow}" flood-opacity="{lift}"/></filter>'
            f'<radialGradient id="glow"><stop offset="0" stop-color="{c.sch.glow}" stop-opacity="0.55"/>'
            f'<stop offset="1" stop-color="{c.sch.glow}" stop-opacity="0"/></radialGradient>'
            "</defs>"
        )
        text = self._write_text()
        return (
            f'<svg xmlns="{SVG_NS}" width="{self.width}" height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            f'{defs}<rect width="{self.width}" height="{self.height}" fill="{c.bg}"/>{"".join(self.shapes)}{text}</svg>'
        )

    def png(self) -> tuple[bytes, int, int]:
        return svg_to_png(self.svg(), width=self.width, background=self.colors.bg)


def polar(cx: float, cy: float, r: float, degrees: float) -> tuple[float, float]:
    """The point at ``degrees`` (0 = 12 o'clock, clockwise) on a circle."""
    a = math.radians(degrees)
    return cx + r * math.sin(a), cy - r * math.cos(a)


def _svg_text(item: _Pending, fitted: Fitted) -> str:
    x, y, w, h = item.box
    family, weight = _FONTS.get(item.style.font, ("Inter", 400))
    anchor = {"left": "start", "right": "end"}.get(item.align, "middle")
    tx = x if item.align == "left" else x + w if item.align == "right" else x + w / 2
    top = y + (h - fitted.height) / 2 if item.valign == "center" else y + h - fitted.height if item.valign == "bottom" else y
    lines = []
    for i, line in enumerate(fitted.lines):
        # Center each line's cap height in its slot (Inter's cap height is 0.727 em).
        base = top + i * fitted.line_height + fitted.line_height / 2 + fitted.size * 0.36
        lines.append(f'<tspan x="{tx:.1f}" y="{base:.1f}">{esc(line)}</tspan>')
    rotate = ""
    if item.rotate:
        rotate = f' transform="rotate({item.rotate:g} {x + w / 2:.1f} {y + h / 2:.1f})"'
    return (
        f'<text font-family="{family}" font-weight="{weight}" font-size="{fitted.size}" fill="{item.style.fill}" '
        f'text-anchor="{anchor}"{rotate}>{"".join(lines)}</text>'
    )


def style(font: str, fill: str, size: int, spacing: float = 1.18) -> Style:
    return Style(font, fill, size, line_spacing=spacing)


def restyle(s: Style, **changes: object) -> Style:
    return replace(s, **changes)  # type: ignore[arg-type]


def frame(board: Board, title: str, credit: str | None) -> float:
    """The shared frame: an optional title top-left and the credit bottom-right. Returns the y where the body starts."""
    c = board.colors
    if credit and credit.strip():
        board.text((board.width - MARGIN - 420, board.height - 48, 420, 30), credit.strip(), style("regular", c.muted, 22), align="right")
    if title.strip():
        board.rect((MARGIN, 52, 64, 7), c.solid(c.at(0.55)), rx=3.5)
        board.text((MARGIN, 70, board.width - 2 * MARGIN, 58), title, style("heavy", c.ink, 44), align="left")
        return 150
    return 56

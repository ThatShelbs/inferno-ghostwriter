"""The diagram templates: code-drawn layouts in a clean Medium style that Claude fills with words.

Every template is 1400 px wide (2x a Medium column) at a fixed height chosen for its shape (see ``TEMPLATES``):
a flat surface from the scheme, white rounded cards with soft shadows, pill labels, ramp colors and generous
whitespace, with the author's credit handle bottom-right. Nothing here calls a model.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from inferno_ghostwriter.images.diagrams.board import (
    BLACK,
    MARGIN,
    WHITE,
    Board,
    Box,
    Colors,
    esc,
    frame,
    polar,
    style,
)
from inferno_ghostwriter.images.diagrams.specs import (
    DiagramSpec,
    Glyph,
    HubSpoke,
    LayerStack,
    Matrix2x2,
    NestedRings,
    Pipeline,
    RadialBars,
    Timeline,
    Venn,
    WinnerCard,
    parse_diagram,
)
from inferno_ghostwriter.images.palettes import Scheme, mix

W = 1400


def _pick(index: int | None, n: int) -> int | None:
    return index if index is not None and 0 <= index < n else None


def fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):,}"
    return f"{value:,.1f}" if abs(value) >= 10 else f"{value:.2g}"


def pill(
    b: Board,
    cx: float,
    cy: float,
    text: str,
    *,
    size: int,
    fill: str,
    color: str,
    stroke: str = "",
    max_w: float = 420,
    pad: float = 22,
    font: str = "bold",
    shadow: str = "lift",
) -> Box:
    """A rounded-full label sized to its text (measured first), centered on (cx, cy). Returns its box."""
    s = style(font, color, size)
    h = round(size * 1.9)
    fitted = b.fit(text, max_w - 2 * pad, size * 1.3, s)
    w = min(max_w, fitted.width + 2 * pad + 2)
    box = (cx - w / 2, cy - h / 2, w, h)
    b.rect(box, fill, rx=h / 2, stroke=stroke, stroke_width=3 if stroke else 0, shadow=shadow)
    b.text((box[0] + pad, cy - size * 0.68, w - 2 * pad, size * 1.36), text, style(font, color, fitted.size))
    return box


# -- mini charts for cards ----------------------------------------------------------------------------------------------


def glyph(b: Board, kind: Glyph, box: Box, colors: list[str], *, muted: bool = False) -> None:
    c = b.colors
    x, y, w, h = box
    tone = [c.grey] * len(colors) if muted else colors
    if kind == "bars":
        heights = (0.42, 0.68, 0.52, 1.0, 0.78, 0.5)
        n = len(heights)
        gap = w * 0.06
        bw = (w - gap * (n + 1)) / n
        for i, k in enumerate(heights):
            bh = (h - 10) * k
            b.rect((x + gap + i * (bw + gap), y + h - 6 - bh, bw, bh), tone[i % len(tone)], rx=min(6, bw / 4))
        b.line(x, y + h - 3, x + w, y + h - 3, c.faint if muted else c.muted, 3)
    elif kind == "radial":
        cx, cy, r = x + w / 2, y + h / 2, min(w, h) / 2
        sweeps = (300, 250, 205, 160, 110)
        pitch = r * 0.62 / len(sweeps)
        for i, sweep in enumerate(sweeps):
            rr = r - pitch * (i + 0.5)
            b.arc(cx, cy, rr, 0, 359.99, c.track, pitch * 0.5)
            b.arc(cx, cy, rr, 0, sweep, tone[i % len(tone)], pitch * 0.62)
        core = r * 0.3
        b.circle(cx, cy, core * 1.25, "url(#glow)")
        b.circle(cx, cy, core * 0.62, c.grey if muted else c.sch.glow)
    elif kind == "line":
        pts = [(0.0, 0.7), (0.17, 0.55), (0.33, 0.62), (0.5, 0.36), (0.67, 0.42), (0.83, 0.18), (1.0, 0.1)]
        xy = [(x + 12 + px * (w - 24), y + 10 + py * (h - 20)) for px, py in pts]
        area = " ".join(f"L{px:.1f},{py:.1f}" for px, py in xy)
        b.path(f"M{xy[0][0]:.1f},{y + h:.1f} {area} L{xy[-1][0]:.1f},{y + h:.1f} Z", fill=c.tint(tone[0], 0.75))
        b.path("M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in xy), stroke=tone[0], width=6)
        for px, py in xy:
            b.circle(px, py, 8, c.card, stroke=tone[0], stroke_width=4)
    elif kind == "dots":
        clusters = ((0.25, 0.65), (0.55, 0.35), (0.8, 0.7))
        offsets = ((0, 0), (-0.08, 0.1), (0.09, 0.08), (0.04, -0.12), (-0.1, -0.06), (0.12, -0.02), (-0.03, 0.15))
        for k, (ux, uy) in enumerate(clusters):
            for j, (ox, oy) in enumerate(offsets):
                rr = min(w, h) * (0.035 + 0.012 * ((j * 7 + k) % 3))
                b.circle(x + (ux + ox) * w, y + (uy + oy) * h, rr, tone[k % len(tone)])
    else:  # donut
        cx, cy, r = x + w / 2, y + h / 2, min(w, h) / 2 * 0.86
        shares = (0.42, 0.27, 0.19, 0.12)
        start = 0.0
        for i, share in enumerate(shares):
            end = start + share * 360
            b.arc(cx, cy, r * 0.78, start + 1.5, end - 1.5, tone[i % len(tone)], r * 0.44, cap="butt")
            start = end


# -- the templates ----------------------------------------------------------------------------------------------------


def nested_rings(b: Board, s: NestedRings, top: float) -> None:
    """Concentric circles that share a bottom point, broadest outside (the AI ⊃ ML ⊃ DL picture)."""
    c = b.colors
    n = len(s.items)
    hi = _pick(s.highlight, n)
    bottom = b.height - 82
    big = min((bottom - top) / 2, 540)
    cx = b.width / 2
    small = big * max(0.24, 0.62 - 0.075 * n)
    radii = [big - i * (big - small) / (n - 1) for i in range(n)]
    fills = c.seq(n + 1)[:n] if not c.dark else c.seq(n)
    if not c.dark:
        fills[-1] = mix(fills[-1], WHITE, 0.72)
    b.circle(cx, bottom - big, big, fills[0], shadow="soft")
    for r, fill in zip(radii, fills, strict=True):
        b.circle(cx, bottom - r, r, fill, stroke=c.card if not c.dark else c.bg, stroke_width=5)
    band = 2 * (big - small) / (n - 1)
    for i, (item, r, fill) in enumerate(zip(s.items, radii, fills, strict=True)):
        ink = c.on(fill)
        if i < n - 1:
            y0 = bottom - 2 * r + band * 0.12
            h = band * 0.76
            half = math.sqrt(max(0.0, r * r - (bottom - r - (y0 + h * 0.12)) ** 2))
            w = min(2 * half * 0.86, 2 * radii[i + 1] * 1.1)
            box: Box = (cx - w / 2, y0, w, h)
        else:
            w, h = r * 1.4, r * 0.86
            box = (cx - w / 2, bottom - r - h / 2, w, h)
        label_h = box[3] * (0.6 if item.note else 1)
        label_box: Box = (box[0], box[1], box[2], label_h)
        size = 42 if i < 2 else 36
        if hi == i:
            room = 2 * radii[i + 1] * 0.95 if i < n - 1 else box[2]
            fitted = b.fit(item.label, room - 56, min(label_h, 64), style("bold", ink, 36))
            pw, ph = fitted.width + 56, fitted.height + 22
            py = box[1] + (label_h - ph) / 2
            b.rect((cx - pw / 2, py, pw, ph), c.card, rx=ph / 2, shadow="lift")
            b.text((cx - pw / 2 + 28, py + 11, pw - 56, ph - 22), item.label, style("bold", c.solid(fills[i]), fitted.size))
        else:
            b.text(label_box, item.label, style("bold", ink, size, 1.1))
        if item.note:
            b.text((box[0], box[1] + label_h, box[2], box[3] - label_h), item.note, style("regular", mix(ink, fill, 0.18), 26, 1.2))


def radial_bars(b: Board, s: RadialBars, top: float) -> None:
    """Concentric progress arcs (a radial bar chart) in a card, with one item called out beside it."""
    c = b.colors
    n = len(s.items)
    card: Box = (MARGIN, top, b.width - 2 * MARGIN, b.height - 76 - top)
    b.rect(card, c.card, rx=30, shadow="soft")
    x0, y0, cw, ch = card
    big = min((ch - 84) / 2, 320)
    cx, cy = x0 + cw * 0.38, y0 + ch / 2
    inner = big * 0.34
    pitch = (big - inner) / n
    width = pitch * 0.66
    top_value = max((item.value for item in s.items), default=1) or 1
    colors = c.seq(n)
    for i, item in enumerate(s.items):
        r = big - pitch * (i + 0.5)
        b.arc(cx, cy, r, 0, 270, c.track, width)
        b.arc(cx, cy, r, 0, max(2.0, 270 * max(0.0, item.value) / top_value), colors[i], width)
        lx = x0 + 40
        b.text(
            (lx, cy - r - pitch * 0.42, cx - 20 - lx, pitch * 0.84),
            f"{item.label}  {fmt(item.value)}{s.unit}",
            style("bold", c.ink, min(30, int(pitch * 0.5))),
            align="right",
            group="labels",
        )
    b.circle(cx, cy, inner * 0.98, "url(#glow)")
    core = inner * 0.6
    b.circle(cx, cy, core, c.sch.glow)
    if s.center:
        b.text((cx - core * 0.8, cy - core * 0.5, core * 1.6, core), s.center, style("bold", c.on(c.sch.glow), 30))
    k = _pick(s.highlight, n)
    if k is None:
        k = max(range(n), key=lambda i: s.items[i].value)
    item = s.items[k]
    rx = cx + big + 80
    rw = x0 + cw - 56 - rx
    b.rect((rx, cy - 150, 72, 10), colors[k], rx=5)
    b.text((rx, cy - 126, rw, 130), f"{fmt(item.value)}{s.unit}", style("heavy", c.solid(colors[k]), 120, 1.0), align="left")
    b.text((rx, cy + 12, rw, 56), item.label, style("bold", c.ink, 40), align="left")
    if item.note:
        b.text((rx, cy + 76, rw, 110), item.note, style("regular", c.muted, 28, 1.28), align="left", valign="top")


def winner_card(b: Board, s: WinnerCard, top: float) -> None:
    """One raised, colored card (the winner, with a check) among greyed alternatives (with crosses)."""
    c = b.colors
    n = len(s.options)
    win = _pick(s.winner, n) or 0
    losers = [i for i in range(n) if i != win]
    ww, wh = 540, min(470, b.height - 120 - top)
    wx, wy = (b.width - ww) / 2, top + (b.height - 120 - top - wh) / 2 + 6
    base = wy + wh - 58
    b.line(MARGIN, base, b.width - MARGIN, base, c.track if not c.dark else c.grey, 4)
    lw, lh, gap = 158, 206, 16
    left = losers[: (len(losers) + 1) // 2]
    right = losers[(len(losers) + 1) // 2 :]
    slots: list[tuple[int, float]] = []
    for j, i in enumerate(reversed(left)):
        slots.append((i, wx - 30 - lw - j * (lw + gap)))
    for j, i in enumerate(right):
        slots.append((i, wx + ww + 30 + j * (lw + gap)))
    lcard = mix(c.bg, c.card, 0.55)
    for i, x in slots:
        option = s.options[i]
        y = base - lh
        b.rect((x, y, lw, lh), lcard, rx=12, stroke=c.edge, stroke_width=2)
        glyph(b, option.glyph or "bars", (x + 22, y + 36, lw - 44, lh - 56), [c.grey], muted=True)
        b.badge(x + lw - 6, y + 8, 19, ok=False, fill=c.grey)
        b.text((x - 6, base + 14, lw + 12, 60), option.label, style("bold", c.muted, 24, 1.1), valign="top", group="losers")
    option = s.options[win]
    b.rect((wx, wy, ww, wh), c.card, rx=22, shadow="soft")
    colors = c.seq(5)
    glyph_box: Box = (wx + 70, wy + 44, ww - 140, wh - (200 if option.note else 150))
    glyph(b, option.glyph or "radial", glyph_box, colors)
    label_y = glyph_box[1] + glyph_box[3] + 22
    b.text((wx + 36, label_y, ww - 72, 52), option.label, style("bold", c.ink, 38), group="")
    if option.note:
        b.text((wx + 44, label_y + 56, ww - 88, wy + wh - label_y - 76), option.note, style("regular", c.muted, 26, 1.22), valign="top")
    b.badge(wx + ww - 4, wy + 6, 34, ok=True, fill=c.solid(c.at(0.62)))


def pipeline(b: Board, s: Pipeline, top: float) -> None:
    """Numbered step cards left to right, joined by arrows."""
    c = b.colors
    n = len(s.steps)
    hi = _pick(s.highlight, n)
    gap = 54
    cw = (b.width - 2 * MARGIN - (n - 1) * gap) / n
    cy0 = top + 36
    ch = b.height - 80 - cy0
    colors = c.seq(n)
    inner = cw - 56
    label_style = style("bold", c.ink, 34, 1.1)
    size, label_h = b.fit_many([st.label for st in s.steps], inner, 84, label_style)
    for i, step in enumerate(s.steps):
        x = MARGIN + i * (cw + gap)
        fill = colors[i] if hi == i else c.card
        ink = c.on(fill) if hi == i else c.ink
        note_ink = mix(ink, fill, 0.15) if hi == i else c.muted
        b.rect((x, cy0, cw, ch), fill, rx=26, shadow="soft")
        if hi != i:
            b.rect((x + 28, cy0 + ch - 18, cw - 56, 6), c.tint(colors[i], 0.45), rx=3)
        dot = c.card if hi == i else colors[i]
        b.circle(x + 56, cy0, 31, dot, stroke=c.bg, stroke_width=6)
        b.text((x + 32, cy0 - 22, 48, 44), str(i + 1), style("heavy", c.solid(colors[i]) if hi == i else c.on(dot), 30))
        b.text((x + 28, cy0 + 52, inner, label_h), step.label, style("bold", ink, size, 1.1), align="left", valign="top")
        if step.note:
            ny = cy0 + 52 + label_h + 14
            b.text(
                (x + 28, ny, inner, cy0 + ch - 36 - ny),
                step.note,
                style("regular", note_ink, 25, 1.3),
                align="left",
                valign="top",
                group="note",
            )
        if i < n - 1:
            ay = cy0 + ch / 2
            b.arrow(x + cw + 12, ay, x + cw + gap - 10, ay, c.faint, 5)


def layer_stack(b: Board, s: LayerStack, top: float) -> None:
    """Stacked isometric slabs (top layer first) with labels on leader lines."""
    c = b.colors
    n = len(s.layers)
    hi = _pick(s.highlight, n)
    bottom = b.height - 84
    avail = bottom - top
    thick = 24.0
    k = 0.6
    pitch = min(165.0, (avail - thick - 30) / (n - 1 + 2 * k))
    half_h = min(k * pitch, 100.0)
    half_w = min(half_h * 2.6, 290.0)
    total = (n - 1) * pitch + 2 * half_h + thick
    y0 = top + (avail - total) / 2
    cx = MARGIN + 320
    colors = c.seq(n, reverse=not c.dark)
    centers = [y0 + half_h + i * pitch for i in range(n)]
    floor = centers[-1] + half_h + thick
    b.add(
        f'<ellipse cx="{cx:.1f}" cy="{floor + 4:.1f}" rx="{half_w * 0.8:.1f}" ry="{half_h * 0.32:.1f}" fill="{BLACK}" '
        f'fill-opacity="{0.3 if c.dark else 0.07}" filter="url(#soft)"/>'
    )
    for i in reversed(range(n)):
        yc, col = centers[i], colors[i]
        x = cx
        b.polygon([(x - half_w, yc), (x, yc + half_h), (x, yc + half_h + thick), (x - half_w, yc + thick)], mix(col, BLACK, 0.18))
        b.polygon([(x, yc + half_h), (x + half_w, yc), (x + half_w, yc + thick), (x, yc + half_h + thick)], mix(col, BLACK, 0.34))
        top_face = [(x, yc - half_h), (x + half_w, yc), (x, yc + half_h), (x - half_w, yc)]
        if hi == i:
            b.polygon(top_face, col, stroke=c.card, width=6, shadow="lift")
        else:
            b.polygon(top_face, col)
    lx = cx + 290 + 120
    lw = b.width - MARGIN - lx
    row_h = min(pitch - 8, 118.0)
    label_style = style("bold", c.ink, 36, 1.05)
    size, _ = b.fit_many(
        [layer.label for layer in s.layers], lw - 70, row_h * (0.52 if any(x.note for x in s.layers) else 0.6), label_style
    )
    for i, layer in enumerate(s.layers):
        yc, col = centers[i], colors[i]
        b.line(cx + half_w + 14, yc, lx - 12, yc, c.faint, 3, dash="2 9")
        b.circle(cx + half_w, yc, 6, c.solid(col))
        tag = col if hi == i else c.card
        b.circle(lx + 26, yc, 25, tag, stroke=col, stroke_width=4, shadow="lift")
        b.text((lx + 6, yc - 18, 40, 36), str(i + 1), style("heavy", c.on(tag) if hi == i else c.solid(col), 26))
        tx = lx + 70
        ink = c.solid(col) if hi == i else c.ink
        if layer.note:
            b.text(
                (tx, yc - row_h * 0.52, lw - 70, row_h * 0.52), layer.label, style("bold", ink, size, 1.05), align="left", valign="bottom"
            )
            b.text(
                (tx, yc + 6, lw - 70, row_h * 0.48 - 6),
                layer.note,
                style("regular", c.muted, 26, 1.2),
                align="left",
                valign="top",
                group="note",
            )
        else:
            b.text((tx, yc - row_h * 0.3, lw - 70, row_h * 0.6), layer.label, style("bold", ink, size, 1.05), align="left")


def hub_spoke(b: Board, s: HubSpoke, top: float) -> None:
    """A glowing hub with pill-labeled parts around it on dashed spokes."""
    c = b.colors
    n = len(s.spokes)
    hi = _pick(s.highlight, n)
    bottom = b.height - 70
    cx, cy = b.width / 2, top + (bottom - top) / 2 - 6
    rx, ry = b.width / 2 - MARGIN - 180, (bottom - top) / 2 - 96
    hub = min(118.0, ry * 0.5)
    colors = c.seq(n)
    points = []
    for i in range(n):
        a = math.radians(360 * i / n)
        points.append((cx + rx * math.sin(a), cy - ry * math.cos(a)))
    for (px, py), col in zip(points, colors, strict=True):
        b.line(cx, cy, px, py, c.tint(col, 0.35) if not c.dark else mix(col, c.bg, 0.3), 3, dash="3 10")
    b.circle(cx, cy, hub * 1.9, "url(#glow)")
    b.circle(cx, cy, hub + 16, c.card, shadow="soft")
    deep = c.seq(3)[0]
    b.circle(cx, cy, hub, deep)
    b.text((cx - hub * 0.78, cy - hub * 0.5, hub * 1.56, hub), s.hub, style("heavy", c.on(deep), 38, 1.05))
    for i, (spoke, (px, py), col) in enumerate(zip(s.spokes, points, colors, strict=True)):
        d = math.hypot(px - cx, py - cy) or 1
        ux, uy = (px - cx) / d, (py - cy) / d
        b.circle(cx + ux * (hub + 34), cy + uy * (hub + 34), 8, col)
        fill = col if hi == i else c.card
        box = pill(
            b,
            px,
            py,
            spoke.label,
            size=28,
            fill=fill,
            color=c.on(fill) if hi == i else c.solid(col),
            stroke="" if hi == i else col,
            max_w=320,
        )
        if spoke.note:
            below = py >= cy - ry * 0.2
            ny = box[1] + box[3] + 8 if below else box[1] - 8 - 62
            b.text(
                (px - 190, ny, 380, 62), spoke.note, style("regular", c.muted, 24, 1.2), valign="top" if below else "bottom", group="notes"
            )


def matrix_2x2(b: Board, s: Matrix2x2, top: float) -> None:
    """Four quadrant cards on two labeled axes, with optional dots placed on the grid."""
    c = b.colors
    hi = _pick(s.highlight, 4)
    gx = MARGIN + 80.0
    gy = top + 4
    gw = b.width - MARGIN - gx
    gh = b.height - 150 - gy
    gap = 18.0
    cw, ch = (gw - gap) / 2, (gh - gap) / 2
    colors = c.seq(4)
    order = [1, 3, 0, 2]  # top-right gets the boldest color, bottom-left the calmest
    label_style = style("bold", c.ink, 38, 1.08)
    size, label_h = b.fit_many([q.label for q in s.quadrants], cw - 68, 92, label_style)
    note_size, note_h = b.fit_many([q.note for q in s.quadrants], cw - 68, 70, style("regular", c.muted, 26, 1.25))
    header = 30 + label_h + (10 + note_h if note_h else 0) + 24
    for q, item in enumerate(s.quadrants):
        col = colors[order[q]]
        qx, qy = gx + (q % 2) * (cw + gap), gy + (q // 2) * (ch + gap)
        fill = col if hi == q else c.tint(col, 0.86 if not c.dark else 0.8)
        ink = c.on(col) if hi == q else c.solid(col) if not c.dark else c.ink
        b.rect((qx, qy, cw, ch), fill, rx=26, shadow="soft" if hi == q else "")
        b.text((qx + 34, qy + 30, cw - 68, label_h), item.label, style("bold", ink, size, 1.08), align="left", valign="top")
        if item.note:
            note_ink = mix(ink, fill, 0.12) if hi == q else c.muted
            b.text(
                (qx + 34, qy + 40 + label_h, cw - 68, note_h),
                item.note,
                style("regular", note_ink, note_size, 1.25),
                align="left",
                valign="top",
            )
    # Axes outside the grid; rotated texts are laid out unrotated around their centers.
    ax = gx - 30
    b.arrow(ax, gy + gh, ax, gy + 6, c.muted, 4)
    b.text((ax - 34 - gh * 0.3, gy + gh / 2 - 20, gh * 0.6, 40), s.y_axis.name, style("bold", c.ink, 30), rotate=-90)
    span = min(300.0, gh * 0.3)
    b.text((ax - 34 - span / 2, gy + gh - span / 2 - 16, span, 32), s.y_axis.low, style("regular", c.muted, 22), rotate=-90, align="left")
    b.text((ax - 34 - span / 2, gy + span / 2 - 16, span, 32), s.y_axis.high, style("regular", c.muted, 22), rotate=-90, align="right")
    ay = gy + gh + 30
    b.arrow(gx, ay, gx + gw - 6, ay, c.muted, 4)
    b.text((gx + gw / 2 - 300, ay + 14, 600, 40), s.x_axis.name, style("bold", c.ink, 30))
    b.text((gx, ay + 16, 300, 32), s.x_axis.low, style("regular", c.muted, 22), align="left")
    b.text((gx + gw - 300, ay + 16, 300, 32), s.x_axis.high, style("regular", c.muted, 22), align="right")
    deep = c.seq(3)[0] if not c.dark else c.ink

    def place(v: float, start: float, length: float) -> float:
        """A 0-1 position inside one half of the grid, clear of that quadrant's header."""
        half = 0 if v < 0.5 else 1
        t = v * 2 - half
        lo = start + half * (length + gap) + 28
        return lo + t * (length - 56)

    for p in s.points:
        px = place(p.x, gx, cw)
        row = 0 if p.y >= 0.5 else 1
        qy = gy + row * (ch + gap)
        t = (1 - p.y) * 2 - row
        py = qy + header + 10 + t * max(0.0, ch - header - 50)
        b.circle(px, py, 13, deep, stroke=c.card, stroke_width=5, shadow="lift")
        fitted = b.fit(p.label, 260, 30, style("bold", c.ink, 22))
        pw = fitted.width + 36
        right = px + 24 + pw <= (gx + cw if p.x < 0.5 else gx + gw) - 10
        pcx = px + 24 + pw / 2 if right else px - 24 - pw / 2
        pill(b, pcx, py, p.label, size=22, fill=c.card, color=c.ink, max_w=300, pad=18)


def timeline(b: Board, s: Timeline, top: float) -> None:
    """Events on a ramp-colored line, cards alternating above and below."""
    c = b.colors
    n = len(s.events)
    hi = _pick(s.highlight, n)
    bottom = b.height - 70
    mid = top + (bottom - top) / 2
    x0, x1 = MARGIN + 24.0, b.width - MARGIN - 24.0
    span = (x1 - x0) / n
    xs = [x0 + (i + 0.5) * span for i in range(n)]
    colors = c.seq(n)
    b.rect((x0, mid - 5, x1 - x0, 10), c.track, rx=5)
    for i in range(n - 1):
        b.line(xs[i], mid, xs[i + 1], mid, colors[i], 10)
    cw = min(330.0, 2 * span - 26)
    ch = mid - top - 52
    label_style = style("bold", c.ink, 30, 1.1)
    size, label_h = b.fit_many([e.label for e in s.events], cw - 52, 72, label_style)
    for i, ev in enumerate(s.events):
        x, col = xs[i], colors[i]
        above = i % 2 == 0
        y = mid - 52 - ch if above else mid + 52
        left = min(max(x - cw / 2, MARGIN - 30), b.width - MARGIN + 30 - cw)
        b.line(x, mid + (-20 if above else 20), x, y + ch if above else y, c.tint(col, 0.3) if not c.dark else col, 3)
        fill = col if hi == i else c.card
        ink = c.on(fill) if hi == i else c.ink
        b.rect((left, y, cw, ch), fill, rx=22, shadow="soft")
        b.text((left + 26, y + 22, cw - 52, 38), ev.when, style("heavy", ink if hi == i else c.solid(col), 30), align="left", group="when")
        b.text((left + 26, y + 66, cw - 52, label_h), ev.label, style("bold", ink, size, 1.1), align="left", valign="top")
        if ev.note:
            ny = y + 66 + label_h + 10
            b.text(
                (left + 26, ny, cw - 52, y + ch - 20 - ny),
                ev.note,
                style("regular", mix(ink, fill, 0.15) if hi == i else c.muted, 24, 1.28),
                align="left",
                valign="top",
                group="note",
            )
        r = 20 if hi == i else 15
        b.circle(x, mid, r, col if hi == i else c.card, stroke=col, stroke_width=6, shadow="lift")


def venn(b: Board, s: Venn, top: float) -> None:
    """Two or three overlapping circles on white disks; what they share sits in the middle."""
    c = b.colors
    n = len(s.sets)
    hi = _pick(s.highlight, n)
    bottom = b.height - 70
    cx, cy = b.width / 2, top + (bottom - top) / 2
    colors = c.seq(n)
    if n == 2:
        r = min(300.0, (bottom - top) / 2 - 8)
        d = r * 1.12
        centers = [(cx - d / 2, cy), (cx + d / 2, cy)]
        spots = [(cx - d / 2 - r * 0.42, cy), (cx + d / 2 + r * 0.42, cy)]
        width = r * 0.82
        core = (cx, cy)
        core_w = (2 * r - d) * 0.95
    else:
        r = min(272.0, (bottom - top - 12) / 3.0)
        d = r * 0.66
        mid = (cx, cy - d * 0.25)
        angles = (300.0, 60.0, 180.0)
        centers = [polar(mid[0], mid[1], d, a) for a in angles]
        spots = [polar(mid[0], mid[1], d + r * 0.46, a) for a in angles]
        width = r * 1.0
        core = mid
        core_w = r * 1.0
    for x, y in centers:
        b.circle(x, y, r, c.card, shadow="soft")
    for x, y in centers:
        b.circle(x, y, r, c.card)
    for i, ((x, y), col) in enumerate(zip(centers, colors, strict=True)):
        op = (0.3 if c.dark else 0.17) * (1.8 if hi == i else 1)
        b.circle(x, y, r, col, opacity=op)
    for i, ((x, y), col) in enumerate(zip(centers, colors, strict=True)):
        b.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" stroke="{c.solid(col)}" stroke-width="{5 if hi == i else 3}"/>')
    label_style = style("bold", c.ink, 40, 1.05)
    size, _ = b.fit_many([st.label for st in s.sets], width, 92, label_style)
    for item, (x, y), col in zip(s.sets, spots, colors, strict=True):
        ink = c.solid(col) if not c.dark else c.ink
        if item.note:
            b.text((x - width / 2, y - 96, width, 90), item.label, style("bold", ink, size, 1.05), valign="bottom")
            note_ink = c.muted if not c.dark else mix(c.ink, c.bg, 0.2)
            b.text((x - width / 2, y + 2, width, 96), item.note, style("regular", note_ink, 25, 1.22), valign="top", group="note")
        else:
            b.text((x - width / 2, y - 46, width, 92), item.label, style("bold", ink, size, 1.05))
    pill(
        b,
        core[0],
        core[1],
        s.overlap,
        size=28,
        fill=c.seq(3)[0],
        color=c.on(c.seq(3)[0]),
        max_w=max(160.0, core_w),
        pad=22,
        font="heavy",
        shadow="soft",
    )


# -- catalog ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    use_when: str
    height: int
    model: type[BaseModel]
    draw: Callable[[Board, Any, float], None]

    @property
    def width(self) -> int:
        return W

    @property
    def size(self) -> tuple[int, int]:
        return W, self.height


_ALL = [
    Template(
        "nested_rings",
        "Nested rings",
        "one idea contains the next (field, subfield, technique, tool); 2-6 levels",
        1200,
        NestedRings,
        nested_rings,
    ),
    Template(
        "radial_bars",
        "Radial bars",
        "comparing 3-7 values of one measure (scores, shares, latency) with one called out",
        860,
        RadialBars,
        radial_bars,
    ),
    Template(
        "winner_card",
        "Winner card",
        "picking one option over 2-4 alternatives (the chart type, tool or approach that wins)",
        788,
        WinnerCard,
        winner_card,
    ),
    Template("pipeline", "Pipeline", "a process or workflow of 3-6 ordered steps", 540, Pipeline, pipeline),
    Template(
        "layer_stack", "Layer stack", "an architecture or platform built in 3-6 layers, top to foundation", 860, LayerStack, layer_stack
    ),
    Template("hub_spoke", "Hub and spoke", "one central thing with 3-8 parts, sources or consumers around it", 900, HubSpoke, hub_spoke),
    Template(
        "matrix_2x2",
        "2x2 matrix",
        "sorting options on two dimensions (effort vs impact), with optional placed dots",
        1000,
        Matrix2x2,
        matrix_2x2,
    ),
    Template(
        "timeline", "Timeline", "3-7 events or stages in time order (a history, a roadmap, a project's weeks)", 700, Timeline, timeline
    ),
    Template("venn", "Venn", "2-3 overlapping skills, fields or traits and what sits where they meet", 860, Venn, venn),
]
TEMPLATES: dict[str, Template] = {t.id: t for t in _ALL}


def menu() -> str:
    """The templates as a prompt reads them."""
    return "\n".join(f"- `{t.id}`: {t.name}. Use when {t.use_when}." for t in TEMPLATES.values())


def layout_diagram(spec: DiagramSpec | dict[str, Any], sch: Scheme, credit: str | None = None) -> Board:
    """The diagram laid out on its board (shapes and placed text), before any rasterizing."""
    parsed = parse_diagram(spec) if isinstance(spec, dict) else spec
    template = TEMPLATES[parsed.template]
    board = Board(Colors(sch), template.height)
    top = frame(board, parsed.title, credit)
    template.draw(board, parsed, top)
    return board


def render_diagram(spec: DiagramSpec | dict[str, Any], sch: Scheme, credit: str | None = None) -> str:
    """The diagram as an SVG document (1400 px wide; height per template). Text is pre-fitted in the bundled fonts."""
    return layout_diagram(spec, sch, credit).svg()


def render_diagram_png(spec: DiagramSpec | dict[str, Any], sch: Scheme, credit: str | None = None) -> tuple[bytes, int, int]:
    """The diagram rasterized by resvg: (png bytes, width, height)."""
    return layout_diagram(spec, sch, credit).png()


__all__ = ["TEMPLATES", "Template", "esc", "glyph", "layout_diagram", "menu", "render_diagram", "render_diagram_png"]

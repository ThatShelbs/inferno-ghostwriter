"""fluid_ribbons: thick swirling paint ribbons traced through a vortex field, with brush-stroke texture and depth."""

from __future__ import annotations

import math
import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Noise, Svg, backdrop, band, clamp, f, lerp, path_d
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme

Point = tuple[float, float]


def _offset(points: list[Point], d: float) -> list[Point]:
    """``points`` moved ``d`` along their normals (a parallel line)."""
    out = []
    n = len(points)
    for i, (x, y) in enumerate(points):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(n - 1, i + 1)]
        tx, ty = bx - ax, by - ay
        length = math.hypot(tx, ty) or 1.0
        out.append((x - ty / length * d, y + tx / length * d))
    return out


def fluid_ribbons(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    backdrop(svg, pal, cx=0.5, cy=0.5)

    # vortices: one strong one near the focus, a few others around it, alternating spin
    n_vort = params.inputs or rng.randint(3, 5)
    fx = width * lerp(0.25, 0.75, params.focus)
    vortices = [(fx + rng.uniform(-80, 80), (top + bottom) / 2 + rng.uniform(-60, 60), 1.0, rng.choice((-1, 1)))]
    for k in range(n_vort - 1):
        vortices.append(
            (
                rng.uniform(0.05, 0.95) * width,
                rng.uniform(0.1, 0.9) * height,
                rng.uniform(0.45, 0.85),
                -vortices[-1][3] if k % 2 == 0 else vortices[-1][3],
            )
        )
    noise = Noise(rng, octaves=3, scale=0.004)
    swirl = lerp(0.6, 1.5, params.energy)
    drift = rng.uniform(0, math.tau)

    def velocity(x: float, y: float) -> Point:
        vx, vy = math.cos(drift) * 0.6, math.sin(drift) * 0.6
        for cx, cy, strength, spin in vortices:
            dx, dy = x - cx, y - cy
            r2 = dx * dx + dy * dy + 40000.0
            k = strength * spin * swirl * 60000 / r2 * math.exp(-r2 / (2 * 420.0**2))
            vx += -dy * k / 30
            vy += dx * k / 30
        a = noise(x, y) * math.pi
        vx += math.cos(a) * 0.5
        vy += math.sin(a) * 0.5
        return vx, vy

    def trace(x: float, y: float, steps: int) -> list[Point]:
        line = [(x, y)]
        for _ in range(steps):
            vx, vy = velocity(x, y)
            m = math.hypot(vx, vy) or 1.0
            mx, my = x + vx / m * 4, y + vy / m * 4
            vx, vy = velocity(mx, my)
            m = math.hypot(vx, vy) or 1.0
            x, y = x + vx / m * 8, y + vy / m * 8
            if not (-300 < x < width + 300 and -300 < y < height + 300):
                break
            line.append((x, y))
        return line[::4]

    # seeds on a jittered grid so the ribbons cover the whole frame; tiny loops are dropped
    n_ribbons = int(lerp(26, 46, params.density))
    gx = max(2, round((n_ribbons * width / height) ** 0.5))
    gy = max(2, n_ribbons // gx + 1)
    seeds = [
        ((i + rng.random()) / gx * (width + 200) - 100, (j + rng.random()) / gy * (height + 200) - 100)
        for i in range(gx)
        for j in range(gy)
    ]
    rng.shuffle(seeds)
    ribbons: list[tuple[list[Point], float, float]] = []
    hue_field = Noise(rng, octaves=2, scale=0.0018)
    for sx, sy in seeds[:n_ribbons]:
        line = trace(sx, sy, int(rng.uniform(140, 260)))
        if len(line) < 10:
            continue
        xs, ys = [p[0] for p in line], [p[1] for p in line]
        if max(max(xs) - min(xs), max(ys) - min(ys)) < 260:
            continue
        u = clamp(0.5 + 0.35 * hue_field(sx, sy) + rng.uniform(-0.45, 0.45))
        ribbons.append((line, rng.uniform(60, 170) * lerp(0.8, 1.15, params.density), u))

    shadow = "#000000"
    for idx, (line, w, u) in enumerate(ribbons):
        d = path_d(line)
        depth = idx / max(1, len(ribbons) - 1)  # later ribbons sit on top
        base_u = clamp(u * 0.85 + 0.1)
        # a soft shadow lifts the ribbon off the one beneath it
        svg.group(
            [
                f'<path d="{d}" fill="none" stroke="{shadow if pal.dark else pal.ramp(0.05)}" stroke-width="{f(w * 1.12)}" '
                f'stroke-linecap="round" stroke-opacity="{0.55 if pal.dark else 0.18:.2f}"/>'
            ],
            filter_id=svg.blur(14.0),
        )
        parts = [
            f'<path d="{d}" fill="none" stroke="{pal.tone(base_u)}" stroke-width="{f(w)}" stroke-linecap="butt" stroke-linejoin="round"/>'
        ]
        # brush texture: fine parallel strokes across the ribbon in neighbouring colours
        strands = int(lerp(6, 11, params.density))
        for s in range(strands):
            off = (s / max(1, strands - 1) - 0.5) * w * 0.9
            edge = abs(off) / (w / 2)
            tone = clamp(base_u + rng.uniform(-0.22, 0.22) - 0.25 * edge)
            sub = line[rng.randrange(0, 4) :]
            if len(sub) < 3:
                continue
            parts.append(
                f'<path d="{path_d(_offset(sub, off))}" fill="none" stroke="{pal.tone(tone)}" '
                f'stroke-width="{f(rng.uniform(1.5, w / strands * 1.6))}" stroke-opacity="{rng.uniform(0.35, 0.8):.2f}" '
                f'stroke-linecap="round"/>'
            )
        # a highlight along one edge gives the paint a rounded body
        parts.append(
            f'<path d="{path_d(_offset(line, -w * 0.28))}" fill="none" stroke="{pal.tone(min(1.0, base_u + 0.35))}" '
            f'stroke-width="{f(w * 0.08)}" stroke-opacity="0.55" stroke-linecap="round"/>'
        )
        blur = 0.0 if depth > 0.35 else lerp(3.5, 0.8, depth / 0.35)
        svg.group(parts, filter_id=svg.blur(blur) if blur > 0.5 else None)

    specks = []
    for _ in range(int(lerp(60, 180, params.density))):
        r = rng.choice((1.2, 1.6, 2.2, 3.5, 5.0))
        specks.append(
            f'<circle cx="{f(rng.uniform(0, width))}" cy="{f(rng.uniform(0, height))}" r="{r}" '
            f'fill="{pal.tone(rng.uniform(0.4, 1))}" opacity="{rng.uniform(0.4, 0.95):.2f}"/>'
        )
    svg.group(specks, filter_id=svg.glow(1.5, strength=0.8))
    return svg.render()

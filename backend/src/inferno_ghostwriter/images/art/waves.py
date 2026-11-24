"""particle_wave: layered waves of glowing particles flowing across the frame, sharp in the middle distance."""

from __future__ import annotations

import math
import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Svg, backdrop, band, clamp, f, lerp, path_d
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def particle_wave(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    backdrop(svg, pal, cx=lerp(0.3, 0.7, params.focus), cy=0.5, tint=0.25 if pal.dark else 0.06, tint_t=0.35)

    mid = (top + bottom) / 2
    n_lines = int(lerp(36, 70, params.density))
    strands = params.inputs or rng.choice((1, 2, 2))
    # each strand is a family of waves sharing a shape and fanning apart along its length
    families = []
    for s in range(strands):
        families.append(
            {
                "waves": [(rng.uniform(0.002, 0.006) * (1 + k), rng.uniform(0, math.tau), rng.uniform(25, 90) / (1 + k)) for k in range(3)],
                "offset": (s - (strands - 1) / 2) * (bottom - top) * 0.22,
                "tone": lerp(0.55, 1.0, s / max(1, strands - 1)) if strands > 1 else 0.85,
                "pinch": rng.uniform(0.25, 0.75),
            }
        )
    amp = lerp(0.6, 1.6, params.energy)
    focus_x = width * lerp(0.3, 0.7, params.focus)
    layers: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
    lines: list[str] = []
    for fam in families:
        for j in range(n_lines // strands):
            v = j / max(1, n_lines // strands - 1) - 0.5  # -0.5..0.5 across the family
            depth = abs(v) * 2  # 0 at the core of the family
            k = 0 if depth < 0.3 else 1 if depth < 0.6 else 2 if depth < 0.85 else 3
            tone = clamp(float(fam["tone"]) - 0.45 * depth + rng.uniform(-0.05, 0.05))  # type: ignore[arg-type]
            phase = rng.uniform(-0.15, 0.15)
            pts = []
            x = -20.0
            step = lerp(10, 7, params.density)
            while x < width + 20:
                spread = 0.35 + 1.4 * abs(x - width * float(fam["pinch"])) / width  # type: ignore[arg-type]
                y = mid + float(fam["offset"])  # type: ignore[arg-type]
                for kx, p, a in fam["waves"]:  # type: ignore[attr-defined]
                    y += a * amp * math.sin(kx * x + p + phase * depth)
                y += v * (bottom - top) * 0.7 * spread
                pts.append((x, y))
                x += step
            lines.append(
                f'<path d="{path_d(pts[::3])}" fill="none" stroke="{pal.tone(tone)}" stroke-width="0.8" '
                f'stroke-opacity="{lerp(0.25, 0.06, depth):.2f}"/>'
            )
            dots = []
            for px, py in pts:
                if rng.random() > lerp(0.35, 0.8, params.density):
                    continue
                near = 1 - min(1.0, abs(px - focus_x) / width * 1.6)
                r = lerp(0.6, 2.6, near) * rng.uniform(0.6, 1.4) * (1.6 if k == 3 else 1.0)
                op = clamp(lerp(0.3, 1.0, near) * rng.uniform(0.5, 1.0))
                dots.append(f'<circle cx="{f(px)}" cy="{f(py)}" r="{f(r)}" opacity="{op:.1f}"/>')
            layers[k].append(f'<g fill="{pal.tone(tone)}">' + "".join(dots) + "</g>")

    svg.group(lines, filter_id=svg.glow(1.5, strength=0.8))
    svg.group(layers[3], filter_id=svg.blur(5.0))
    svg.group(layers[2], filter_id=svg.blur(2.0))
    svg.group(layers[1], filter_id=svg.glow(1.4, strength=0.8))
    svg.group(layers[0], filter_id=svg.glow(2.2, strength=1.2))

    # a handful of bright sparks riding the core
    sparks = []
    for _ in range(int(lerp(10, 30, params.density))):
        x = rng.uniform(0, width)
        y = mid + rng.gauss(0, (bottom - top) * 0.12)
        sparks.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(rng.uniform(2, 4.5))}" fill="{pal.glow()}"/>')
    svg.group(sparks, filter_id=svg.glow(4.0, strength=1.6))
    return svg.render()

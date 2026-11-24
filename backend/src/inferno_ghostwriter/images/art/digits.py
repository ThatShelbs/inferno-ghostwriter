"""radial_digits: a tunnel of binary marks (rings for 0, dashes for 1) streaming out of a bright centre."""

from __future__ import annotations

import math
import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Noise, Svg, backdrop, clamp, f, lerp
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def radial_digits(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    svg = Svg(width, height)
    cx = width * lerp(0.35, 0.65, params.focus) + rng.uniform(-30, 30)
    cy = height * 0.5 + rng.uniform(-40, 40)
    backdrop(svg, pal, cx=cx / width, cy=cy / height, tint=0.25 if pal.dark else 0.0, tint_t=0.6)

    rays = int(lerp(90, 170, params.density))
    r0 = rng.uniform(70, 110)
    r_max = math.hypot(width, height) * 0.62
    growth = lerp(1.085, 1.06, params.density)
    hue = Noise(rng, octaves=2, scale=1.0)
    twist = lerp(0.0, 0.55, params.energy) * rng.choice((-1, 1))
    gaps = Noise(rng, octaves=3, scale=2.2)

    layers: dict[int, list[str]] = {0: [], 1: [], 2: [], 3: []}
    for i in range(rays):
        base = i / rays * math.tau + rng.uniform(-0.01, 0.01)
        r = r0 * rng.uniform(0.9, 1.4)
        while r < r_max:
            t = max(0.0, (r - r0) / (r_max - r0))
            ang = base + twist * t
            if gaps(math.cos(base) * 1.5, math.sin(base) * 1.5 + t * 2) < -0.35 and rng.random() < 0.85:
                r *= growth
                continue
            size = lerp(3.0, 34, t**1.0)
            x, y = cx + math.cos(ang) * r, cy + math.sin(ang) * r
            if -40 < x < width + 40 and -40 < y < height + 40:
                tone = clamp(0.5 + 0.55 * hue(math.cos(base), math.sin(base)) + rng.uniform(-0.08, 0.08))
                color = pal.tone(lerp(tone, 1.0, 0.25) if pal.dark else tone)
                op = clamp(lerp(0.35, 1.0, min(1.0, t * 3.0)) * rng.uniform(0.7, 1.0))
                deg = math.degrees(ang)
                if rng.random() < 0.5:  # a 0: a ring stretched along the ray
                    mark = (
                        f'<ellipse cx="0" cy="0" rx="{f(size * 0.55)}" ry="{f(size * 0.34)}" fill="none" stroke="{color}" '
                        f'stroke-width="{f(max(0.8, size * 0.13))}"/>'
                    )
                else:  # a 1: a dash along the ray
                    mark = (
                        f'<rect x="{f(-size * 0.5)}" y="{f(-size * 0.08)}" width="{f(size)}" '
                        f'height="{f(max(1.0, size * 0.16))}" rx="{f(size * 0.08)}" fill="{color}"/>'
                    )
                k = 0 if t < 0.32 else 1 if t < 0.55 else 2 if t < 0.8 else 3
                layers[k].append(f'<g transform="translate({f(x)},{f(y)}) rotate({f(deg)})" opacity="{op:.2f}">{mark}</g>')
            r *= growth * rng.uniform(0.98, 1.04)

    svg.group(layers[0], filter_id=svg.glow(1.2, strength=0.7))
    svg.group(layers[1], filter_id=svg.glow(1.6, strength=0.6))
    svg.group(layers[2], filter_id=svg.blur(1.6))
    svg.group(layers[3], filter_id=svg.blur(4.5))
    # the bright core everything streams out of
    core = pal.glow() if pal.dark else "#ffffff"
    svg.radial(
        "core",
        [(0.0, core, 1.0), (0.18, core, 0.75 if pal.dark else 1.0), (0.5, core, 0.18 if pal.dark else 0.6), (1.0, core, 0.0)],
        cx=0.5,
        cy=0.5,
        r=0.5,
    )
    svg.add(f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r0 * (2.2 if pal.dark else 3.0))}" fill="url(#core)"/>')
    # coloured haze drifting over the outer field
    haze = []
    for _ in range(5):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0.4, 0.8) * r_max
        haze.append(
            f'<circle cx="{f(cx + math.cos(a) * d)}" cy="{f(cy + math.sin(a) * d)}" r="{f(rng.uniform(160, 300))}" '
            f'fill="{pal.tone(rng.uniform(0.3, 0.9))}" opacity="{0.16 if pal.dark else 0.12:.2f}"/>'
        )
    svg.group(haze, filter_id=svg.blur(60.0))
    return svg.render()

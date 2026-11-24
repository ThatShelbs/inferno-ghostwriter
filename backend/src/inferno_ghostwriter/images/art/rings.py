"""rings: a tilted wheel of thousands of fanned slivers sweeping the ramp, in concentric rings around a dark core."""

from __future__ import annotations

import math
import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Svg, backdrop, band, clamp, f, lerp
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def _wedge(cx: float, cy: float, r0: float, r1: float, a0: float, a1: float, tilt: float) -> str:
    c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
    return (
        f"M{f(cx + c0 * r0)},{f(cy + s0 * r0 * tilt)}L{f(cx + c0 * r1)},{f(cy + s0 * r1 * tilt)}"
        f"L{f(cx + c1 * r1)},{f(cy + s1 * r1 * tilt)}L{f(cx + c1 * r0)},{f(cy + s1 * r0 * tilt)}Z"
    )


def _sweep(angle: float) -> float:
    """0..1..0 around the circle, so the colours flow all the way round with no hard seam."""
    u = (angle % math.tau) / math.tau
    return 1 - abs(2 * u - 1)


def rings(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    cx = width * lerp(0.35, 0.65, params.focus)
    cy = (top + bottom) / 2 - 10
    backdrop(svg, pal, cx=cx / width, cy=cy / height, tint=0.12 if pal.dark else 0.0, tint_t=0.5)

    tilt = lerp(0.82, 0.55, params.energy)
    r_out = min((bottom - top) / 2 / tilt - 30, width * 0.3)
    r_hole = r_out * rng.uniform(0.14, 0.2)
    n_rings = params.outputs or rng.choice((1, 2, 3))
    thick = lerp(26, 48, params.energy)
    start = rng.uniform(0, math.tau)

    # drop shadow under the wheel
    svg.group(
        [
            f'<ellipse cx="{f(cx + 18)}" cy="{f(cy + thick + 26)}" rx="{f(r_out * 1.02)}" ry="{f(r_out * tilt * 1.02)}" '
            f'fill="#000000" opacity="{0.6 if pal.dark else 0.25:.2f}"/>'
        ],
        filter_id=svg.blur(28.0),
    )
    slivers = int(lerp(180, 360, params.density))
    edges = int(params.inputs or 0)
    bounds = [lerp(r_hole, r_out, i / n_rings) for i in range(n_rings + 1)]

    # the side of the wheel: stacked dark copies of the rim give it thickness
    side = []
    for i in range(slivers):
        a0 = i / slivers * math.tau
        a1 = (i + 1.15) / slivers * math.tau
        if math.sin((a0 + a1) / 2) < -0.05:
            continue
        u = _sweep(a0 - start)
        side.append(f'<path d="{_wedge(cx, cy + thick, r_out - 4, r_out, a0, a1, tilt)}" fill="{pal.tone(clamp(u * 0.9 - 0.15))}"/>')
        for k in range(1, 6):
            yy = cy + thick * k / 6
            side.append(
                f'<path d="{_wedge(cx, yy, r_out - 2, r_out, a0, a1, tilt)}" fill="{pal.tone(clamp(u * 0.95 - 0.05 - 0.04 * k))}"/>'
            )
    svg.group(side, filter_id=svg.blur(0.6))

    top_parts = []
    edge_lines = []
    for ring in range(n_rings):
        r0, r1 = bounds[ring], bounds[ring + 1]
        twist = ring * rng.uniform(0.25, 0.6)
        for i in range(slivers):
            a0 = start + twist + i / slivers * math.tau
            a1 = a0 + math.tau / slivers * 1.25
            u = _sweep(a0 - start)
            # every fifth or so sliver is a lighter sheet edge, like fanned paper
            light = rng.random() < 0.22
            tone = clamp(u + rng.uniform(-0.05, 0.05) + (0.12 if light else 0.0) - (0.08 if rng.random() < 0.2 else 0.0))
            top_parts.append(f'<path d="{_wedge(cx, cy, r0 + 1, r1 - 1, a0, a1, tilt)}" fill="{pal.tone(tone)}"/>')
            if light or (edges and i % max(1, slivers // (edges * 6)) == 0):
                edge_lines.append(
                    f'<line x1="{f(cx + math.cos(a0) * r0)}" y1="{f(cy + math.sin(a0) * r0 * tilt)}" '
                    f'x2="{f(cx + math.cos(a0) * r1)}" y2="{f(cy + math.sin(a0) * r1 * tilt)}" '
                    f'stroke="{pal.tone(min(1.0, tone + 0.25))}" stroke-width="0.7" stroke-opacity="0.7"/>'
                )
    svg.group(top_parts)
    svg.group(edge_lines)
    # shading: a radial gradient darkens toward the core, a sheen lights the near rim
    svg.radial(
        "depth", [(0.0, "#000000", 0.7), (0.3, "#000000", 0.25), (0.75, "#000000", 0.0), (1.0, "#000000", 0.12)], cx=0.5, cy=0.5, r=0.5
    )
    svg.add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(r_out)}" ry="{f(r_out * tilt)}" fill="url(#depth)"/>')
    svg.linear("sheen", [(0.0, "#ffffff", 0.0), (0.6, "#ffffff", 0.0), (1.0, "#ffffff", 0.16)])
    svg.add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(r_out)}" ry="{f(r_out * tilt)}" fill="url(#sheen)"/>')
    # the hole
    svg.add(f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(r_hole)}" ry="{f(r_hole * tilt)}" fill="#000000"/>')
    svg.add(f'<ellipse cx="{f(cx)}" cy="{f(cy + 6)}" rx="{f(r_hole * 0.9)}" ry="{f(r_hole * tilt * 0.7)}" fill="{pal.bg2}" opacity="0.6"/>')
    return svg.render()

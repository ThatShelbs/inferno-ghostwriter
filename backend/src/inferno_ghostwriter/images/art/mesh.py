"""network_mesh: a glowing node mesh rolling away in perspective, sharp in the focal distance, soft near and far."""

from __future__ import annotations

import math
import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Noise, Svg, backdrop, band, clamp, f, lerp
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def network_mesh(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    backdrop(svg, pal, cx=0.5, cy=0.0, tint=0.55 if pal.dark else 0.16, tint_t=rng.uniform(0.3, 0.5))

    noise = Noise(rng, octaves=3, scale=rng.uniform(0.3, 0.55) + 0.3 * params.energy)
    cols = int(lerp(26, 46, params.density))
    rows = int(lerp(16, 26, params.density))
    horizon = top + (bottom - top) * rng.uniform(0.08, 0.3)
    cam_h = rng.uniform(2.2, 3.4)
    fov = width * 0.62
    cx = width * lerp(0.3, 0.7, params.focus)
    z_near, z_far = 1.3, 16.0
    amp = lerp(0.9, 2.0, params.energy) * rng.uniform(0.8, 1.2)
    focal_z = lerp(z_near, z_far, rng.uniform(0.18, 0.3))

    grid: list[list[tuple[float, float, float]]] = []  # (sx, sy, z)
    for j in range(rows):
        z = z_near * (z_far / z_near) ** (j / (rows - 1))
        row = []
        span = (width / fov) * z * 1.25 + 2
        for i in range(cols):
            x = lerp(-span, span, i / (cols - 1)) + rng.uniform(-0.45, 0.45) * 2 * span / cols
            zz = z * (1 + rng.uniform(-0.07, 0.07))
            y = amp * noise(x * 0.35, zz * 0.35) + 0.25 * amp * noise(x * 1.1 + 5, zz * 1.1)
            sx = cx + x * fov / zz
            sy = horizon + (cam_h - y) * fov / zz * 0.42
            row.append((sx, sy, zz))
        grid.append(row)

    def depth_class(z: float) -> int:
        """0 = in focus, 1..3 = increasingly soft."""
        d = abs(math.log(z / focal_z))
        return 0 if d < 0.35 else 1 if d < 0.75 else 2 if d < 1.2 else 3

    layers: dict[int, tuple[list[str], list[str]]] = {k: ([], []) for k in range(4)}
    for j in range(rows):
        for i in range(cols):
            sx, sy, z = grid[j][i]
            nbrs = []
            if i + 1 < cols:
                nbrs.append(grid[j][i + 1])
            if j + 1 < rows:
                nbrs.append(grid[j + 1][i])
                diag = i + 1 if rng.random() < 0.5 else i - 1
                if 0 <= diag < cols:
                    nbrs.append(grid[j + 1][diag])
            near = clamp(1 - math.log(z / z_near) / math.log(z_far / z_near))
            k = depth_class(z)
            color = pal.tone(lerp(0.35, 1.0, near) * rng.uniform(0.85, 1.0))
            fade = clamp(lerp(0.12, 1.0, near**0.7))
            for nx, ny, _ in nbrs:
                if -200 < sx < width + 200 and -200 < sy < height + 200:
                    layers[k][0].append(
                        f'<line x1="{f(sx)}" y1="{f(sy)}" x2="{f(nx)}" y2="{f(ny)}" stroke="{color}" '
                        f'stroke-opacity="{0.55 * fade:.2f}" stroke-width="{f(lerp(0.6, 2.2, near))}"/>'
                    )
            if -50 < sx < width + 50 and -50 < sy < height + 50:
                r = lerp(1.4, 9.0, near**1.3) * rng.uniform(0.6, 1.3)
                bright = pal.tone(min(1.0, lerp(0.6, 1.0, near) + 0.1))
                layers[k][1].append(f'<circle cx="{f(sx)}" cy="{f(sy)}" r="{f(r)}" fill="{bright}" opacity="{min(1.0, 0.35 + fade):.2f}"/>')

    # far to near: very soft, soft, in focus with a glow, then the near blur over the top
    blur_of = {3: 7.0, 2: 3.2, 1: 1.3}
    for k in (3, 2, 1):
        lines, nodes = layers[k]
        fid = svg.blur(blur_of[k])
        svg.group(lines + nodes, filter_id=fid, opacity=0.9)
    lines, nodes = layers[0]
    svg.group(lines, filter_id=svg.glow(2.0, strength=0.8))
    svg.group(nodes, filter_id=svg.glow(4.0, strength=1.6))
    # dust drifting in the air above the mesh
    dust = [
        f'<circle cx="{f(rng.uniform(0, width))}" cy="{f(rng.uniform(0, horizon + 80))}" r="{f(rng.uniform(0.6, 2.0))}" '
        f'fill="{pal.tone(rng.uniform(0.6, 1))}" opacity="{rng.uniform(0.15, 0.6):.2f}"/>'
        for _ in range(int(lerp(40, 120, params.density)))
    ]
    svg.group(dust, filter_id=svg.glow(1.2, strength=0.8))

    # floating bokeh: a few big soft out-of-focus nodes in the foreground
    bokeh = []
    for _ in range(int(lerp(6, 16, params.density))):
        x, y = rng.uniform(0, width), rng.uniform(bottom - 60, height + 40)
        bokeh.append(
            f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(rng.uniform(10, 34))}" fill="{pal.tone(rng.uniform(0.6, 1))}" '
            f'opacity="{rng.uniform(0.15, 0.4):.2f}"/>'
        )
    svg.group(bokeh, filter_id=svg.blur(12.0))
    return svg.render()

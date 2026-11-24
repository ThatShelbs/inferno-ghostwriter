"""fan_streams: a few glowing bundles of fine threads fan out and dissolve into a field of data pixels."""

from __future__ import annotations

import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Svg, backdrop, band, clamp, f, lerp, smoothstep
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def fan_streams(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    split = width * lerp(0.4, 0.58, params.focus)  # where the threads meet the field
    backdrop(svg, pal, cx=split / width, cy=0.5, tint=0.22 if pal.dark else 0.08, tint_t=0.3)

    n_in = params.inputs or rng.choice((3, 3, 4))
    n_bands = params.outputs or 1
    mid = (top + bottom) / 2
    spread_in = (bottom - top) * lerp(0.42, 0.6, rng.random())
    sources = [mid + (k - (n_in - 1) / 2) * spread_in / max(1, n_in - 1) for k in range(n_in)] if n_in > 1 else [mid]
    src_x = width * lerp(0.17, 0.28, params.focus)
    field_top, field_bottom = top + 10, bottom - 10
    colors = [pal.tone(lerp(0.45, 1.0, k / max(1, n_in - 1))) for k in range(n_in)]
    rng.shuffle(colors)

    # the field's rows, grouped into bands with gaps between
    cell = lerp(9.0, 6.0, params.density)
    rows = int((field_bottom - field_top) / cell)
    gap_rows = max(1, rows // 30) if n_bands > 1 else 0
    band_rows: list[int] = []
    per = (rows - gap_rows * (n_bands - 1)) // n_bands
    for b in range(n_bands):
        start = b * (per + gap_rows)
        band_rows.extend(range(start, start + per))

    threads_per = int(lerp(26, 60, params.density))
    sharp: list[str] = []
    soft: list[str] = []
    ends_by_row: dict[int, list[int]] = {}
    for k, sy in enumerate(sources):
        lo = int(len(band_rows) * k / n_in)
        hi = int(len(band_rows) * (k + 1) / n_in)
        for t in range(threads_per):
            # each bundle fans over its share of the field and overlaps its neighbours
            u = (t + rng.random()) / threads_per
            row_idx = band_rows[min(len(band_rows) - 1, max(0, int(lerp(lo - (hi - lo) * 0.35, hi + (hi - lo) * 0.35, u))))]
            ey = field_top + row_idx * cell + cell / 2
            ends_by_row.setdefault(row_idx, []).append(k)
            c1x = lerp(src_x, split, rng.uniform(0.35, 0.55))
            c2x = lerp(src_x, split, rng.uniform(0.55, 0.8))
            d = f"M{f(src_x)},{f(sy)}C{f(c1x)},{f(sy)} {f(c2x)},{f(ey)} {f(split)},{f(ey)}"
            w = rng.uniform(0.5, 1.4)
            op = rng.uniform(0.35, 0.85)
            shade = pal.tone(clamp(lerp(0.45, 1.0, (k + 0.5) / n_in) + rng.uniform(-0.12, 0.12)))
            (sharp if rng.random() < 0.75 else soft).append(
                f'<path d="{d}" fill="none" stroke="{shade if rng.random() < 0.3 else colors[k]}" stroke-width="{f(w)}" '
                f'stroke-opacity="{op:.2f}"/>'
            )

    # incoming streaks: dashed glowing lines from the left edge into each source
    streaks: list[str] = []
    for k, sy in enumerate(sources):
        x = 0.0
        while x < src_x - 8:
            seg = rng.uniform(4, 26) * lerp(0.4, 1.0, x / src_x)
            a = clamp(x / src_x) ** 1.6
            streaks.append(
                f'<rect x="{f(x)}" y="{f(sy - 1.6)}" width="{f(seg)}" height="3.2" rx="1.6" fill="{colors[k]}" '
                f'opacity="{lerp(0.1, 0.95, a):.2f}"/>'
            )
            x += seg + rng.uniform(4, 30) * (1 - 0.6 * a)
        streaks.append(f'<circle cx="{f(src_x)}" cy="{f(sy)}" r="5" fill="{pal.glow()}"/>')

    # the pixel field: dense at the seam, thinning to the right edge
    pixels_sharp: list[str] = []
    pixels_soft: list[str] = []
    for row_idx in band_rows:
        y = field_top + row_idx * cell
        owners = ends_by_row.get(row_idx) or ends_by_row.get(row_idx - 1) or [rng.randrange(n_in)]
        x = split + 4
        while x < width:
            depth = (x - split) / (width - split)
            keep = lerp(0.9, 0.05, smoothstep(depth) ** 0.8) * lerp(0.55, 1.0, params.density)
            if rng.random() < keep:
                k = rng.choice(owners) if rng.random() < 0.7 else rng.randrange(n_in)
                tone = clamp(lerp(0.45, 1.0, (k + 0.5) / n_in) + rng.uniform(-0.3, 0.2))
                size = cell * rng.uniform(0.45, 0.85)
                op = lerp(1.0, 0.25, depth) * rng.uniform(0.5, 1.0)
                cell_svg = f'<rect x="{f(x)}" y="{f(y)}" width="{f(size)}" height="{f(size)}" fill="{pal.tone(tone)}" opacity="{op:.2f}"/>'
                (pixels_sharp if depth < 0.5 or rng.random() < 0.4 else pixels_soft).append(cell_svg)
            x += cell * (1 + depth * rng.uniform(0, 1.6))

    svg.group(soft + pixels_soft, filter_id=svg.blur(2.2))
    svg.group(sharp, filter_id=svg.glow(1.8, strength=0.9))
    svg.group(pixels_sharp, filter_id=svg.glow(2.4, strength=0.7))
    svg.group(streaks, filter_id=svg.glow(3.0, strength=1.4))
    # a soft light at the seam where everything meets
    svg.radial("seam", [(0.0, pal.glow(), 0.35 if pal.dark else 0.15), (1.0, pal.glow(), 0.0)], cx=0.5, cy=0.5, r=0.5)
    svg.add(f'<ellipse cx="{f(split)}" cy="{f(mid)}" rx="90" ry="{f((bottom - top) / 2)}" fill="url(#seam)"/>')
    return svg.render()

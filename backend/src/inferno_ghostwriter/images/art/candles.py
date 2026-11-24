"""glow_candles: market-style candlesticks glowing in layers of depth, with bokeh and falling digit columns."""

from __future__ import annotations

import random

from inferno_ghostwriter.images.art.canvas import ArtPalette, Svg, backdrop, band, clamp, f, lerp
from inferno_ghostwriter.images.art.specs import DataArtSpec
from inferno_ghostwriter.images.palettes import Scheme


def _series(rng: random.Random, n: int, vol: float) -> list[tuple[float, float, float, float]]:
    """A random walk as open/high/low/close, normalised to 0..1."""
    price = 0.0
    drift = rng.uniform(-0.02, 0.05)
    out = []
    for _ in range(n):
        o = price
        c = o + rng.gauss(drift, vol)
        h = max(o, c) + abs(rng.gauss(0, vol * 0.7))
        lo = min(o, c) - abs(rng.gauss(0, vol * 0.7))
        out.append((o, h, lo, c))
        price = c
    lo_all = min(x[2] for x in out)
    hi_all = max(x[1] for x in out)
    span = (hi_all - lo_all) or 1.0
    return [tuple((v - lo_all) / span for v in x) for x in out]  # type: ignore[misc]


def glow_candles(params: DataArtSpec, scheme: Scheme, seed: int, width: int = 1600, height: int = 900) -> str:
    rng = random.Random(seed)
    pal = ArtPalette(scheme)
    top, bottom = band(width, height)
    svg = Svg(width, height)
    backdrop(svg, pal, cx=lerp(0.3, 0.7, params.focus), cy=0.5, tint=0.18 if pal.dark else 0.05, tint_t=0.4)
    vol = lerp(0.06, 0.16, params.energy)
    up_color, down_color = pal.tone(0.95), pal.tone(0.45)

    # far bokeh: big soft discs of light
    bokeh = []
    for _ in range(int(lerp(10, 24, params.density))):
        bokeh.append(
            f'<circle cx="{f(rng.uniform(0, width))}" cy="{f(rng.uniform(0, height))}" r="{f(rng.uniform(30, 95))}" '
            f'fill="{pal.tone(rng.uniform(0.3, 1.0))}" opacity="{rng.uniform(0.2, 0.55) * (1 if pal.dark else 0.6):.2f}"/>'
        )
    svg.group(bokeh, filter_id=svg.blur(22.0))

    # digit columns: thin falling ticks of light
    cols = []
    for _ in range(int(lerp(14, 34, params.density))):
        x = rng.uniform(0, width)
        y = rng.uniform(-50, height * 0.6)
        length = rng.uniform(120, 520)
        tone = pal.tone(rng.uniform(0.2, 0.7))
        yy = y
        while yy < y + length:
            h = rng.choice((2.0, 2.0, 5.0))
            cols.append(
                f'<rect x="{f(x)}" y="{f(yy)}" width="{f(rng.uniform(3, 7))}" height="{f(h)}" fill="{tone}" '
                f'opacity="{lerp(0.7, 0.1, (yy - y) / length):.2f}"/>'
            )
            yy += h + rng.uniform(2, 6)
    svg.group(cols, filter_id=svg.glow(1.0, strength=0.6))

    def draw(series: list[tuple[float, float, float, float]], x0: float, x1: float, y0: float, y1: float, body_w: float) -> list[str]:
        out = []
        step = (x1 - x0) / len(series)
        for i, (o, h, lo, c) in enumerate(series):
            x = x0 + (i + 0.5) * step
            ys = [lerp(y1, y0, v) for v in (o, h, lo, c)]
            color = up_color if c >= o else down_color
            out.append(f'<rect x="{f(x - 0.9)}" y="{f(ys[1])}" width="1.8" height="{f(max(1.0, ys[2] - ys[1]))}" fill="{color}"/>')
            yb, ye = min(ys[0], ys[3]), max(ys[0], ys[3])
            out.append(f'<rect x="{f(x - body_w / 2)}" y="{f(yb)}" width="{f(body_w)}" height="{f(max(2.0, ye - yb))}" fill="{color}"/>')
        return out

    # far, focal and near rows of candles: small and soft, sharp and glowing, huge and blurred
    far = draw(_series(rng, int(lerp(40, 70, params.density)), vol), -20, width + 20, top + 40, bottom - 120, 7)
    svg.group(far, filter_id=svg.blur(3.5), opacity=0.55)
    n_focus = int(lerp(18, 30, params.density))
    fx = width * lerp(0.22, 0.5, params.focus)
    focus = draw(_series(rng, n_focus, vol), fx - 120, fx + width * 0.55, top + 20, bottom - 20, 13)
    svg.group(focus, filter_id=svg.glow(3.0, strength=1.3))
    near = draw(_series(rng, 6, vol * 1.4), -60, width + 60, -80, height + 80, 46)
    svg.group(near, filter_id=svg.blur(18.0), opacity=0.5 if pal.dark else 0.35)

    # a hazy horizon line of light through the focal band
    svg.linear("haze", [(0.0, pal.glow(), 0.0), (0.5, pal.glow(), 0.22 if pal.dark else 0.1), (1.0, pal.glow(), 0.0)])
    svg.add(f'<rect x="0" y="{f((top + bottom) / 2 - 140)}" width="{width}" height="280" fill="url(#haze)" opacity="{clamp(0.8):.2f}"/>')
    return svg.render()

"""Generative data art: deterministic code engines that Claude only parameterizes.

Claude picks an engine from :data:`ENGINES` and fills a :class:`DataArtSpec`; :func:`render_art` draws it as SVG
(glow and depth-of-field filters, gradients, layered opacity) in the scheme's colors, ready for ``svg_to_png``. The
same spec and scheme always give the same picture. Pieces are abstract: no objects, people or icons, only
structure, rhythm and colour, with any focal structure inside the centre 5:2 crop band.
"""

from __future__ import annotations

from collections.abc import Callable

from inferno_ghostwriter.images import palettes
from inferno_ghostwriter.images.art.candles import glow_candles
from inferno_ghostwriter.images.art.canvas import ArtPalette, band
from inferno_ghostwriter.images.art.digits import radial_digits
from inferno_ghostwriter.images.art.mesh import network_mesh
from inferno_ghostwriter.images.art.ribbons import fluid_ribbons
from inferno_ghostwriter.images.art.rings import rings
from inferno_ghostwriter.images.art.specs import DataArtSpec, EngineId
from inferno_ghostwriter.images.art.streams import fan_streams
from inferno_ghostwriter.images.art.waves import particle_wave
from inferno_ghostwriter.images.palettes import Scheme

Engine = Callable[[DataArtSpec, Scheme, int, int, int], str]

# The preferred engines come first; the weaker ones (``WEAKER``) are listed last and say so, so Claude picks them only
# when nothing else fits the subject. Prompts list engines in this order.
ENGINES: dict[str, str] = {
    "fan_streams": "A few bundles of fine threads fanning out into a field of data pixels "
    "(inputs becoming features, classification, pipelines). inputs = bundles, outputs = field bands.",
    "fluid_ribbons": "Thick swirling paint ribbons around vortices (creativity, generative models, messy data, turbulence). "
    "inputs = vortices.",
    "radial_digits": "A tunnel of binary marks streaming out of a bright centre (raw data, scale, compute, the digital deep end).",
    "particle_wave": "Layered waves of glowing particles flowing across the frame (signals, time series, flow, streaming). "
    "inputs = strands.",
    "glow_candles": "Candlesticks glowing in layers of depth with bokeh (markets, metrics, volatility, forecasting).",
    "network_mesh": "Weaker, last resort: a glowing node-and-edge mesh in perspective (networks, graphs, connected systems).",
    "rings": "Weaker, last resort: a tilted wheel of fanned slivers in concentric rings (categories, spectra, cycles). outputs = rings.",
}
"""Each engine with the one line Claude reads when choosing, preferred engines first."""
WEAKER = ("network_mesh", "rings")
"""Engines that draw less striking pieces: kept, listed last, picked only when nothing else fits."""
PREFERRED = tuple(k for k in ENGINES if k not in WEAKER)

_DRAW: dict[str, Engine] = {
    "network_mesh": network_mesh,
    "fan_streams": fan_streams,
    "fluid_ribbons": fluid_ribbons,
    "radial_digits": radial_digits,
    "particle_wave": particle_wave,
    "glow_candles": glow_candles,
    "rings": rings,
}


def art_scheme(spec: DataArtSpec, scheme: Scheme) -> Scheme:
    """The scheme a piece is drawn in: ``background`` switches a house scheme's surface; a brand scheme stays."""
    if spec.background == "auto" or scheme.ramp_id not in palettes.RAMPS:
        return scheme
    if spec.background == "dark" and not scheme.dark:
        return palettes.scheme(scheme.ramp_id, "near_black")
    if spec.background == "light" and scheme.dark:
        return palettes.scheme(scheme.ramp_id, "white")
    return scheme


def render_art(spec: DataArtSpec, scheme: Scheme, *, width: int = 1600, height: int = 900) -> str:
    """The piece as SVG."""
    return _DRAW[spec.engine](spec, art_scheme(spec, scheme), spec.seed, width, height)


__all__ = [
    "ENGINES",
    "PREFERRED",
    "WEAKER",
    "ArtPalette",
    "DataArtSpec",
    "EngineId",
    "art_scheme",
    "band",
    "fan_streams",
    "fluid_ribbons",
    "glow_candles",
    "network_mesh",
    "particle_wave",
    "radial_digits",
    "render_art",
    "rings",
]

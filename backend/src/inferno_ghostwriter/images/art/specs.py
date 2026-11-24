"""What Claude chooses for a piece of data art: an engine and a handful of dials. Code draws it."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EngineId = Literal["network_mesh", "fan_streams", "fluid_ribbons", "radial_digits", "particle_wave", "glow_candles", "rings"]


class DataArtSpec(BaseModel):
    """One piece of generative data art. Every field but ``engine`` has a smart default."""

    engine: EngineId = Field(description="Which engine draws the piece (see ENGINES).")
    seed: int = Field(default=1, ge=0, le=2**31 - 1, description="Same seed, same picture; change it for a variation.")
    density: float = Field(default=0.6, ge=0.0, le=1.0, description="How much there is: 0 = sparse and airy, 1 = rich and packed.")
    focus: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Where the sharp, glowing focal structure sits left to right (0 = left, 0.5 = centre, 1 = right).",
    )
    energy: float = Field(default=0.5, ge=0.0, le=1.0, description="Calm (0) to turbulent (1): curvature, swirl and volatility.")
    inputs: int | None = Field(
        default=None, ge=1, le=12, description="A count the structure should show on its input side: bundles, sources, series."
    )
    outputs: int | None = Field(default=None, ge=1, le=12, description="A count for the output side: bands, clusters, rings.")
    background: Literal["auto", "dark", "light"] = Field(
        default="auto", description="auto keeps the scheme's surface; dark or light switches a house scheme's surface."
    )

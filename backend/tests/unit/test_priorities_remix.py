"""Priorities bias a redraw's random experiment (never a pin)."""

from __future__ import annotations

import random

from inferno_ghostwriter.images import remix


def palette_ids(priorities: dict[str, str] | None, runs: int = 60) -> list[str]:
    rng = random.Random(1)
    return [t.id for _ in range(runs) for t in remix.choose_tweaks((remix.PALETTE,), rng=rng, count=1, priorities=priorities)]


def test_avoided_looks_never_come_up_and_preferred_ones_come_up_more() -> None:
    neutral = palette_ids(None)
    avoided = palette_ids({"palette:viridis": "avoid", "palette:sepia": "avoid"})
    assert "viridis" in neutral and "viridis" not in avoided and "sepia" not in avoided
    liked = palette_ids({"palette:candy": "prefer"})
    assert liked.count("candy") > neutral.count("candy")


def test_a_pin_still_wins_over_an_avoided_look() -> None:
    chosen = remix.choose_tweaks((remix.PALETTE,), pinned={"palette": "sepia"}, priorities={"palette:sepia": "avoid"})
    assert [t.id for t in chosen] == ["sepia"]


def test_avoiding_every_look_in_a_dimension_falls_back_to_all_of_them() -> None:
    everything = {f"palette:{t.id}": "avoid" for t in remix.TWEAKS if t.dimension == remix.PALETTE}
    assert palette_ids(everything, runs=5)

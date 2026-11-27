"""The shared ideas board, the kind table and chart colors."""

from __future__ import annotations

import json

from inferno_ghostwriter.images import board, kinds
from inferno_ghostwriter.images.body import KIND_OPTIONS, PAINTABLE
from inferno_ghostwriter.images.palettes import scheme
from inferno_ghostwriter.images.remix import KIND_DIMENSIONS
from inferno_ghostwriter.images.render import CHART_CATEGORY, prepare_vega_spec
from inferno_ghostwriter.writer.schemas import ImageKind


def test_new_pitches_are_added_and_old_ones_keep_their_place() -> None:
    old = [{"hook": f"old {i}"} for i in range(4)]
    entries, mapping, new = board.merge(old, [{"hook": "new 0"}, {"hook": "new 1"}])
    assert [e["hook"] for e in entries] == ["old 0", "old 1", "old 2", "old 3", "new 0", "new 1"]
    assert mapping == {0: 0, 1: 1, 2: 2, 3: 3} and new == [4, 5] and entries[4]["batch"] == 1
    # A full board drops the oldest ideas nobody drew; the one on show and the tried ones stay, and indexes follow.
    entries, mapping, new = board.merge(old, [{"hook": "new"}] * 2, keep={0, 2}, cap=4)
    assert [e["hook"] for e in entries] == ["old 0", "old 2", "new", "new"] and mapping == {0: 0, 2: 1} and new == [2, 3]
    assert board.remap([0, 1, 2], mapping) == [0, 1] and board.remap_one(2, mapping) == 1 and board.remap_one(1, mapping) is None
    assert board.edit_pitch({"hook": "a", "concept": "b"}, {"hook": " c ", "concept": ""}) == {"hook": "c", "concept": "b", "edited": True}


def test_the_kind_table_covers_every_kind_and_feeds_the_rooms() -> None:
    assert set(kinds.KINDS) == set(ImageKind.__args__)  # type: ignore[attr-defined]
    assert PAINTABLE == ("illustration", "icon") and KIND_OPTIONS["diagram"] == ("diagram", "illustration", "chart")
    assert KIND_DIMENSIONS["chart"] == ("palette",) and "hands_on_viz" not in KIND_DIMENSIONS
    assert kinds.label("screenshot") == "Screenshot mock" and kinds.KINDS["screenshot"].lint == "structure"


def test_charts_take_the_posts_colors() -> None:
    spec = {"mark": "bar", "data": {"values": [{"a": 1}]}}
    viridis = prepare_vega_spec(json.dumps(spec), scheme=scheme("viridis", "white"))
    colors = viridis["config"]["range"]["category"]
    assert colors != CHART_CATEGORY and set(colors) <= set(scheme("viridis", "white").ramp)
    assert viridis["config"]["range"]["ramp"] == list(scheme("viridis", "white").ramp)
    # A brand palette still wins, and without either the inferno defaults stand.
    assert prepare_vega_spec(spec, ("#111111", "#222222", "#333333"), scheme("viridis"))["config"]["range"]["category"][0] == "#111111"
    assert prepare_vega_spec(spec)["config"]["range"]["category"] == CHART_CATEGORY

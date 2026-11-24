"""The shared image room: pitch, draw candidates, judge, refine, keep finalists (memes, openers and in-body images)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from pydantic import BaseModel

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.demo import DRAFT, FakeLLM
from inferno_ghostwriter.images import ImageProviderError
from inferno_ghostwriter.images.body import BodyContext, BodyRoom
from inferno_ghostwriter.images.judge import SheetVerdict, judge_sheet, rank_pitches
from inferno_ghostwriter.images.memes import ArtDirection, MemeContext, MemeMaker, load_state
from inferno_ghostwriter.images.memes.formats import CAST, menu
from inferno_ghostwriter.images.opening.room import OpeningContext, OpeningRoom
from inferno_ghostwriter.images.opening.room import load_state as load_opening_state
from inferno_ghostwriter.images.opening.styles import STYLES
from inferno_ghostwriter.images.references import ReferenceLibrary, load_png
from inferno_ghostwriter.images.story import anchored, deal, moments
from inferno_ghostwriter.llm import LLMError
from inferno_ghostwriter.llm.base import LLMImagesUnsupportedError

POST = MemeContext(title="Pie Charts Are Lame", markdown="# Pie Charts Are Lame\n\nUse bars.", voice_profile="", brief="Closing laugh")
ART = ArtDirection(visual_style="flat vector")


class NoEyesLLM(FakeLLM):
    """A connection that cannot show Claude an image (like headless Claude Code)."""

    async def structured(self, *, task: str, schema: type[BaseModel], **kwargs: Any) -> Any:
        if kwargs.get("images"):
            raise LLMImagesUnsupportedError()
        return await super().structured(task=task, schema=schema, **kwargs)


class FixingLLM(FakeLLM):
    """The picture judge prefers the third candidate and asks every candidate for a fix."""

    async def structured(self, *, task: str, schema: type[BaseModel], **kwargs: Any) -> Any:
        if schema is SheetVerdict:
            self.calls.append({"kind": "structured", "task": task, "prompt": kwargs["prompt"], "images": len(kwargs.get("images") or [])})
            count = len(kwargs.get("images") or [])
            return SheetVerdict.model_validate(
                {
                    "scores": [
                        {"candidate": i, "reads_as": f"picture {i}", "score": 9 if i == 2 else 5, "fidelity": 0, "fix": "Shorter words"}
                        for i in range(count)
                    ],
                    "why": "The third one lands.",
                }
            )
        return await super().structured(task=task, schema=schema, **kwargs)


# -- the judge -------------------------------------------------------------------------------------------------------


async def test_the_pitch_judge_ranks_with_vetoes_and_never_fails_an_image() -> None:
    ranking = await rank_pitches(FakeLLM(), Settings(), context="c", candidates=["a", "b", "c"])
    assert ranking is not None and ranking.order() == [0, 1, 2] and ranking.entry(0)["vetoed"] is False

    class Down(FakeLLM):
        async def structured(self, **kwargs: Any) -> Any:
            raise LLMError("down")

    assert await rank_pitches(Down(), Settings(), context="c", candidates=["a"]) is None
    assert await judge_sheet(NoEyesLLM(), Settings(), context="c", candidates=["a", "b"], pngs=[b"x", b"y"]) is None
    # One picture is not a choice: no call.
    llm = FakeLLM()
    assert await judge_sheet(llm, Settings(), context="c", candidates=["a"], pngs=[b"x"]) is None and llm.calls == []


async def test_the_sheet_judge_sees_references_first_and_blends_fidelity() -> None:
    llm = FixingLLM()
    sheet = await judge_sheet(
        llm,
        Settings(),
        context="c",
        candidates=["a", "b", "c"],
        pngs=[b"1", b"2", b"3"],
        references=[b"r"],
        reference_note="the original memes",
    )
    assert sheet is not None and sheet.order()[0] == 2 and sheet.fixes[0] == "Shorter words"
    call = llm.calls[-1]
    assert call["images"] == 4 and "first 1 attached image(s) are REFERENCES" in call["prompt"]


# -- memes -----------------------------------------------------------------------------------------------------------


async def test_a_fresh_meme_draws_six_candidates_and_keeps_three_finalists() -> None:
    llm = FakeLLM()
    meme = await MemeMaker(llm, Settings()).make("", POST, ART)
    state = load_state(meme.spec)
    assert state and len(state["concepts"]) == 6 and len(meme.finalists) == 3
    tasks = llm.tasks()
    assert tasks[:3] == ["meme ideas", "image pitch judge", "image sheet judge"] and not any(t.startswith("meme build") for t in tasks)
    assert "Pitch 6 distinct concepts" in llm.calls[0]["prompt"] and "Angle cards" in llm.calls[0]["prompt"]
    # Each finalist is a whole meme with its own chosen pitch, so swapping costs nothing.
    chosen = [load_state(f.spec)["chosen"] for f in meme.finalists]  # type: ignore[index]
    assert len(set(chosen)) == 3 and meme.finalists[0].spec == meme.spec and meme.finalists[0].reads_as


async def test_the_judges_favourite_wins_and_its_fix_is_applied_by_restaging() -> None:
    llm = FixingLLM()
    meme = await MemeMaker(llm, Settings()).make("", POST, ART)
    state = load_state(meme.spec)
    assert state and state["chosen"] == 2 and meme.score == 9
    assert "Shorter words" in next(c for c in llm.calls if c["task"].startswith("meme edit"))["prompt"]


async def test_without_eyes_the_pitch_order_stands_and_finalists_are_still_offered() -> None:
    meme = await MemeMaker(NoEyesLLM(), Settings()).make("", POST, ART)
    state = load_state(meme.spec)
    assert state and state["chosen"] == 0 and state["review"]["skipped"] and len(meme.finalists) == 3


async def test_stored_pitches_and_redraws_need_no_pitching_call() -> None:
    llm = FakeLLM()
    maker = MemeMaker(llm, Settings())
    first = await maker.make("", POST, ART, meme_format="terminal")
    llm.calls.clear()
    picked = await maker.make(first.spec, POST, ART, concept_index=3)
    assert load_state(picked.spec)["chosen"] == 3 and llm.calls == []  # type: ignore[index]
    with pytest.raises(ImageProviderError):
        await maker.make(first.spec, POST, ART, concept_index=40)
    reworded = maker.reword(picked.spec, {"out3": "fatal: nobody owns this chart"}, ART)
    assert "nobody owns this chart" in reworded.alt and llm.calls == []
    # A remix redraw sends the critique to the meme by restaging its words.
    remixed = await maker.make(first.spec, POST, ArtDirection(visual_style="x", note="angrier"), redraw=True)
    assert load_state(remixed.spec) and "The author asked: angrier" in llm.calls[-1]["prompt"]


async def test_an_opening_meme_is_drawn_once_without_finalists() -> None:
    llm = FakeLLM()
    meme = await MemeMaker(llm, Settings()).make("", MemeContext(**{**POST.__dict__, "position": "opening"}), ART, finalists=False)
    assert meme.finalists == [] and "image sheet judge" not in llm.tasks()


def test_the_cast_stays_our_own() -> None:
    assert "ghost" in CAST and "never real people" not in menu()  # the catalog itself names no real person


# -- the opening room ------------------------------------------------------------------------------------------------


def opening_context(**changes: Any) -> OpeningContext:
    base = OpeningContext(
        title="Pie Charts Are Lame",
        markdown=DRAFT,
        voice_profile="",
        brief="Thumbnail",
        hook="Admit to hating pie charts.",
        humor=5,
        suggested=("cheat_sheet", "editorial", "data_art"),
        eligible=tuple(s.id for s in STYLES),
    )
    return OpeningContext(**{**base.__dict__, **changes})


async def test_a_fresh_opener_builds_candidates_judges_them_and_keeps_finalists() -> None:
    llm = FakeLLM()
    room = OpeningRoom(llm, Settings(), MemeMaker(llm, Settings()))
    result = await room.make("", opening_context(), ART)
    state = load_opening_state(result.spec)
    assert state is not None and state["mode"] == "auto" and len(state["concepts"]) == 6
    styles = [c["style"] for c in state["concepts"]]
    assert styles.count("editorial") >= 2 and "data_art" in styles
    assert all({"total", "vetoed", "note"} <= set(c["panel"]) for c in state["concepts"])
    tasks = llm.tasks()
    assert tasks[:2] == ["opening ideas", "image pitch judge"] and "image sheet judge" in tasks
    assert len(state["review"]["candidates"]) >= 3 and len(result.finalists) == 3
    assert "Angle cards" in llm.calls[0]["prompt"] and "Pitch exactly 6" in llm.calls[0]["prompt"]


async def test_a_redraw_or_a_picked_pitch_skips_the_room() -> None:
    llm = FakeLLM()
    room = OpeningRoom(llm, Settings(), MemeMaker(llm, Settings()))
    first = await room.make("", opening_context(), ART)
    llm.calls.clear()
    picked = await room.make(first.spec, opening_context(), ART, concept_index=1)
    assert picked.finalists == [] and "image sheet judge" not in llm.tasks() and "opening ideas" not in llm.tasks()


# -- in-body images --------------------------------------------------------------------------------------------------


def body_context(**changes: Any) -> BodyContext:
    base = BodyContext(
        kind="diagram",
        slot_id="img1",
        title="Pie Charts Are Lame",
        purpose="Show the four steps",
        brief="A four-step loop",
        visual_style="flat",
        brand="",
        image_guidance="",
        siblings="(none)",
        builds_on="",
        context=DRAFT[:2000],
        markdown=DRAFT,
    )
    return BodyContext(**{**base.__dict__, **changes})


async def test_an_in_body_image_gets_ideas_candidates_and_finalists() -> None:
    llm = FakeLLM()
    room = BodyRoom(llm, Settings())
    ideas = await room.pitch(body_context(), [], None)
    assert len(ideas["concepts"]) == 4 and all(c["kind"] == "diagram" for c in ideas["concepts"])
    drawn, index = await room.run(ideas, body_context(), None)
    assert index == 0 and len(drawn.finalists) == 3 and ideas["tried"] == [0, 1, 2]
    assert llm.tasks().count("diagram image design") == 3 and "image sheet judge" in llm.tasks()


# -- story: anchors, angle cards, references -------------------------------------------------------------------------


def test_anchors_must_quote_the_post_and_cards_vary_with_the_seed() -> None:
    post = "# T\n\nPeople compare **lengths** better than angles, which is why bars win.\n\n" + "Another long paragraph here. " * 8
    assert anchored("people compare lengths better than angles", post)
    assert not anchored("readers adore three dimensional pie charts", post)
    assert anchored("", post) and anchored("bars", post)
    a, b = deal(post, seed=1, families={"x": "X", "y": "Y", "z": "Z"}), deal(post, seed=2, families={"x": "X", "y": "Y", "z": "Z"})
    assert "Moment card 1" in a and "Family card" in a and "Tone card" in a
    assert deal(post, seed=1, families={"x": "X", "y": "Y", "z": "Z"}) == a
    assert a != b or len(moments(post, 2, random.Random(0))) < 3


def test_the_reference_library_is_optional_and_finds_memes_by_name(tmp_path: Path) -> None:
    assert ReferenceLibrary(tmp_path / "missing").for_meme("distracted") is None
    (tmp_path / "Meme").mkdir()
    Image.new("RGB", (40, 20), "red").save(tmp_path / "Meme" / "Distracted Boyfriend.jpg")
    (tmp_path / "Meme" / "notes.txt").write_text("not an image")
    library = ReferenceLibrary(tmp_path)
    found = library.for_meme("distracted")
    assert found is not None and found.name == "Distracted Boyfriend.jpg" and library.for_meme("venn") is None
    pngs = load_png([found, tmp_path / "Meme" / "notes.txt"], 16)
    assert len(pngs) == 1 and pngs[0][:4] == b"\x89PNG"


def test_meme_state_round_trips() -> None:
    state = {"version": 2, "concepts": [], "chosen": None}
    assert load_state(json.dumps(state)) == state and load_state("<svg/>") is None

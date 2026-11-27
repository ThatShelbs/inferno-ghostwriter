"""What each image action costs and does: picks draw as-is, uploads can be edited and built on, the ideas board grows
instead of being replaced, and the text around an image is only checked when what the image shows changed.

These pin the call budget per card action (``backend/scripts/usage_report.py --actions`` prints the same numbers)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from inferno_ghostwriter.db import ProjectImage
from inferno_ghostwriter.demo import FakeLLM, png_bytes
from inferno_ghostwriter.services import Services
from tests.api.test_remix import images, make_post

SYNC = "image text sync"
# Matching the text to a changed image: the find/replace call and, when the text changed, its fresh AI-detection score.
TEXT_SYNC = (SYNC, "ai detection")


def calls_besides_sync(fake_llm: FakeLLM) -> list[str]:
    return [t for t in fake_llm.tasks() if t not in TEXT_SYNC]


def redraw(client: TestClient, image: dict, **body: object) -> dict:
    job = client.post(f"/api/images/{image['id']}/redraw", json=body).json()
    assert job["status"] == "succeeded", job
    return job


def upload(client: TestClient, image: dict) -> dict:
    response = client.post(f"/api/images/{image['id']}/upload", files={"file": ("mine.png", png_bytes(), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_picked_idea_is_drawn_as_it_is(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    meme = images(client, project)["meme"]
    target = next(p for p in meme["room"]["pitches"] if not p["current"])

    fake_llm.calls.clear()
    redraw(client, meme, concept=target["index"], pitch_hook=target["hook"])
    # A code-drawn meme pick asks no model at all: no critique, no twist, no restaging of the picked words.
    assert calls_besides_sync(fake_llm) == []
    after = images(client, project)["meme"]
    assert after["remix"] is None and after["room"]["pitches"][target["index"]]["current"]

    diagram = images(client, project)["img2"]
    pick = next(p for p in diagram["room"]["pitches"] if not p["current"])
    fake_llm.calls.clear()
    redraw(client, diagram, concept=pick["index"])
    assert len(calls_besides_sync(fake_llm)) == 1 and "image improvement plan" not in fake_llm.tasks()
    assert images(client, project)["img2"]["remix"] is None


def test_an_adjusted_idea_is_saved_and_drawn_with_no_ideation(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    meme = images(client, project)["meme"]
    target = next(p for p in meme["room"]["pitches"] if not p["current"] and p["words"])
    words = ["My own first line", *target["words"][1:]]

    fake_llm.calls.clear()
    redraw(client, meme, concept=target["index"], concept_edit={"hook": "My sharper premise", "words": words})
    assert calls_besides_sync(fake_llm) == []
    pitch = images(client, project)["meme"]["room"]["pitches"][target["index"]]
    assert pitch["edited"] and pitch["hook"] == "My sharper premise" and pitch["words"][0] == "My own first line"


def test_a_new_round_joins_the_board_and_keeps_earlier_ideas_in_place(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    diagram = images(client, project)["img2"]
    before = [(p["index"], p["hook"]) for p in diagram["room"]["pitches"]]

    fake_llm.calls.clear()
    redraw(client, diagram, rethink=True, pitch=True, note="more like a subway map")
    room = images(client, project)["img2"]["room"]
    assert [(p["index"], p["hook"]) for p in room["pitches"][: len(before)]] == before
    newest = max(p["batch"] for p in room["pitches"])
    assert newest > 0 and len(room["pitches"]) > len(before)
    assert next(p for p in room["pitches"] if p["current"])["batch"] == newest
    assert "more like a subway map" in next(c for c in fake_llm.calls if c["task"] == "diagram image ideas")["prompt"]


def test_a_tried_idea_shows_its_picture(client: TestClient, sample_docx: bytes) -> None:
    project = make_post(client, sample_docx)
    meme = images(client, project)["meme"]
    first, second = [p for p in meme["room"]["pitches"] if not p["current"]][:2]
    redraw(client, meme, concept=first["index"])
    redraw(client, meme, concept=second["index"])
    shown = images(client, project)["meme"]
    pitch = shown["room"]["pitches"][first["index"]]
    assert pitch["thumb_url"] and pitch["version"] is not None
    assert client.get(pitch["thumb_url"]).status_code == 200


def test_a_plain_redraw_does_not_rework_the_text(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    diagram = images(client, project)["img2"]
    fake_llm.calls.clear()
    redraw(client, diagram)
    assert SYNC not in fake_llm.tasks()


def test_the_first_redraw_uses_the_judges_saved_fix(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM, services: Services) -> None:
    project = make_post(client, sample_docx)
    diagram = images(client, project)["img2"]
    with Session(services.engine) as session:
        row = session.get(ProjectImage, diagram["id"])
        assert row is not None
        row.remix = {"pending_fix": "Make the middle box twice as large."}
        session.add(row)
        session.commit()

    fake_llm.calls.clear()
    redraw(client, diagram)
    assert "image improvement plan" not in fake_llm.tasks()
    remix = images(client, project)["img2"]["remix"]
    assert remix["weakness"] == "Make the middle box twice as large." and remix["brainstormed"]
    # Used once: the next redraw critiques the new picture.
    fake_llm.calls.clear()
    redraw(client, diagram)
    assert "image improvement plan" in fake_llm.tasks()


def test_an_upload_can_be_edited_redrawn_and_built_on(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    slots = images(client, project)
    meme, diagram, chart = slots["meme"], slots["img2"], slots["img3"]

    mine = upload(client, meme)
    # The old picture's pitches stay pickable, but none is on show, and there are no words to retype or stale finalists.
    assert mine["finalists"] == [] and mine["room"]["slots"] == [] and not any(p["current"] for p in mine["room"]["pitches"])
    assert client.put(f"/api/images/{meme['id']}/words", json={"words": {"top": "x"}}).status_code == 422

    up = upload(client, diagram)
    assert up["room"] is not None  # every image has an ideas board
    fake_llm.calls.clear()
    edit = client.post(f"/api/images/{diagram['id']}/edit", json={"instruction": "Make the arrows orange"}).json()
    assert edit["status"] == "succeeded", edit
    assert calls_besides_sync(fake_llm) == ["diagram image design"]
    edited = images(client, project)["img2"]
    assert edited["provider"] == "claude-svg"

    upload(client, diagram)
    fake_llm.calls.clear()
    redraw(client, diagram)
    assert calls_besides_sync(fake_llm) == ["diagram image design"]

    upload(client, diagram)
    built = client.post(f"/api/images/{chart['id']}/build-on", json={"slot_id": "img2"}).json()
    assert built["status"] == "succeeded", built
    assert images(client, project)["img3"]["remix"] is None  # no random twist against "same look as the base"

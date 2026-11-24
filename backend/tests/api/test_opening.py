"""The opening image through the API: styles, the panel's pitches, retyped words and the meme sandwich."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from inferno_ghostwriter.demo import FakeLLM
from tests.api.test_flow import create_persona, upload


def post_with(client: TestClient, sample_docx: bytes, **dials: object) -> dict:
    pid = create_persona(client)["id"]
    upload(client, pid, sample_docx)
    client.post(f"/api/personas/{pid}/voice-profile")
    created = client.post("/api/projects", json={"prompt": "Pie charts", "dials": {"revision_passes": 0, **dials}}).json()
    return client.get(f"/api/projects/{created['project']['id']}").json()


def image(client: TestClient, project: dict, kind: str) -> dict:
    return next(i for i in client.get(f"/api/projects/{project['id']}").json()["images"] if i["kind"] == kind)


def test_the_catalog_lists_every_style_and_what_suits_each_article_type(client: TestClient) -> None:
    catalog = client.get("/api/opening-styles").json()
    ids = [s["id"] for s in catalog["styles"]]
    assert ids[:2] == ["editorial", "data_art"] and {
        "meme",
        "cheat_sheet",
        "data_chart",
        "big_number",
        "versus",
        "framework",
        "receipt",
    } <= set(ids)
    assert catalog["suggested_by_type"]["how_to"][0] == "cheat_sheet"
    assert catalog["suggested_by_type"]["auto"] == ["editorial", "data_art"]


def test_a_chosen_style_its_pitches_and_words_need_no_new_judging(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = post_with(client, sample_docx, opening_style="cheat_sheet")
    assert project["resolved_dials"]["opening_style"] == "cheat_sheet"
    hero = image(client, project, "hero")
    opening = hero["room"]
    assert opening["room"] == "opening" and opening["format"] == "cheat_sheet" and len(opening["pitches"]) == 4
    assert all(p["format"] == "cheat_sheet" and p["score"] is not None for p in opening["pitches"])
    assert sum(p["current"] for p in opening["pitches"]) == 1 and len(hero["finalists"]) == 3 and opening["why"]
    assert {s["name"] for s in opening["slots"]} >= {"headline", "items.0.label", "items.0.detail"}
    url = f"/api/images/{hero['id']}"

    fake_llm.calls.clear()
    retyped = client.put(f"{url}/words", json={"words": {"headline": "Six rules, zero pies"}})
    assert retyped.status_code == 200, retyped.text
    assert {s["name"]: s["text"] for s in retyped.json()["room"]["slots"]}["headline"] == "Six rules, zero pies"
    assert fake_llm.calls == [] and len(retyped.json()["history"]) == len(hero["history"]) + 1

    assert client.post(f"{url}/redraw", json={"concept": 2}).json()["status"] == "succeeded"
    assert image(client, project, "hero")["room"]["pitches"][2]["current"]
    assert "opening ideas" not in fake_llm.tasks() and "image sheet judge" not in fake_llm.tasks()

    assert client.post(f"{url}/redraw", json={"format": "versus"}).json()["status"] == "succeeded"
    assert image(client, project, "hero")["room"]["format"] == "versus"
    assert client.post(f"{url}/redraw", json={"format": "hologram"}).status_code == 422
    assert client.post(f"{url}/redraw", json={"concept": 40}).status_code == 422

    meme = image(client, project, "meme")
    assert client.post(f"/api/images/{meme['id']}/redraw", json={"format": "versus"}).status_code == 422

    job = client.post(f"{url}/edit", json={"instruction": "Make the headline shorter"}).json()
    assert job["status"] == "succeeded", job
    edit = next(c for c in reversed(fake_llm.calls) if c["task"].startswith("opening "))
    assert "Make the headline shorter" in edit["prompt"]


def test_a_data_opener_prints_its_sources(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = post_with(client, sample_docx, opening_style="data_chart")
    opening = image(client, project, "hero")["room"]
    assert opening["format"] == "data_chart" and opening["sources"][0]["url"].startswith("https://example.com/")
    assert "Source" in image(client, project, "hero")["caption"]
    research = next(c for c in fake_llm.calls if c["task"] == "research" and "opening chart" in c["prompt"])
    assert "Pie chart accuracy" in research["prompt"]


def test_a_meme_sandwich(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = post_with(client, sample_docx, opening_style="meme", humor=6)
    hero = image(client, project, "hero")
    assert hero["room"]["format"] == "meme" and hero["room"]["slots"] and hero["provider"] == "claude-meme"
    ideas = [c for c in fake_llm.calls if c["task"] == "meme ideas"]
    # The opener is pitched first; the closer is told about it, so the two memes differ and can bookend.
    assert "Pitch the opening meme" in ideas[0]["prompt"] and "meme sandwich" in ideas[1]["prompt"]

    url = f"/api/images/{hero['id']}"
    slot = hero["room"]["slots"][0]["name"]
    fake_llm.calls.clear()
    retyped = client.put(f"{url}/words", json={"words": {slot: "Me, opening with a meme"}})
    assert retyped.status_code == 200, retyped.text
    assert retyped.json()["room"]["format"] == "meme" and fake_llm.calls == []
    assert {s["name"]: s["text"] for s in retyped.json()["room"]["slots"]}[slot] == "Me, opening with a meme"

    bundle = client.get(f"/api/projects/{project['id']}/export/x")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf, Image.open(io.BytesIO(zf.read("thumbnail.png"))) as thumb:
        assert thumb.size == (1500, 600)

    medium = client.get(f"/api/projects/{project['id']}/export/medium")
    with zipfile.ZipFile(io.BytesIO(medium.content)) as zf:
        with Image.open(io.BytesIO(zf.read("thumbnail.png"))) as thumb:
            assert thumb.size == (1400, 560)
        # An opening meme is padded to 5:2, so Medium's story-preview crop only trims padding.
        hero_file = next(n for n in zf.namelist() if n.startswith("images/") and "hero" in n)
        with Image.open(io.BytesIO(zf.read(hero_file))) as opener:
            assert opener.width * 2 == opener.height * 5


def test_low_humor_never_opens_with_a_meme_and_the_persona_default_applies(client: TestClient, sample_docx: bytes) -> None:
    project = post_with(client, sample_docx, humor=1)
    styles = {p["format"] for p in image(client, project, "hero")["room"]["pitches"]}
    assert "meme" not in styles and {"editorial", "data_art"} <= styles

    pid = project["persona_id"]
    assert client.get(f"/api/personas/{pid}").json()["default_opening_style"] == "auto"
    assert client.patch(f"/api/personas/{pid}", json={"default_opening_style": "versus"}).json()["default_opening_style"] == "versus"
    created = client.post("/api/projects", json={"prompt": "Pie charts", "dials": {"revision_passes": 0}}).json()
    later = client.get(f"/api/projects/{created['project']['id']}").json()
    assert later["resolved_dials"]["opening_style"] == "versus" and image(client, later, "hero")["room"]["format"] == "versus"
    assert client.patch(f"/api/personas/{pid}", json={"default_opening_style": "hologram"}).json()["default_opening_style"] == "auto"


def test_redraw_of_an_edited_opener_keeps_the_edit(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = post_with(client, sample_docx, opening_style="versus")
    hero = image(client, project, "hero")
    url = f"/api/images/{hero['id']}"
    assert client.post(f"{url}/edit", json={"instruction": "Make the headline shorter"}).json()["status"] == "succeeded"
    fake_llm.calls.clear()
    assert client.post(f"{url}/redraw", json={}).json()["status"] == "succeeded"
    build = next(c for c in fake_llm.calls if c["task"].startswith("opening ") and "Make the headline shorter" in c["prompt"])
    assert "<current_build>" in build["prompt"]
    # Another idea starts over.
    fake_llm.calls.clear()
    assert client.post(f"{url}/redraw", json={"concept": 1}).json()["status"] == "succeeded"
    assert not any("Make the headline shorter" in c["prompt"] for c in fake_llm.calls)

"""Image studio: start every image over (with a note), map each slot to its own idea, look and model, replace one
slot with its next idea, turn a middle slot into a meme, and keep a chart of styles and looks to prefer or avoid."""

from __future__ import annotations

from fastapi.testclient import TestClient

from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.images import priorities
from tests.api.test_image_actions import calls_besides_sync
from tests.api.test_remix import images, make_post


def studio(client: TestClient, project: dict, **body: object) -> dict:
    response = client.post(f"/api/projects/{project['id']}/images/redraw", json=body)
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "succeeded", job
    return job


def versions(client: TestClient, project: dict) -> dict[str, int]:
    return {slot: len(image["history"]) for slot, image in images(client, project).items()}


def test_start_over_pitches_all_new_ideas_and_the_note_steers_every_slot(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    before = versions(client, project)
    fake_llm.calls.clear()
    studio(client, project, note="make it feel like a subway map")
    # Every slot pitched again, and the author's feedback reached a pitching room.
    assert "diagram image ideas" in fake_llm.tasks() and "meme ideas" in fake_llm.tasks()
    assert any("subway map" in c["prompt"] for c in fake_llm.calls if c["task"] == "diagram image ideas")
    after = versions(client, project)
    assert all(after[slot] > before[slot] for slot in before)


def test_keeping_the_ideas_only_redraws_them(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    fake_llm.calls.clear()
    studio(client, project, fresh=False, improve=False)
    assert "diagram image ideas" not in fake_llm.tasks() and "meme ideas" not in fake_llm.tasks()
    assert "image improvement plan" not in fake_llm.tasks()


def test_one_slot_can_be_run_alone_with_its_own_format_and_look(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    before = versions(client, project)
    slot = images(client, project)["img2"]
    assert slot["kind"] != "meme"

    studio(client, project, slots=[{"image_id": slot["id"], "format": "nope_yep", "tweaks": {"palette": "inferno"}}])
    after = images(client, project)
    # The slot kept its place and became a meme in the format asked for; nothing else was touched.
    assert after["img2"]["kind"] == "meme" and after["img2"]["room"]["room"] == "meme"
    assert after["img2"]["slot_id"] == "img2"
    # Only the last slot is the "Closing meme"; a meme in the middle is just a meme.
    assert after["img2"]["kind_label"] == "Meme" and after["meme"]["kind_label"] == "Closing meme"
    # Restoring the first version (the diagram) brings its kind back with it.
    restored = client.post(f"/api/images/{slot['id']}/revert", json={"index": 0}).json()
    assert restored["kind"] == slot["kind"]
    studio(client, project, slots=[{"image_id": slot["id"], "format": "nope_yep"}])
    changed = {s for s, n in versions(client, project).items() if n != before[s]}
    assert changed == {"img2"}
    ideas = next(c for c in fake_llm.calls if c["task"] == "meme ideas" and "middle of this post" in c["prompt"])
    assert ideas is not None


def test_slots_can_each_have_their_own_note_and_the_run_note_fills_the_rest(
    client: TestClient, sample_docx: bytes, fake_llm: FakeLLM
) -> None:
    project = make_post(client, sample_docx)
    rows = images(client, project)
    fake_llm.calls.clear()
    studio(
        client,
        project,
        note="shared steer",
        slots=[{"image_id": rows["img2"]["id"], "note": "only for slot two"}, {"image_id": rows["img3"]["id"]}],
    )
    prompts = [c["prompt"] for c in fake_llm.calls]
    assert any("only for slot two" in p for p in prompts) and any("shared steer" in p for p in prompts)


def test_next_idea_replaces_one_image_without_pitching(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    before = versions(client, project)
    diagram = images(client, project)["img2"]
    fake_llm.calls.clear()
    studio(client, project, slots=[{"image_id": diagram["id"], "next": True}])
    assert "diagram image ideas" not in fake_llm.tasks()
    after = versions(client, project)
    assert after["img2"] == before["img2"] + 1 and after["img3"] == before["img3"]
    assert images(client, project)["img2"]["room"]["pitches"]


def test_a_bad_slot_stops_the_run_before_anything_is_drawn(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    rows = images(client, project)
    before = versions(client, project)
    url = f"/api/projects/{project['id']}/images/redraw"
    good = {"image_id": rows["img2"]["id"]}
    assert client.post(url, json={"slots": [{**good, "format": "nope"}]}).status_code == 422
    assert client.post(url, json={"slots": [{**good, "tweaks": {"palette": "nope"}}]}).status_code == 422
    assert client.post(url, json={"slots": [{**good, "model": "codex"}]}).status_code == 422
    assert client.post(url, json={"model": "gemini"}).status_code == 422
    assert client.post(url, json={"slots": [{"image_id": 999999}]}).status_code == 404
    assert versions(client, project) == before


def test_formats_for_a_middle_slot_include_the_meme_bank(client: TestClient) -> None:
    slot = client.get("/api/image-formats", params={"room": "slot", "kind": "diagram"}).json()
    ids = [f["id"] for f in slot]
    assert ids[:3] == ["diagram", "illustration", "chart"] and "nope_yep" in ids
    # The body list the card uses is unchanged.
    body = client.get("/api/image-formats", params={"room": "body", "kind": "diagram"}).json()
    assert [f["id"] for f in body] == ["diagram", "illustration", "chart"]


def test_priorities_are_saved_for_the_post_and_can_become_the_persona_default(client: TestClient, sample_docx: bytes) -> None:
    project = make_post(client, sample_docx)
    url = f"/api/projects/{project['id']}/image-priorities"
    chart = client.get(url).json()
    assert {"style:editorial", "meme:nope_yep", "kind:chart", "palette:viridis"} <= {t["id"] for t in chart["tags"]}
    assert chart["post"] == {} and chart["persona"] == {}

    saved = client.put(url, json={"post": {"style:editorial": "prefer", "meme:nope_yep": "avoid", "bogus": "prefer"}}).json()
    assert saved["post"] == {"style:editorial": "prefer", "meme:nope_yep": "avoid"} and saved["persona"] == {}
    default = client.put(url, json={"post": {"palette:viridis": "prefer"}, "save_as_default": True}).json()
    assert default["persona"] == {"palette:viridis": "prefer"}


def test_priorities_reach_the_pitching_rooms(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    client.put(f"/api/projects/{project['id']}/image-priorities", json={"post": {"kind:chart": "avoid", "style:editorial": "prefer"}})
    diagram = images(client, project)["img2"]
    fake_llm.calls.clear()
    assert client.post(f"/api/images/{diagram['id']}/redraw", json={"rethink": True, "pitch": True}).json()["status"] == "succeeded"
    prompt = next(c["prompt"] for c in fake_llm.calls if c["task"] == "diagram image ideas")
    assert "The author prefers: Visual metaphor." in prompt and "The author does not want: Chart." in prompt
    assert calls_besides_sync(fake_llm)


def test_priority_rules() -> None:
    chart = {"style:data_art": "avoid", "style:receipt": "prefer", "palette:sepia": "avoid"}
    # Avoided styles leave, preferred ones lead, the rest keep their order; never an empty menu.
    assert priorities.order_styles(["editorial", "data_art", "receipt"], chart) == ["receipt", "editorial"]
    assert priorities.order_styles(["data_art"], chart) == ["data_art"]
    assert priorities.clean({"style:editorial": "prefer", "style:editorial2": "prefer", "kind:chart": "meh"}) == {
        "style:editorial": "prefer"
    }
    assert priorities.merge({"kind:chart": "prefer"}, {"kind:chart": "avoid"}) == {"kind:chart": "avoid"}
    assert priorities.note({}) == "" and "prefers" in priorities.note({"kind:chart": "prefer"})

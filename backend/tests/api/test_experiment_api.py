"""A library bake-off end to end with a fake Claude and a fake sandbox: every scenario asked and run, the post built by code."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from inferno_ghostwriter.demo import FakeLLM, experiment_code
from inferno_ghostwriter.experiments import compose
from inferno_ghostwriter.experiments.models import Experiment
from inferno_ghostwriter.services import Services
from tests.api.test_flow import create_persona, upload

PROMPT = "**Goal:** a stacked bar chart of films per genre.\n\n**Source:** the vega movies dataset."
SLOTS = ["exp1", "exp2", "exp3", "exp4", "exp5", "exp6"]


def make_experiment_post(client: TestClient, sample_docx: bytes, *, run_code: bool = True, **body: object) -> dict:
    pid = create_persona(client)["id"]
    upload(client, pid, sample_docx)
    client.post(f"/api/personas/{pid}/voice-profile")
    created = client.post(
        "/api/projects",
        json={
            "prompt": "Six libraries, one prompt.",
            "dials": {"revision_passes": 0},
            "experiment": {"prompt": PROMPT, "run_code": run_code},
            **body,
        },
    )
    assert created.status_code == 201, created.text
    return client.get(f"/api/projects/{created.json()['project']['id']}").json()


def images(project: dict) -> dict[str, dict]:
    return {i["slot_id"]: i for i in project["images"]}


def test_every_scenario_is_asked_run_and_composed_into_the_post(
    client: TestClient, services: Services, sample_docx: bytes, fake_llm: FakeLLM
) -> None:
    services.settings.allow_code_execution = True
    project = make_experiment_post(client, sample_docx)
    assert project["status"] == "ready", project["error"]

    # One pinned-model answer per scenario; the first sends the prompt exactly as written, the rest add one line.
    asked = [c for c in fake_llm.calls if c["task"].startswith("experiment ")]
    assert len(asked) == 6 and {c["model"] for c in asked} == {"claude-opus-5-5"}
    assert asked[0]["prompt"] == PROMPT
    assert all(c["prompt"].startswith(PROMPT + "\n\nUse the Python library") for c in asked[1:])

    experiment = Experiment.model_validate(project["experiment"])
    assert [s.status for s in experiment.scenarios] == ["ready"] * 6
    assert [s.slot_id for s in experiment.scenarios] == SLOTS and experiment.montage_slot == "expmontage"

    # The writer got the results to frame, and the post got the exact prompt, code, counts and chart from code.
    draft = next(c for c in fake_llm.calls if c["task"] == "draft")
    assert "{{experiment:matplotlib}}" in draft["prompt"] and "NO prompts, NO code" in draft["prompt"]
    markdown = project["markdown"]
    assert compose.verify(markdown, experiment) == [] and "{{experiment:" not in markdown
    assert experiment_code("matplotlib") in markdown and "| Library | Lines of code | Characters | Chart |" in markdown
    assert markdown.count("**The prompt**") == 6
    assert all(f"{{{{image:{slot}}}}}" in markdown for slot in [*SLOTS, "expmontage"])

    # Each chart is a hands-on image made by its code; the closing sheet shows them all.
    shown = images(project)
    for slot in SLOTS:
        chart = shown[slot]
        assert chart["kind"] == "hands_on_viz" and chart["provider"] == "hands-on-code" and chart["status"] == "ready"
        assert chart["hands_on"]["lines"] > 0 and chart["hands_on"]["stale"] is False
        assert "lines of" in chart["caption"]
    sheet = shown["expmontage"]
    assert sheet["status"] == "ready" and sheet["provider"] == "montage"
    png = client.get(sheet["url"]).content
    assert Image.open(io.BytesIO(png)).size == (1600, 900)
    # Hero first, meme last, the experiment's slots in reading order between them.
    order = [i["slot_id"] for i in sorted(project["images"], key=lambda i: i["position"])]
    assert order[0] == "hero" and order[-1] == "meme" and order.index("exp1") < order.index("exp6") < order.index("expmontage")


def test_without_consent_the_code_is_shown_but_not_run(client: TestClient, services: Services, sample_docx: bytes) -> None:
    assert services.settings.allow_code_execution is False
    project = make_experiment_post(client, sample_docx, run_code=True)
    experiment = Experiment.model_validate(project["experiment"])
    assert [s.status for s in experiment.scenarios] == ["code_only"] * 6 and experiment.montage_slot == ""
    assert compose.verify(project["markdown"], experiment) == []
    assert "This code was not run by the app." in project["markdown"]
    assert not any(slot in images(project) for slot in SLOTS)


def test_a_scenario_can_be_rerun_and_the_sheet_follows(
    client: TestClient, services: Services, sample_docx: bytes, fake_llm: FakeLLM
) -> None:
    services.settings.allow_code_execution = True
    project = make_experiment_post(client, sample_docx)
    before = images(project)["expmontage"]
    fake_llm.calls.clear()

    job = client.post(f"/api/projects/{project['id']}/experiment/altair/rerun").json()
    assert job["status"] == "succeeded", job["error"]
    assert [c["task"] for c in fake_llm.calls if c["task"].startswith("experiment ")] == ["experiment altair"]

    after = client.get(f"/api/projects/{project['id']}").json()
    experiment = Experiment.model_validate(after["experiment"])
    assert compose.verify(after["markdown"], experiment) == []
    assert any(r["label"] == "Experiment rerun" for r in after["revisions"])
    # The side-by-side image was drawn again from the charts as they are now.
    assert len(images(after)["expmontage"]["history"]) > len(before["history"])

    assert client.post(f"/api/projects/{project['id']}/experiment/nope/rerun").status_code == 404
    everything = client.post(f"/api/projects/{project['id']}/experiment/rerun").json()
    assert everything["status"] == "succeeded", everything["error"]


def test_a_rerun_of_an_ordinary_post_is_refused(client: TestClient, sample_docx: bytes) -> None:
    pid = create_persona(client)["id"]
    upload(client, pid, sample_docx)
    client.post(f"/api/personas/{pid}/voice-profile")
    created = client.post("/api/projects", json={"prompt": "Pie charts", "dials": {"revision_passes": 0}}).json()
    assert client.post(f"/api/projects/{created['project']['id']}/experiment/rerun").status_code == 409


def test_a_highlight_inside_the_printed_code_is_not_rewritten(client: TestClient, services: Services, sample_docx: bytes) -> None:
    services.settings.allow_code_execution = True
    project = make_experiment_post(client, sample_docx)
    line = experiment_code("matplotlib").splitlines()[-1]
    refused = client.post(f"/api/projects/{project['id']}/rewrite", json={"selection": line, "instruction": "shorter"})
    assert refused.status_code >= 400 and "word for word" in refused.text
    assert client.get(f"/api/projects/{project['id']}").json()["markdown"] == project["markdown"]


def test_an_experiment_cannot_also_be_an_ab_test(client: TestClient, sample_docx: bytes) -> None:
    pid = create_persona(client)["id"]
    upload(client, pid, sample_docx)
    client.post(f"/api/personas/{pid}/voice-profile")
    refused = client.post("/api/projects", json={"prompt": "x y z", "mode": "ab", "experiment": {"prompt": PROMPT}})
    assert refused.status_code == 422

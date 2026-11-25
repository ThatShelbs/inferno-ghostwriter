"""The hands-on kit end to end: build, download, push with a fake GitHub CLI, and link it from the post."""

from __future__ import annotations

import ast
import csv
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.kit import GitHubCLI
from inferno_ghostwriter.services import Services
from tests.api.test_remix import make_post

FAKE_GH = Path(__file__).parent.parent / "fixtures" / "fake_gh.py"


@pytest.fixture
def remotes(tmp_path: Path, services: Services, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "remotes"
    folder.mkdir()
    monkeypatch.setenv("FAKE_GH_REMOTES", str(folder))
    monkeypatch.setenv("FAKE_GH_RECORD", str(tmp_path / "gh.jsonl"))
    services.github = GitHubCLI([sys.executable, str(FAKE_GH)])
    return folder


def _built(client: TestClient, sample_docx: bytes, **body: object) -> dict:
    project = make_post(client, sample_docx)
    job = client.post(f"/api/projects/{project['id']}/kit", json=body).json()
    assert job["status"] == "succeeded", job["error"]
    return project


def _notebook(client: TestClient, project_id: int) -> dict:
    data = client.get(f"/api/projects/{project_id}/kit/download").content
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(n for n in zf.namelist() if n.endswith("/notebook.ipynb"))
        return json.loads(zf.read(name))


def _git(remote: Path, *args: str) -> str:
    return subprocess.run(["git", "--git-dir", str(remote), *args], capture_output=True, text=True, check=True).stdout


def test_build_and_download_a_kit(client: TestClient, sample_docx: bytes, fake_llm: FakeLLM) -> None:
    project = make_post(client, sample_docx)
    before = client.get(f"/api/projects/{project['id']}/kit").json()
    assert not before["built"] and before["files"] == [] and before["repo"] is None
    assert any("chart" in r for r in before["fit"]["reasons"])
    assert before["default_name"] == "pie-charts-are-lame"

    job = client.post(f"/api/projects/{project['id']}/kit", json={"library": "altair", "note": "Keep it short"}).json()
    assert job["status"] == "succeeded", job["error"]
    call = next(c for c in fake_llm.calls if c["task"] == "kit design")
    assert "Altair" in call["prompt"] and "Keep it short" in call["prompt"] and "data/chart_img3.csv" in call["prompt"]

    kit = client.get(f"/api/projects/{project['id']}/kit").json()
    assert kit["built"] and kit["library"] == "altair"
    files = set(kit["files"])
    for path in [
        "notebook.ipynb",
        "article.md",
        "README.md",
        "LICENSE",
        "requirements.txt",
        "make_data.py",
        "data/chart_img3.csv",
        "code/01_sorted_bars.py",
        "prompts/starter_prompts.md",
        "assets/credits.md",
        ".gitignore",
    ]:
        assert path in files, path
    assert any(f.startswith("assets/") and f.endswith(".png") for f in files)

    data = client.get(f"/api/projects/{project['id']}/kit/download")
    with zipfile.ZipFile(io.BytesIO(data.content)) as zf:
        names = zf.namelist()
        assert all(n.startswith("pie-charts-are-lame/") for n in names)
        assert zf.read("pie-charts-are-lame/requirements.txt").decode().split() == ["altair", "numpy", "pandas"]
        assert "MIT License" in zf.read("pie-charts-are-lame/LICENSE").decode()
        rows = list(csv.DictReader(io.StringIO(zf.read("pie-charts-are-lame/data/chart_img3.csv").decode())))
        assert rows

    nb = _notebook(client, project["id"])
    assert nb["nbformat"] == 4 and nb["metadata"]["kernelspec"]["name"] == "python3"
    text = ["".join(c["source"]) for c in nb["cells"]]
    # The whole article is there, images come from assets/, and the cell follows the sentence it was anchored to.
    assert any("Pie charts have a fan club" in t for t in text)
    assert any("](assets/" in t for t in text)
    anchor = next(i for i, t in enumerate(text) if "Bar charts. Seriously" in t)
    assert text[anchor + 1].startswith("**Try it:**") and "mark_bar" in text[anchor + 2]
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            source = "\n".join(line for line in "".join(cell["source"]).splitlines() if not line.lstrip().startswith(("%", "!")))
            ast.parse(source)


def test_push_needs_the_github_cli(client: TestClient, sample_docx: bytes) -> None:
    project = make_post(client, sample_docx)
    assert client.post(f"/api/projects/{project['id']}/kit/push", json={}).status_code == 409  # not built yet
    client.post(f"/api/projects/{project['id']}/kit", json={})
    response = client.post(f"/api/projects/{project['id']}/kit/push", json={})
    assert response.status_code == 422 and "GitHub CLI" in response.json()["detail"]
    status = client.get("/api/github/status").json()
    assert not status["installed"] and status["sign_in_command"].startswith("gh auth login")


def test_push_private_then_update_then_link(client: TestClient, sample_docx: bytes, remotes: Path, tmp_path: Path) -> None:
    project = _built(client, sample_docx)
    assert client.get("/api/github/status?fresh=true").json()["login"] == "kit-tester"

    job = client.post(f"/api/projects/{project['id']}/kit/push", json={"name": "pie-kit", "visibility": "private"}).json()
    assert job["status"] == "succeeded", job["error"]
    kit = client.get(f"/api/projects/{project['id']}/kit").json()
    assert kit["repo"]["url"] == "https://github.com/kit-tester/pie-kit"
    assert kit["repo"]["visibility"] == "private" and kit["repo"]["colab_url"] is None
    calls = [json.loads(line) for line in (tmp_path / "gh.jsonl").read_text().splitlines()]
    create = next(c for c in calls if c[:2] == ["repo", "create"])
    assert "--private" in create and "--push" in create

    remote = remotes / "pie-kit.git"
    assert "notebook.ipynb" in _git(remote, "ls-tree", "--name-only", "main")
    # A private repository cannot be cloned from Colab, so the notebook links images relatively.
    assert "raw.githubusercontent" not in _git(remote, "show", "main:notebook.ipynb")

    # Rebuild with an article link, then push the update to the same repository.
    client.post(f"/api/projects/{project['id']}/kit", json={"article_url": "https://example.com/pies"})
    job = client.post(f"/api/projects/{project['id']}/kit/push", json={"name": "ignored"}).json()
    assert job["status"] == "succeeded", job["error"]
    assert len(_git(remote, "log", "--oneline", "main").splitlines()) == 2
    assert "https://example.com/pies" in _git(remote, "show", "main:README.md")

    assert client.post(f"/api/projects/{project['id']}/kit/link").json() == {"added": True}
    post = client.get(f"/api/projects/{project['id']}").json()
    assert "https://github.com/kit-tester/pie-kit" in post["markdown"]
    assert post["revisions"][0]["label"] == "Linked the hands-on kit"
    assert client.post(f"/api/projects/{project['id']}/kit/link").json() == {"added": False}
    assert client.get(f"/api/projects/{project['id']}/kit").json()["linked"]


def test_public_kit_opens_in_colab(client: TestClient, sample_docx: bytes, remotes: Path) -> None:
    project = _built(client, sample_docx)
    job = client.post(f"/api/projects/{project['id']}/kit/push", json={"name": "pie-public", "visibility": "public"}).json()
    assert job["status"] == "succeeded", job["error"]
    kit = client.get(f"/api/projects/{project['id']}/kit").json()
    assert kit["repo"]["colab_url"].endswith("/kit-tester/pie-public/blob/main/notebook.ipynb")
    notebook = _git(remotes / "pie-public.git", "show", "main:notebook.ipynb")
    assert "raw.githubusercontent.com/kit-tester/pie-public/main/assets/" in notebook
    assert "git clone --depth 1 https://github.com/kit-tester/pie-public.git" in notebook


def test_a_taken_name_fails_the_push_not_the_kit(client: TestClient, sample_docx: bytes, remotes: Path) -> None:
    project = _built(client, sample_docx)
    (remotes / "taken.git").mkdir()
    job = client.post(f"/api/projects/{project['id']}/kit/push", json={"name": "taken"}).json()
    assert job["status"] == "failed" and "already have a repository named taken" in job["error"]
    kit = client.get(f"/api/projects/{project['id']}/kit").json()
    assert kit["repo"] is None and kit["built"]
    # Another name works from the same folder.
    job = client.post(f"/api/projects/{project['id']}/kit/push", json={"name": "free"}).json()
    assert job["status"] == "succeeded", job["error"]

"""Count the model calls one post costs, per task, for free.

    uv run python scripts/usage_report.py              # the demo post, printed as a table
    uv run python scripts/usage_report.py --json out.json
    uv run python scripts/usage_report.py --with-chatgpt   # as if ChatGPT were signed in: what still reaches Claude
    uv run python scripts/usage_report.py --actions        # the calls each image card action makes (Redraw, Ideas, Edit...)

Runs the example persona's voice profile and post through ``demo.FakeLLM`` in a temporary data folder and
reports, for each task, the number of calls, how many characters of system prompt and prompt were sent, and
how many images were shown. Characters are a stand-in for input tokens (about four per token), so a change
that trims a prompt or drops a call shows up here before any real run. Real runs record the same breakdown per
provider in each job's ``usage.by_model``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from inferno_ghostwriter import example
from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.llm.auth import ClaudeAuth
from inferno_ghostwriter.llm.router import RoutingLLM
from inferno_ghostwriter.llm.secondary import SecondaryCLI
from inferno_ghostwriter.secrets import MemorySecretStore
from inferno_ghostwriter.services import build_services

IMAGE_WORDS = ("image", "meme", "opening", "pitch", "judge", "diagram", "chart", "art", "restage", "sheet", "remix")
SETUP_WORDS = ("voice", "sample", "insight")


MADE: list[FakeLLM] = []


CODEX: list[FakeLLM] = []


class _StubCodex(SecondaryCLI):
    """A signed-in ChatGPT stand-in: answers with the demo's canned payloads and records what it was sent."""

    def __init__(self) -> None:
        super().__init__("codex", discover=False)
        self.fake = FakeLLM(showcase=True)
        self.fake.painter = True
        CODEX.append(self.fake)

    async def signed_in(self, *, fresh: bool = False) -> bool:
        return True

    async def complete(
        self, *, system: Any, prompt: str, schema: Any = None, images: Any = None, usage: Any = None, timeout: float = 240
    ) -> Any:
        if schema is None:
            return await self.fake.text(task="text", system=system, prompt=prompt, effort="medium", usage=usage)
        task = f"{schema.__name__}"
        return await self.fake.structured(
            task=task, system=system, prompt=prompt, schema=schema, effort="medium", usage=usage, images=images
        )

    async def paint(self, prompt: str, *, images: Any = None, usage: Any = None, timeout: float = 360) -> bytes:
        return await self.fake.paint(prompt, images=images, usage=usage)


class _Recorder(FakeLLM):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        MADE.append(self)


def _area(task: str) -> str:
    lowered = task.lower()
    if any(word in lowered for word in SETUP_WORDS):
        return "setup"
    return "images" if any(word in lowered for word in IMAGE_WORDS) else "text"


def tally(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "system_chars": 0, "prompt_chars": 0, "images": 0})
    for call in calls:
        row = rows[call["task"]]
        row["calls"] += 1
        row["system_chars"] += sum(len(block.text) for block in call.get("system") or [])
        row["prompt_chars"] += len(call.get("prompt") or "")
        row["images"] += int(call.get("images") or 0)
    out = [{"task": task, "area": _area(task), **row} for task, row in rows.items()]
    return sorted(out, key=lambda r: (r["area"], -(r["system_chars"] + r["prompt_chars"])))


async def run(with_chatgpt: bool = False) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "seed").mkdir()
        settings = Settings(data_dir=root / "data", seed_samples_dir=root / "seed", frontend_dist=root / "dist", _env_file=None)  # type: ignore[call-arg]
        secrets = MemorySecretStore()
        auth = ClaudeAuth(secrets, env={"APPDATA": str(root / "appdata"), "ANTHROPIC_CONFIG_DIR": str(root / "ant")}, discover_ant=False)
        services = build_services(settings, secrets=secrets, llm=FakeLLM(), auth=auth, inline_jobs=True)
        original = example.FakeLLM
        codex = _StubCodex()

        def routed(*args: Any, **kwargs: Any) -> Any:
            claude = _Recorder(*args, **kwargs)
            return RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex})

        example.FakeLLM = routed if with_chatgpt else _Recorder  # type: ignore[assignment,misc]
        try:
            await example.seed_example(services, activate=True)
        finally:
            example.FakeLLM = original  # type: ignore[misc]
            services.engine.dispose()
        claude_rows = tally([call for fake in MADE for call in fake.calls])
        codex_rows = tally([call for fake in CODEX for call in fake.calls])
    return [{"model": "claude", **r} for r in claude_rows] + [{"model": "chatgpt", **r} for r in codex_rows]


def print_table(rows: list[dict[str, Any]]) -> None:
    print(f"{'model':<8} {'area':<7} {'task':<34} {'calls':>5} {'system kB':>10} {'prompt kB':>10} {'images':>6}")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        system, prompt = r["system_chars"] / 1000, r["prompt_chars"] / 1000
        print(f"{r['model']:<8} {r['area']:<7} {r['task'][:34]:<34} {r['calls']:>5} {system:>10.1f} {prompt:>10.1f} {r['images']:>6}")
        t = totals[f"{r['model']:<8} {r['area']}"]
        t[0] += r["calls"]
        t[1] += r["system_chars"]
        t[2] += r["prompt_chars"]
        t[3] += r["images"]
    print()
    for area, (calls, system, prompt, images) in sorted(totals.items()):
        print(f"{area:<16} {'TOTAL':<34} {calls:>5} {system / 1000:>10.1f} {prompt / 1000:>10.1f} {images:>6}")


def run_actions() -> list[dict[str, Any]]:
    """Every image card action once, on a fresh demo post, through the real API: the model calls each one makes."""
    from fastapi.testclient import TestClient

    from inferno_ghostwriter.demo import png_bytes
    from inferno_ghostwriter.main import create_app

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "seed").mkdir()
        settings = Settings(data_dir=root / "data", seed_samples_dir=root / "seed", frontend_dist=root / "dist", _env_file=None)  # type: ignore[call-arg]
        secrets = MemorySecretStore()
        auth = ClaudeAuth(secrets, env={"APPDATA": str(root / "appdata"), "ANTHROPIC_CONFIG_DIR": str(root / "ant")}, discover_ant=False)
        llm = FakeLLM()
        services = build_services(settings, secrets=secrets, llm=llm, auth=auth, inline_jobs=True)
        rows: list[dict[str, Any]] = []
        with TestClient(create_app(settings, services)) as client:
            pid = client.post("/api/personas", json={"name": "Report"}).json()["id"]
            client.post(f"/api/personas/{pid}/samples/import-sample-writing")
            client.post(f"/api/personas/{pid}/voice-profile")
            llm.calls.clear()
            created = client.post("/api/projects", json={"prompt": "Pie charts", "dials": {"revision_passes": 0}}).json()
            project_id = created["project"]["id"]
            rows.append({"action": "write the post (all images)", "tasks": [c["task"] for c in llm.calls]})

            def image(slot: str) -> dict[str, Any]:
                found = client.get(f"/api/projects/{project_id}").json()["images"]
                return next(i for i in found if i["slot_id"] == slot or i["kind"] == slot)

            def act(name: str, method: str, path: str, **kwargs: Any) -> None:
                llm.calls.clear()
                response = client.request(method, path, **kwargs)
                status = response.json().get("status", response.status_code) if response.status_code < 400 else response.status_code
                rows.append({"action": name, "tasks": [c["task"] for c in llm.calls], "status": status})

            body = next(i for i in client.get(f"/api/projects/{project_id}").json()["images"] if i["kind"] == "diagram")
            slot = body["slot_id"]
            meme = image("meme")
            other = next(p for p in meme["room"]["pitches"] if not p["current"])
            body_other = next(p for p in body["room"]["pitches"] if not p["current"])
            act("Redraw (in-body)", "POST", f"/api/images/{body['id']}/redraw", json={})
            act("Redraw again (critique)", "POST", f"/api/images/{body['id']}/redraw", json={})
            act("Redraw options: pinned colors", "POST", f"/api/images/{body['id']}/redraw", json={"tweaks": {"palette": "viridis"}})
            act("Ideas: pick an idea (in-body)", "POST", f"/api/images/{body['id']}/redraw", json={"concept": body_other["index"]})
            act("Ideas: pick an idea (meme)", "POST", f"/api/images/{meme['id']}/redraw", json={"concept": other["index"]})
            act(
                "Ideas: adjust words, draw (meme)",
                "POST",
                f"/api/images/{meme['id']}/redraw",
                json={"concept": other["index"], "concept_edit": {"hook": "Sharper"}},
            )
            act("Ideas: draw next idea", "POST", f"/api/images/{body['id']}/redraw", json={"rethink": True})
            act("Ideas: pitch new ideas", "POST", f"/api/images/{body['id']}/redraw", json={"rethink": True, "pitch": True})
            act("Ideas: another format", "POST", f"/api/images/{body['id']}/redraw", json={"format": "illustration"})
            act("Edit", "POST", f"/api/images/{body['id']}/edit", json={"instruction": "Make the arrows orange"})
            finalists = image("hero")["finalists"]
            if len(finalists) > 1:
                act("Finalist pick", "POST", f"/api/images/{image('hero')['id']}/pick", json={"index": 1})
            act("Words (meme)", "PUT", f"/api/images/{meme['id']}/words", json={"words": {"top": "Retyped"}})
            act("Replace (upload)", "POST", f"/api/images/{body['id']}/upload", files={"file": ("mine.png", png_bytes(), "image/png")})
            act("Edit an upload", "POST", f"/api/images/{body['id']}/edit", json={"instruction": "Make it cleaner"})
            act("Redraw an upload", "POST", f"/api/images/{body['id']}/upload", files={"file": ("mine.png", png_bytes(), "image/png")})
            rows[-1]["action"] = "Replace again (upload)"
            act("Redraw an upload", "POST", f"/api/images/{body['id']}/redraw", json={})
            later = [i for i in client.get(f"/api/projects/{project_id}").json()["images"] if i["position"] > body["position"]]
            target = next((i for i in later if i["kind"] in ("chart", "diagram", "illustration")), None)
            if target is not None:
                act("Builds on (from the upload)", "POST", f"/api/images/{target['id']}/build-on", json={"slot_id": slot})
            versions = image(slot)["history"]
            act("Undo (restore a version)", "POST", f"/api/images/{body['id']}/revert", json={"index": max(0, len(versions) - 2)})
        services.engine.dispose()
    return rows


def print_actions(rows: list[dict[str, Any]]) -> None:
    print(f"{'action':<34} {'calls':>5}  tasks")
    for r in rows:
        counts: dict[str, int] = defaultdict(int)
        for task in r["tasks"]:
            counts[task] += 1
        tasks = ", ".join(f"{t} x{n}" if n > 1 else t for t, n in counts.items()) or "(no model call)"
        print(f"{r['action'][:34]:<34} {len(r['tasks']):>5}  {tasks}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, help="also write the rows to this file")
    parser.add_argument("--with-chatgpt", action="store_true", help="route as if ChatGPT (Codex) were signed in, painting on")
    parser.add_argument("--actions", action="store_true", help="the calls each image card action makes (Redraw, Ideas, Edit...)")
    args = parser.parse_args()
    if args.actions:
        actions = run_actions()
        print_actions(actions)
        if args.json:
            args.json.write_text(json.dumps(actions, indent=2), encoding="utf-8")
        return
    rows = asyncio.run(run(args.with_chatgpt))
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

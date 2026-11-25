"""Count the model calls one post costs, per task, for free.

    uv run python scripts/usage_report.py              # the demo post, printed as a table
    uv run python scripts/usage_report.py --json out.json
    uv run python scripts/usage_report.py --with-chatgpt   # as if ChatGPT were signed in: what still reaches Claude

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, help="also write the rows to this file")
    parser.add_argument("--with-chatgpt", action="store_true", help="route as if ChatGPT (Codex) were signed in, painting on")
    args = parser.parse_args()
    rows = asyncio.run(run(args.with_chatgpt))
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

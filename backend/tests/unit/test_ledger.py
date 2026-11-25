from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from pydantic import BaseModel
from sqlmodel import Session

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Job
from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.jobs import JobContext
from inferno_ghostwriter.llm.ledger import UsageLedger, tap, using
from inferno_ghostwriter.llm.router import RoutingLLM
from inferno_ghostwriter.llm.secondary import SecondaryCLI
from inferno_ghostwriter.services import Services


class Answer(BaseModel):
    word: str


def test_tap_is_a_no_op_without_a_ledger() -> None:
    sink = lambda usage: None  # noqa: E731
    assert tap(sink, "claude", "draft") is sink
    assert tap(None, "claude", "draft") is None


def test_ledger_groups_by_provider_and_task_and_forwards() -> None:
    seen: list[dict[str, int]] = []
    with using(UsageLedger()) as ledger:
        sink = tap(seen.append, "claude", "meme ideas")
        assert sink is not None
        sink({"input_tokens": 100, "output_tokens": 10})
        sink({"input_tokens": 50, "output_tokens": 5, "cache_read_input_tokens": 7})
        recorder = tap(None, "codex", "image sheet judge")
        assert recorder is not None
        recorder({"input_tokens": 9})
    summary = ledger.summary()
    assert seen == [{"input_tokens": 100, "output_tokens": 10}, {"input_tokens": 50, "output_tokens": 5, "cache_read_input_tokens": 7}]
    assert summary["providers"]["claude"] == {
        "calls": 2,
        "input_tokens": 150,
        "output_tokens": 15,
        "cache_read_input_tokens": 7,
        "cache_creation_input_tokens": 0,
    }
    assert summary["providers"]["codex"]["calls"] == 1
    assert [row["task"] for row in summary["tasks"]] == ["meme ideas", "image sheet judge"]


async def test_router_records_who_answered_across_spawned_tasks(settings: Settings) -> None:
    settings.secondary.critique = "codex"
    claude = FakeLLM()
    codex = SecondaryCLI("codex", discover=False)

    async def complete(**kwargs: Any) -> Answer:
        kwargs["usage"]({"input_tokens": 40, "output_tokens": 4})
        return Answer(word="ok")

    codex.complete = AsyncMock(side_effect=complete)
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex})
    with using(UsageLedger()) as ledger:
        await asyncio.gather(
            router.text(task="draft", system=[], prompt="Brief", effort="high"),
            router.structured(task="critique", system=[], prompt="Draft", schema=Answer, effort="medium"),
        )
    providers = ledger.summary()["providers"]
    assert providers["claude"]["calls"] == 1 and providers["claude"]["input_tokens"] == 1000
    assert providers["codex"] == {
        "calls": 1,
        "input_tokens": 40,
        "output_tokens": 4,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


async def test_jobs_store_the_breakdown(settings: Settings, services: Services) -> None:
    router = RoutingLLM(settings, api=FakeLLM(), subscription=FakeLLM())

    async def work(ctx: JobContext) -> dict[str, Any]:
        await router.text(task="draft", system=[], prompt="Brief", effort="high", usage=ctx.add_usage)
        return {}

    job = await services.jobs.start("test", work)
    with Session(services.engine) as session:
        stored = session.get(Job, job.id)
        assert stored is not None
        assert stored.usage["input_tokens"] == 1000
        assert stored.usage["by_model"]["providers"]["claude"]["calls"] == 1

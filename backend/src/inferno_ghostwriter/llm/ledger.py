"""Who spent what: model usage per provider and task for one job.

A job sets a :class:`UsageLedger` as the current one (a context variable, so every task the job spawns
shares it); :class:`~inferno_ghostwriter.llm.router.RoutingLLM` taps each call's usage sink with the
provider that actually answered. The job stores :meth:`UsageLedger.summary` next to its plain totals,
so the author can see how much of a post went to Claude and how much to an optional model.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from inferno_ghostwriter.llm.base import UsageSink

COUNTERS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


class UsageLedger:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, int]] = {}

    def record(self, provider: str, task: str, usage: dict[str, int]) -> None:
        row = self.rows.setdefault((provider, task), {"calls": 0, **dict.fromkeys(COUNTERS, 0)})
        row["calls"] += 1
        for key in COUNTERS:
            row[key] += int(usage.get(key) or 0)

    def summary(self) -> dict[str, Any]:
        providers: dict[str, dict[str, int]] = {}
        for (provider, _), row in self.rows.items():
            total = providers.setdefault(provider, {"calls": 0, **dict.fromkeys(COUNTERS, 0)})
            for key, value in row.items():
                total[key] += value
        tasks = [
            {"provider": provider, "task": task, **row}
            for (provider, task), row in sorted(self.rows.items(), key=lambda item: -_weight(item[1]))
        ]
        return {"providers": providers, "tasks": tasks}


def _weight(row: dict[str, int]) -> int:
    return row["input_tokens"] + row["output_tokens"] + row["cache_creation_input_tokens"]


_current: ContextVar[UsageLedger | None] = ContextVar("usage_ledger", default=None)


def current() -> UsageLedger | None:
    return _current.get()


@contextmanager
def using(ledger: UsageLedger) -> Iterator[UsageLedger]:
    token = _current.set(ledger)
    try:
        yield ledger
    finally:
        _current.reset(token)


def tap(sink: UsageSink | None, provider: str, task: str) -> UsageSink | None:
    """Wrap ``sink`` so the current ledger also records the call; returns ``sink`` when no ledger is set."""
    ledger = current()
    if ledger is None:
        return sink

    def record(usage: dict[str, int]) -> None:
        ledger.record(provider, task, usage)
        if sink is not None:
            sink(usage)

    return record

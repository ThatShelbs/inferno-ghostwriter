"""Ask the model once per scenario, keep its code word for word, run it, and keep the chart it really makes."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.experiments.models import Attempt, Experiment, Scenario, measure
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.sandbox import Sandbox

log = logging.getLogger(__name__)

PARALLEL = 3
FENCE_RE = re.compile(r"```[ \t]*(?:python|py|python3)[^\n]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
# What a plain chat with the model starts from: no persona, no house style, so the answer is the model's own.
SYSTEM = [SystemBlock("You are a helpful assistant.")]


class ExperimentError(RuntimeError):
    pass


@dataclass
class ScenarioOutcome:
    scenario: Scenario
    png: bytes | None = None
    versions: dict[str, str] = field(default_factory=dict)


def extract_code(reply: str) -> str:
    """The Python the model returned: its longest ```python block, untouched (only the fence's newlines are trimmed)."""
    blocks = [m.group(1) for m in FENCE_RE.finditer(reply)]
    if not blocks:
        return ""
    return max(blocks, key=len).strip("\n")


def retry_prompt(prompt: str, code: str, error: str) -> str:
    return (
        f"{prompt}\n\n---\nYou answered with this code:\n\n```python\n{code}\n```\n\n"
        f"Running it failed with this error:\n\n```text\n{error.strip()[-1500:]}\n```\n\n"
        "Reply again with the complete corrected Python code in one ```python block."
    )


async def run_scenario(
    *,
    llm: LLM,
    settings: Settings,
    sandbox: Sandbox,
    experiment: Experiment,
    scenario: Scenario,
    usage: Callable[[dict[str, int]], None] | None = None,
    reuse: bool = False,
) -> ScenarioOutcome:
    """Prompt, extract, run (once more if it fails). A failure is recorded on the scenario and never raised.

    ``reuse`` runs the code already stored on the scenario instead of asking the model again (a regeneration)."""
    started = time.perf_counter()
    prompt = experiment.prompt_for(scenario)
    stored = (scenario.reply, scenario.code) if reuse and scenario.code else None
    scenario = scenario.model_copy(update={"status": "running", "error": "", "attempts": []})

    async def ask(text: str) -> tuple[str, str]:
        reply = await llm.text(
            task=f"experiment {scenario.id}",
            system=SYSTEM,
            prompt=text,
            effort=settings.effort_draft,
            max_tokens=32000,
            usage=usage,
            model=experiment.model,
        )
        return reply, extract_code(reply)

    try:
        reply, code = stored if stored is not None else await ask(prompt)
    except LLMError as exc:
        return ScenarioOutcome(scenario.model_copy(update={"status": "error", "error": str(exc), "seconds": time.perf_counter() - started}))
    if not code:
        return ScenarioOutcome(
            scenario.model_copy(
                update={
                    "status": "error",
                    "reply": reply,
                    "error": "The reply had no Python code block.",
                    "seconds": time.perf_counter() - started,
                }
            )
        )

    result = None
    attempts: list[Attempt] = []
    for round_number in range(2):
        lines, chars = measure(code)
        scenario = scenario.model_copy(update={"code": code, "reply": reply, "lines": lines, "chars": chars})
        if not experiment.run_code:
            return ScenarioOutcome(
                scenario.model_copy(update={"status": "code_only", "attempts": attempts, "seconds": time.perf_counter() - started})
            )
        result = await sandbox.run(code)
        if result.ok and result.png:
            break
        attempts.append(Attempt(code=code, reply=reply, error=result.error))
        if round_number == 1:
            break
        try:
            reply, fixed = await ask(retry_prompt(prompt, code, result.error))
        except LLMError as exc:
            log.info("Retry for %s failed: %s", scenario.id, exc)
            break
        if not fixed:
            break
        code = fixed

    assert result is not None
    seconds = time.perf_counter() - started
    if result.ok and result.png:
        return ScenarioOutcome(
            scenario.model_copy(update={"status": "ready", "attempts": attempts, "seconds": seconds, "error": ""}),
            result.png,
            result.versions,
        )
    # The last code that failed is still shown, with the error, so the article never claims a chart it does not have.
    return ScenarioOutcome(
        scenario.model_copy(update={"status": "error", "attempts": attempts[:-1], "error": result.error, "seconds": seconds})
    )


async def run_experiment(
    *,
    llm: LLM,
    settings: Settings,
    sandbox: Sandbox,
    experiment: Experiment,
    only: list[str] | None = None,
    usage: Callable[[dict[str, int]], None] | None = None,
    reuse: bool = False,
    on_outcome: Callable[[ScenarioOutcome], Awaitable[None]] | None = None,
) -> list[ScenarioOutcome]:
    """Every scenario (or just ``only``), three at a time; outcomes come back in scenario order."""
    wanted = [s for s in experiment.scenarios if not only or s.id in only]
    if not wanted:
        raise ExperimentError("There is nothing to run.")
    semaphore = asyncio.Semaphore(PARALLEL)

    async def one(scenario: Scenario) -> ScenarioOutcome:
        async with semaphore:
            outcome = await run_scenario(
                llm=llm, settings=settings, sandbox=sandbox, experiment=experiment, scenario=scenario, usage=usage, reuse=reuse
            )
        if on_outcome is not None:
            await on_outcome(outcome)
        return outcome

    return list(await asyncio.gather(*(one(s) for s in wanted)))

"""One answer per scenario, kept word for word and run: retries, consent, failure, reuse."""

from __future__ import annotations

import asyncio

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.demo import FakeLLM, experiment_code
from inferno_ghostwriter.experiments.models import Experiment, default_scenarios, measure
from inferno_ghostwriter.experiments.run import extract_code, run_experiment, run_scenario
from inferno_ghostwriter.sandbox import NoSandbox


def make(run_code: bool = True) -> Experiment:
    return Experiment(prompt="Make a stacked bar chart of movies.", scenarios=default_scenarios(), run_code=run_code)


def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(data_dir=tmp_path / "d", _env_file=None)  # type: ignore[call-arg]


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_the_longest_python_block_is_the_answer_untouched() -> None:
    reply = "Install:\n```python\nimport x\n```\nThe chart:\n```python\nimport matplotlib\n\n\nprint(1)\n```\nDone."
    assert extract_code(reply) == "import matplotlib\n\n\nprint(1)"
    assert extract_code("no code here") == ""


def test_a_scenario_sends_the_prompt_plus_its_one_line_and_pins_the_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm, sandbox, exp = FakeLLM(), NoSandbox(), make()
    scenario = exp.scenario("seaborn")
    assert scenario is not None
    outcome = run(run_scenario(llm=llm, settings=settings(tmp_path), sandbox=sandbox, experiment=exp, scenario=scenario))
    call = llm.calls[0]
    assert call["task"] == "experiment seaborn" and call["model"] == "claude-opus-5-5"
    assert call["prompt"] == "Make a stacked bar chart of movies.\n\nUse the Python library Seaborn."
    assert outcome.scenario.status == "ready" and outcome.png and outcome.scenario.code == experiment_code("seaborn")
    assert (outcome.scenario.lines, outcome.scenario.chars) == measure(experiment_code("seaborn"))
    # "I don't specify" sends the prompt exactly as the author wrote it.
    unspecified = exp.scenario("unspecified")
    assert unspecified is not None and exp.prompt_for(unspecified) == exp.prompt


def test_a_failed_run_gets_one_retry_with_the_error_and_keeps_the_history(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm, sandbox, exp = FakeLLM(), NoSandbox(fail_first=1), make()
    scenario = exp.scenario("matplotlib")
    assert scenario is not None
    outcome = run(run_scenario(llm=llm, settings=settings(tmp_path), sandbox=sandbox, experiment=exp, scenario=scenario))
    assert outcome.scenario.status == "ready"
    assert len(llm.calls) == 2 and "NameError" in llm.calls[1]["prompt"] and experiment_code("matplotlib") in llm.calls[1]["prompt"]
    assert len(outcome.scenario.attempts) == 1 and "NameError" in outcome.scenario.attempts[0].error


def test_a_scenario_that_keeps_failing_is_an_error_not_a_chart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm, sandbox, exp = FakeLLM(), NoSandbox(fail_first=2), make()
    scenario = exp.scenario("plotly")
    assert scenario is not None
    outcome = run(run_scenario(llm=llm, settings=settings(tmp_path), sandbox=sandbox, experiment=exp, scenario=scenario))
    assert outcome.scenario.status == "error" and outcome.png is None and "NameError" in outcome.scenario.error
    assert outcome.scenario.code  # the failing code is still shown, honestly


def test_without_consent_nothing_runs_and_the_code_is_kept(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sandbox, exp = NoSandbox(), make(run_code=False)
    outcomes = run(run_experiment(llm=FakeLLM(), settings=settings(tmp_path), sandbox=sandbox, experiment=exp))
    assert [o.scenario.status for o in outcomes] == ["code_only"] * 6 and sandbox.calls == []
    assert all(o.scenario.code and o.png is None for o in outcomes)


def test_a_regeneration_runs_the_stored_code_without_asking_the_model_again(tmp_path) -> None:  # type: ignore[no-untyped-def]
    first = run(run_experiment(llm=FakeLLM(), settings=settings(tmp_path), sandbox=NoSandbox(), experiment=make(), only=["altair"]))
    stored = make().model_copy(update={"scenarios": [first[0].scenario]})
    llm = FakeLLM()
    again = run(run_experiment(llm=llm, settings=settings(tmp_path), sandbox=NoSandbox(), experiment=stored, reuse=True))
    assert llm.calls == [] and again[0].scenario.code == first[0].scenario.code and again[0].scenario.status == "ready"

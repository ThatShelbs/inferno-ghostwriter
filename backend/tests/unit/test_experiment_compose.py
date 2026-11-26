"""An experiment's blocks are composed by code: the prompt and code reach the post character for character."""

from __future__ import annotations

import pytest

from inferno_ghostwriter.experiments import compose
from inferno_ghostwriter.experiments.models import Experiment, Scenario, default_scenarios, measure

PROMPT = "**Goal:** make a stacked bar chart.\n\nUse `real` data.\n```not a fence```"
CODE_A = "import matplotlib.pyplot as plt\n\nplt.bar([1, 2], [3, 4])\nplt.show()"
CODE_B = 'import altair as alt\n\nprint("```")\nalt.Chart().show()'


def experiment(status: str = "ready") -> Experiment:
    lines_a, chars_a = measure(CODE_A)
    lines_b, chars_b = measure(CODE_B)
    return Experiment(
        prompt=PROMPT,
        scenarios=[
            Scenario(
                id="matplotlib",
                label="Matplotlib",
                addendum="Use the Python library Matplotlib.",
                status=status,
                code=CODE_A,
                lines=lines_a,
                chars=chars_a,
                slot_id="exp1",
            ),  # type: ignore[arg-type]
            Scenario(id="altair", label="Altair", status=status, code=CODE_B, lines=lines_b, chars=chars_b, slot_id="exp2"),  # type: ignore[arg-type]
        ],
        montage_slot="expmontage",
    )


def test_counts_are_measured_from_the_code() -> None:
    assert measure(CODE_A) == (4, len(CODE_A))
    assert measure("") == (0, 0)
    assert measure("\nprint(1)\n\n") == (1, len("print(1)"))


def test_the_default_scenarios_are_the_six_in_the_brief() -> None:
    scenarios = default_scenarios()
    assert [s.id for s in scenarios] == ["unspecified", "matplotlib", "plotly", "seaborn", "altair", "bokeh"]
    assert scenarios[0].addendum == ""  # "I don't specify": the prompt goes as it is
    assert all(s.addendum.startswith("Use the Python library") for s in scenarios[1:])


def test_a_block_holds_the_exact_prompt_code_counts_and_image() -> None:
    exp = experiment()
    scenario = exp.scenarios[0]
    block = compose.scenario_block(exp, scenario)
    assert "### Matplotlib" in block
    # The prompt itself has a run of three backticks, so its fence is four; the added line comes after it, unchanged.
    assert compose.fenced(exp.prompt_for(scenario), "text") in block and "Use the Python library Matplotlib." in block
    assert compose.fenced(CODE_A, "python") in block
    assert f"4 lines, {len(CODE_A)} characters" in block
    assert block.rstrip().endswith("{{image:exp1}}")


def test_the_fence_outgrows_backticks_inside_the_text() -> None:
    exp = experiment()
    block = compose.scenario_block(exp, exp.scenarios[1])
    # The code prints three backticks, so its fence is four.
    assert compose.fenced(CODE_B, "python").startswith("````python\n") and compose.fenced(CODE_B, "python") in block
    # A post holding only this block is missing the other scenario's prompt, code and chart, and verify says so.
    assert compose.verify("# T\n\n" + block, exp) == [
        "Matplotlib: the prompt is not in the post word for word",
        "Matplotlib: the code is not in the post character for character",
        "Matplotlib: its chart image is missing from the post",
    ]


def test_expand_puts_every_marker_in_place_and_adds_missing_ones() -> None:
    exp = experiment()
    text = compose.expand("# T\n\nIntro.\n\n## Test\n\n{{experiment:altair}}\n\n## Wrap\n\nThe end.\n", exp)
    assert compose.verify(text, exp) == []
    assert text.count("{{image:expmontage}}") == 1
    assert "| Library | Lines of code | Characters | Chart |" in text
    # The marker the writer left out (matplotlib) is added before the closing section, never lost.
    assert text.index("### Matplotlib") < text.index("## Wrap")
    assert "{{experiment:" not in text


def test_verify_catches_a_changed_prompt_or_code() -> None:
    exp = experiment()
    good = compose.expand("# T\n\nIntro.\n", exp)
    assert compose.verify(good, exp) == []
    assert compose.verify(good.replace("plt.bar([1, 2]", "plt.bar([9, 9]"), exp) == [
        "Matplotlib: the code is not in the post character for character"
    ]
    assert compose.verify(good.replace("stacked bar", "stacked column"), exp)
    assert compose.broken_by(good, good.replace("plt.show()", "pass"), exp)
    assert compose.broken_by(good, good.replace("Intro", "Opening"), exp) == []


def test_a_failed_run_never_claims_a_chart() -> None:
    exp = experiment("error")
    exp.scenarios[0].slot_id = ""
    exp.scenarios[0].error = "Traceback\nNameError: df"
    block = compose.scenario_block(exp, exp.scenarios[0])
    assert "{{image:" not in block and "no chart: NameError: df" in block


def test_replace_block_swaps_one_scenario_and_refuses_an_edited_one() -> None:
    before = experiment()
    text = compose.expand("# T\n\nIntro.\n", before)
    after = before.model_copy(deep=True)
    after.scenarios[0].code = "print('new')"
    after.scenarios[0].lines, after.scenarios[0].chars = measure("print('new')")
    swapped = compose.replace_block(text, before, after, "matplotlib")
    assert "print('new')" in swapped and CODE_A not in swapped and CODE_B in swapped
    with pytest.raises(ValueError, match="was edited"):
        compose.replace_block(text.replace("plt.bar", "plt.barh"), before, after, "matplotlib")


def test_the_writer_is_told_to_leave_code_to_the_markers() -> None:
    notes = compose.writer_notes(experiment())
    assert "{{experiment:matplotlib}}" in notes and "{{experiment:table}}" in notes and "{{experiment:montage}}" in notes
    assert "NO prompts, NO code" in notes

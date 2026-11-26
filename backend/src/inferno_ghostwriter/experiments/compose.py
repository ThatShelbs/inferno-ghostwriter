"""Turn an experiment into the article's Markdown with plain code, so nothing the model returned is ever retyped.

The writer only frames the story and leaves ``{{experiment:ID}}`` markers; this module expands them into the exact prompt,
the exact code (with measured line and character counts) and the chart image that code made. ``verify`` proves it.
"""

from __future__ import annotations

import re

from inferno_ghostwriter.experiments.models import Experiment, Scenario

MARKER_RE = re.compile(r"\{\{experiment:([A-Za-z0-9_\-]+)\}\}")
TABLE = "table"
MONTAGE = "montage"
HEADING_RE = re.compile(r"^## ", re.MULTILINE)


def fence_for(text: str) -> str:
    """A code fence longer than any run of backticks inside the text."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def fenced(text: str, language: str) -> str:
    fence = fence_for(text)
    return f"{fence}{language}\n{text}\n{fence}"


def count_line(scenario: Scenario) -> str:
    return f"{scenario.lines:,} lines, {scenario.chars:,} characters"


def scenario_block(experiment: Experiment, scenario: Scenario) -> str:
    """One scenario: heading, the prompt, the code with its counts, and the chart it drew."""
    parts = [f"### {scenario.label}", "", "**The prompt**", "", fenced(experiment.prompt_for(scenario), "text"), ""]
    if scenario.code:
        parts += [f"**The code** ({count_line(scenario)})", "", fenced(scenario.code, "python"), ""]
    if scenario.status == "ready" and scenario.slot_id:
        parts += [f"{{{{image:{scenario.slot_id}}}}}", ""]
        if scenario.attempts:
            parts += ["_The first answer failed when run, so the model was shown the error once and this is its corrected code._", ""]
    elif scenario.status == "code_only":
        parts += ["_This code was not run by the app._", ""]
    else:
        reason = scenario.error.strip().splitlines()[-1] if scenario.error.strip() else "it did not finish"
        parts += [f"_This run produced no chart: {reason}_", ""]
    return "\n".join(parts).rstrip() + "\n"


def comparison_table(experiment: Experiment) -> str:
    rows = ["| Library | Lines of code | Characters | Chart |", "| --- | ---: | ---: | --- |"]
    for scenario in experiment.scenarios:
        if not scenario.code:
            continue
        chart = {"ready": "yes", "code_only": "not run"}.get(scenario.status, "failed")
        rows.append(f"| {scenario.label} | {scenario.lines:,} | {scenario.chars:,} | {chart} |")
    return "\n".join(rows) + "\n"


def marker_ids(experiment: Experiment) -> list[str]:
    """Every marker the writer should place, in reading order."""
    ids = [s.id for s in experiment.scenarios]
    return [*ids, TABLE] + ([MONTAGE] if experiment.montage_slot else [])


def expansion(experiment: Experiment, marker: str) -> str:
    if marker == TABLE:
        return comparison_table(experiment)
    if marker == MONTAGE:
        return f"{{{{image:{experiment.montage_slot}}}}}\n" if experiment.montage_slot else ""
    scenario = experiment.scenario(marker)
    return scenario_block(experiment, scenario) if scenario else ""


def ensure_markers(markdown: str, experiment: Experiment) -> str:
    """Add any marker the writer left out, just before the last ``##`` section (the closing) or at the end."""
    present = set(MARKER_RE.findall(markdown))
    missing = [m for m in marker_ids(experiment) if m not in present]
    if not missing:
        return markdown
    block = "\n\n".join(f"{{{{experiment:{m}}}}}" for m in missing)
    headings = list(HEADING_RE.finditer(markdown))
    if len(headings) > 1:
        at = headings[-1].start()
        return markdown[:at].rstrip() + "\n\n" + block + "\n\n" + markdown[at:]
    return markdown.rstrip() + "\n\n" + block + "\n"


def expand(markdown: str, experiment: Experiment) -> str:
    """Replace each marker with its exact block (a marker for something that does not exist disappears)."""
    markdown = ensure_markers(markdown, experiment)
    out = MARKER_RE.sub(lambda m: "\n" + expansion(experiment, m.group(1)).rstrip() + "\n", markdown)
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"


def verify(markdown: str, experiment: Experiment) -> list[str]:
    """What is wrong with the post's experiment blocks: a prompt or code that is not there character for character."""
    problems: list[str] = []
    # Two scenarios may share a prompt or an answer: each needs its own copy, so a change to one of them shows.
    prompts = [fenced(experiment.prompt_for(s), "text") for s in experiment.scenarios]
    codes = [fenced(s.code, "python") if s.code else "" for s in experiment.scenarios]
    for index, scenario in enumerate(experiment.scenarios):
        before = slice(0, index + 1)
        if markdown.count(prompts[index]) < prompts[before].count(prompts[index]):
            problems.append(f"{scenario.label}: the prompt is not in the post word for word")
        if scenario.code and markdown.count(codes[index]) < codes[before].count(codes[index]):
            problems.append(f"{scenario.label}: the code is not in the post character for character")
        if scenario.status == "ready" and scenario.slot_id and f"{{{{image:{scenario.slot_id}}}}}" not in markdown:
            problems.append(f"{scenario.label}: its chart image is missing from the post")
    return problems


def broken_by(before: str, after: str, experiment: Experiment) -> list[str]:
    """What a text change breaks in the experiment's blocks (problems the change added, not ones already there)."""
    already = set(verify(before, experiment))
    return [p for p in verify(after, experiment) if p not in already]


def writer_notes(experiment: Experiment) -> str:
    """What the writer is told about the results: facts and markers, never code to retype."""
    lines = [
        "This post is built from an experiment. The same prompt was given to "
        f"{experiment.model} once per scenario, and each answer was run for real.",
        "",
        "The post's body already contains, for each scenario, the exact prompt, the exact code with its counts and the chart the "
        "code made. Code puts them in place of these markers, so write NO prompts, NO code and NO image placeholders yourself. "
        "Put each marker on its own line, in this order, each under its own `##` or `###` heading context:",
        "",
    ]
    for scenario in experiment.scenarios:
        outcome = {"ready": "drew a chart", "code_only": "was not run", "error": "did not produce a chart"}.get(scenario.status, "")
        lines.append(f"- `{{{{experiment:{scenario.id}}}}}` {scenario.label}: {count_line(scenario)}; the code {outcome}.")
    lines.append(f"- `{{{{experiment:{TABLE}}}}}` the comparison table of lines and characters.")
    if experiment.montage_slot:
        lines.append(f"- `{{{{experiment:{MONTAGE}}}}}` one image that shows every chart side by side (place it after the last scenario).")
    lines += [
        "",
        "Write the framing (why this test, what is held constant: only the library changes), what each result shows, what the "
        "charts and counts reveal when compared, and a conclusion. Describe only what the counts and the code in the notes show.",
        "",
        "What each scenario's code does (for you to describe; do not copy it):",
    ]
    for scenario in experiment.scenarios:
        if scenario.code:
            lines += ["", f"### {scenario.label}", "```python", scenario.code[:3500], "```"]
    return "\n".join(lines)


def replace_block(markdown: str, before: Experiment, after: Experiment, scenario_id: str) -> str:
    """Swap one scenario's block for its new version (after a rerun); the post must still hold the old block as composed."""
    old, new = before.scenario(scenario_id), after.scenario(scenario_id)
    if old is None or new is None:
        raise ValueError(f"There is no scenario {scenario_id!r}.")
    old_text = scenario_block(before, old).rstrip()
    if old_text not in markdown:
        raise ValueError(
            f"The {old.label} section was edited, so it cannot be swapped for the new run. Undo the edit to its prompt or code, then rerun."
        )
    return markdown.replace(old_text, scenario_block(after, new).rstrip(), 1)

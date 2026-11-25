"""Claude designs the kit's code, data and prompts in one call; code builds the files (see ``build.py``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images.palettes import RAMPS
from inferno_ghostwriter.kit.check import PACKAGES, problems
from inferno_ghostwriter.llm import LLM, SystemBlock
from inferno_ghostwriter.prompts import render

LIBRARIES = ("auto", "altair", "plotly", "matplotlib", "seaborn")
LIBRARY_LABELS = {
    "auto": "Auto (what the post teaches, else Altair + Plotly Express)",
    "altair": "Altair (Vega-Lite)",
    "plotly": "Plotly Express",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
}
# The chart colors every kit starts with (the setup cell defines them as COLORS): inferno, dark to light, minus the
# near-black and near-white ends that vanish on a page.
COLORS = list(RAMPS["inferno"][2:9])


class KitDataset(BaseModel):
    file: str = Field(description="CSV file name the code saves under data/, e.g. `daily_signups.csv` (lowercase, no folders).")
    description: str = Field(description="One sentence: what each row is and where the numbers come from.")
    source: Literal["synthetic", "builtin"] = Field(
        description="`synthetic`: made with numpy/pandas from a fixed seed. `builtin`: loaded with a library's own sample "
        "loader (never a URL you are not sure exists)."
    )
    code: str = Field(description="Short top-to-bottom Python that builds a DataFrame `df` and saves it to data/<file>.")


class KitCell(BaseModel):
    anchor: str = Field(description="An exact sentence from the post (8+ words) that this cell should follow.")
    lead_in: str = Field(description="One or two plain sentences, in the author's voice, saying what the cell does.")
    code: str = Field(description="The runnable cell: beginner-level, top to bottom, comments say why.")


class KitChart(BaseModel):
    slot_id: str = Field(description="The image slot id of the post's chart or diagram this recreates.")
    lead_in: str = Field(description="One or two sentences: what the reader will see and what to try changing.")
    code: str = Field(description="Code that reads the CSV from data/ and draws a polished, fully labelled chart.")


class KitScript(BaseModel):
    file: str = Field(description="Script name under code/, numbered in reading order, e.g. `01_load_the_data.py`.")
    title: str = Field(description="What the script shows, in a few words.")
    code: str = Field(description="A complete script (runs with `python code/<file>` from the repo root).")


class KitPrompt(BaseModel):
    title: str
    when: str = Field(description="One sentence: when a reader would use it.")
    prompt: str = Field(description="The prompt text, with [BRACKETED] blanks the reader fills in.")


class KitDesign(BaseModel):
    description: str = Field(description="The GitHub repository description, under 150 characters.")
    library: str = Field(description="The chart library the kit uses, as it is imported (e.g. `altair`, `plotly`).")
    learn: list[str] = Field(description="3-5 short bullets: what the reader will be able to do after the notebook.")
    datasets: list[KitDataset] = Field(default_factory=list)
    cells: list[KitCell] = Field(default_factory=list)
    charts: list[KitChart] = Field(default_factory=list)
    scripts: list[KitScript] = Field(default_factory=list)
    prompts: list[KitPrompt] = Field(default_factory=list)


@dataclass
class ChartData:
    """A chart in the post whose data the kit ships (from the chart's own Vega-Lite spec)."""

    slot_id: str
    file: str
    columns: list[str]
    rows: list[dict[str, object]]
    caption: str
    alt: str


def _code_blocks(design: KitDesign) -> list[tuple[str, str]]:
    return (
        [(f"dataset {d.file}", d.code) for d in design.datasets]
        + [(f"cell after “{c.anchor[:60]}”", c.code) for c in design.cells]
        + [(f"chart {c.slot_id}", c.code) for c in design.charts]
        + [(f"script {s.file}", s.code) for s in design.scripts]
    )


def design_problems(design: KitDesign) -> list[str]:
    return [f"{where}: {issue}" for where, code in _code_blocks(design) for issue in problems(code)]


def drop_broken(design: KitDesign) -> tuple[KitDesign, list[str]]:
    """Remove the blocks that still fail the check, with a note for each (the kit never fails over one cell)."""
    notes: list[str] = []

    def ok(where: str, code: str) -> bool:
        issues = problems(code)
        if issues:
            notes.append(f"Left out {where}: {issues[0]}")
        return not issues

    return (
        design.model_copy(
            update={
                "datasets": [d for d in design.datasets if ok(f"the data file {d.file}", d.code)],
                "cells": [c for c in design.cells if ok("a code cell", c.code)],
                "charts": [c for c in design.charts if ok(f"the chart {c.slot_id}", c.code)],
                "scripts": [s for s in design.scripts if ok(f"the script {s.file}", s.code)],
            }
        ),
        notes,
    )


def charts_block(charts: list[ChartData], others: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for chart in charts:
        sample = json.dumps(chart.rows[:3], ensure_ascii=False)
        lines.append(
            f"- `{chart.slot_id}` (chart): {chart.caption or chart.alt}. Data: `data/{chart.file}`, columns "
            f"{', '.join(chart.columns)}, {len(chart.rows)} rows, first rows {sample}"
        )
    for slot_id, kind, about in others:
        lines.append(f"- `{slot_id}` ({kind}): {about}. No data file; recreate it only if it is a plot of numbers (make the data).")
    return "\n".join(lines) or "(The post has no charts or diagrams.)"


async def design_kit(
    *,
    llm: LLM,
    settings: Settings,
    system: list[SystemBlock],
    markdown: str,
    article_type: str,
    library: str,
    note: str,
    charts: list[ChartData],
    others: list[tuple[str, str, str]],
) -> tuple[KitDesign, list[str]]:
    """The kit's design and notes on anything left out. One retry quotes the check's findings."""
    choice = (
        "Choose the chart library: the one the post teaches or uses if it names one; otherwise Altair (Vega-Lite) for "
        "static charts and Plotly Express where hovering helps."
        if library == "auto"
        else f"Use {LIBRARY_LABELS.get(library, library)} for every chart."
    )
    prompt = render(
        "kit_design",
        markdown=markdown,
        article_type=article_type,
        library=choice,
        colors=", ".join(f'"{c}"' for c in COLORS),
        allowed=", ".join(sorted(PACKAGES)),
        charts=charts_block(charts, others),
        note=note.strip() or "(none)",
    )
    design = await llm.structured(
        task="kit design", system=system, prompt=prompt, schema=KitDesign, effort=settings.effort_kit, max_tokens=32000
    )
    issues = design_problems(design)
    if issues:
        retry = prompt + "\n\nYour last design had code that fails the kit's checks. Fix these and return the whole design again:\n"
        retry += "\n".join(f"- {issue}" for issue in issues[:20])
        design = await llm.structured(
            task="kit design", system=system, prompt=retry, schema=KitDesign, effort=settings.effort_kit, max_tokens=32000
        )
    return drop_broken(design)

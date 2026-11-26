# ruff: noqa: E501
"""An experiment: one prompt run once per scenario, each answer kept word for word and run for real.

The state lives in ``Project.experiment`` (JSON). Counts are always measured here from the stored code, never taken from
what the model says about its own answer.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-opus-5-5"
MAX_SCENARIOS = 8
# The closing image that shows every chart side by side (a code-made montage), and the slot ids of the scenarios' charts.
MONTAGE_SLOT = "expmontage"

# The author's own bake-off prompt: a good starting point that already works with the six default scenarios.
DEFAULT_PROMPT = """**Goal:** Create an exceptional, publication-quality stacked bar chart using Python.

**Context:** The visualization should reveal an interesting, thought-provoking insight while demonstrating advanced data visualization craftsmanship.

**Source:** Use a real, publicly available dataset accessible through Python, preferably involving movies, entertainment, culture, or another engaging subject. Consider the vega movie dataset. Avoid overused textbook datasets and synthetic data.

**Expectation:** Deliver 1 highly customized bar chart visualization using a discrete Viridis color palette, intentional typography, meaningful annotations, thoughtful category ordering, clear labeling, and minimal visual clutter. We are interested in advanced bar chart visualizations such as, volume stacked bar chart, percentage bar chart, diverging bar chart, radial bar chart, tornado bar chart, side-by-side bar chart, lollipop chart, waterfall bar chart, funnel bar chart. Adhere to established data visualization best practices. Provide complete, reproducible Python code that is pure minimalist for human comprehension. Also produce the resulting visualization. Please report how much code was used to generate it (line count and total character count)."""

Status = Literal["pending", "running", "ready", "code_only", "error"]


class Attempt(BaseModel):
    """One answer from the model and what happened when it ran."""

    code: str
    reply: str = ""
    error: str = ""


class Scenario(BaseModel):
    id: str = Field(description="Stable slug, e.g. `matplotlib`.")
    label: str = Field(description="What the reader sees, e.g. `Matplotlib`.")
    library: str = Field(default="", description="The library the prompt asks for; empty = the prompt does not say.")
    addendum: str = Field(default="", description="The one sentence added to the prompt for this scenario; empty = none.")
    status: Status = "pending"
    code: str = ""
    reply: str = ""
    lines: int = 0
    chars: int = 0
    error: str = ""
    # Earlier answers that failed to run, kept so the article can say the code was fixed after an error.
    attempts: list[Attempt] = Field(default_factory=list)
    slot_id: str = ""
    seconds: float = 0.0


class Experiment(BaseModel):
    prompt: str
    model: str = DEFAULT_MODEL
    scenarios: list[Scenario]
    # The author agreed to let the app run the returned code on this computer (see sandbox.py).
    run_code: bool = False
    montage_slot: str = ""
    # The measured Python and library versions the charts were made with.
    environment: dict[str, Any] = Field(default_factory=dict)

    def scenario(self, scenario_id: str) -> Scenario | None:
        return next((s for s in self.scenarios if s.id == scenario_id), None)

    def prompt_for(self, scenario: Scenario) -> str:
        """The exact text sent to the model for one scenario (the author's prompt plus its one added line)."""
        text = self.prompt.strip()
        return f"{text}\n\n{scenario.addendum.strip()}" if scenario.addendum.strip() else text


def default_scenarios() -> list[Scenario]:
    def lib(id_: str, label: str, name: str) -> Scenario:
        return Scenario(id=id_, label=label, library=id_, addendum=f"Use the Python library {name}.")

    return [
        Scenario(id="unspecified", label="No library specified"),
        lib("matplotlib", "Matplotlib", "Matplotlib"),
        lib("plotly", "Plotly Express", "Plotly Express"),
        lib("seaborn", "Seaborn", "Seaborn"),
        lib("altair", "Altair (Vega-Lite)", "Altair (Vega-Lite)"),
        lib("bokeh", "Bokeh", "Bokeh"),
    ]


def measure(code: str) -> tuple[int, int]:
    """(line count, character count) of the stored code: what the article reports."""
    text = code.strip("\n")
    return (len(text.splitlines()) if text else 0), len(text)


def load(data: dict[str, Any] | None) -> Experiment | None:
    return Experiment.model_validate(data) if data else None


def slot_id(index: int) -> str:
    return f"exp{index + 1}"

"""The hands-on kit's pure parts: code checks, requirements, notebook pieces, fit and the follow-along link."""

from __future__ import annotations

import json
from pathlib import Path

from inferno_ghostwriter.db import Project, ProjectImage
from inferno_ghostwriter.kit import kit_fit
from inferno_ghostwriter.kit.build import Repo, blocks_of, chart_data, kit_files, kit_prompts, other_images, own_code, setup_code
from inferno_ghostwriter.kit.check import imports, problems, requirements
from inferno_ghostwriter.kit.design import KitDesign, charts_block, drop_broken
from inferno_ghostwriter.kit.github import repo_name
from inferno_ghostwriter.kit.service import insert_link, link_markdown


def test_checks_parse_and_vet_imports_without_running_code() -> None:
    assert problems("import pandas as pd\nprint(pd.__version__)") == []
    # Notebook magics are not Python but are fine in a cell.
    assert problems("%pip install -q altair\nimport altair as alt") == []
    assert "syntax error" in problems("def broken(:\n    pass")[0]
    assert "not an allowed library" in problems("import torch")[0]
    assert "not allowed" in problems("import subprocess")[0]
    assert problems("eval('1 + 1')") == ["`eval()` is not allowed"]
    assert problems("import os\nos.system('ls')") == ["`os.system()` is not allowed"]
    assert problems("   ") == ["the code is empty"]
    assert imports("from sklearn.linear_model import LinearRegression\nimport numpy.random") == {"sklearn", "numpy"}


def test_requirements_name_pip_packages() -> None:
    assert requirements(["import sklearn", "import json"]) == ["scikit-learn"]
    assert requirements(["import plotly.express as px"]) == ["nbformat", "pandas", "plotly"]


def test_broken_blocks_are_dropped_with_a_note() -> None:
    design = KitDesign.model_validate(
        {
            "description": "d",
            "library": "altair",
            "learn": [],
            "cells": [
                {"anchor": "a b c d", "lead_in": "ok", "code": "x = 1"},
                {"anchor": "a b c d", "lead_in": "bad", "code": "import torch"},
            ],
        }
    )
    kept, notes = drop_broken(design)
    assert [c.lead_in for c in kept.cells] == ["ok"]
    assert notes and "torch" in notes[0]


def test_blocks_keep_fenced_code_whole() -> None:
    markdown = "# T\n\nIntro.\n\n```python\nx = 1\n\ny = 2\n```\n\nAfter."
    assert blocks_of(markdown) == ["# T", "Intro.", "```python\nx = 1\n\ny = 2\n```", "After."]


def test_chart_data_reads_vega_lite_rows() -> None:
    spec = '{"layer": [{"data": {"values": [{"a": 1, "b": "x"}, {"a": 2, "c": true}]}}]}'
    image = ProjectImage(project_id=1, slot_id="img3", kind="chart", spec=spec, status="ready", caption="C")
    (chart,) = chart_data([image])
    assert chart.file == "chart_img3.csv"
    assert chart.columns == ["a", "b", "c"]
    assert chart_data([ProjectImage(project_id=1, slot_id="img2", kind="chart", spec="<svg/>", status="ready")]) == []


def test_colab_setup_only_for_public_repos() -> None:
    public = setup_code(Repo("me", "kit", public=True))
    assert "git clone --depth 1 https://github.com/me/kit.git" in public and "%cd kit" in public
    assert "git clone" not in setup_code(Repo("me", "kit", public=False))
    assert "COLORS = [" in setup_code(None)


def test_fit_recommends_hands_on_posts() -> None:
    tutorial = Project(
        persona_id=1,
        prompt="A tutorial: plot your first chart",
        markdown="# Plot it\n\nLoad the data:\n\n```python\nimport pandas as pd\n```\n",
    )
    chart = ProjectImage(project_id=1, slot_id="img2", kind="chart", status="ready")
    fit = kit_fit(tutorial, [chart])
    assert fit.recommended and fit.article_type == "tutorial"
    assert any("code example" in r for r in fit.reasons) and any("chart" in r for r in fit.reasons)
    essay = Project(persona_id=1, prompt="Why I left my job", markdown="# Leaving\n\nIt was a Tuesday.\n")
    assert not kit_fit(essay, []).recommended


def test_follow_along_link_goes_before_the_first_section() -> None:
    repo = Repo("me", "pie-kit", public=True)
    link = link_markdown(repo, repo.url)
    assert "colab.research.google.com/github/me/pie-kit" in link
    post = "# Title\n\nIntro.\n\n## First\n\nBody.\n"
    assert insert_link(post, link).index(link) < insert_link(post, link).index("## First")
    assert insert_link("# Title\n\nNo sections.", link).endswith(link + "\n")
    assert "Colab" not in link_markdown(Repo("me", "x", public=False), "https://github.com/me/x")


def test_repo_names_are_valid() -> None:
    assert repo_name("Pie Charts Are Lame!") == "Pie-Charts-Are-Lame"


# -- hands-on images and experiments --------------------------------------------------------------

MPL = "import matplotlib.pyplot as plt\nfrom vega_datasets import data\n\ndf = data.movies()\nplt.show()"
BOKEH = "from bokeh.plotting import figure, show\n\np = figure()\nshow(p)"


def _handson_post() -> tuple[Project, list[ProjectImage]]:
    markdown = (
        f"# Two charts\n\n## One\n\nHere is the first:\n\n```python\n{MPL}\n```\n\n{{{{image:img2}}}}\n\n"
        f"## Two\n\nAnd the second:\n\n```python\n{BOKEH}\n```\n\n{{{{image:img3}}}}\n"
    )
    project = Project(persona_id=1, prompt="A tutorial", markdown=markdown)
    images = [
        ProjectImage(
            project_id=1,
            slot_id=slot,
            position=position,
            kind="hands_on_viz",
            provider="hands-on-code",
            status="ready",
            file_name=f"{slot}.png",
            spec=f'{{"library": "{library}"}}',
            alt=f"{library} chart",
        )
        for position, (slot, library) in enumerate([("img2", "matplotlib"), ("img3", "bokeh")], start=1)
    ]
    return project, images


def _set_experiment(project: Project, experiment: dict) -> None:
    # Works whether or not Project already has the column (the experiment is read with getattr).
    object.__setattr__(project, "experiment", experiment)


def test_own_code_is_the_articles_block_byte_for_byte(tmp_path: Path) -> None:
    project, images = _handson_post()
    code = own_code(project, images)
    assert [c.file for c in code] == ["01_matplotlib_img2.py", "02_bokeh_img3.py"]
    assert [c.code for c in code] == [MPL, BOKEH]
    for image in images:
        (tmp_path / image.file_name).write_bytes(b"png")
    design = KitDesign(description="d", library="auto", learn=[])
    files = kit_files(project, images, tmp_path, design, author="Me")
    assert files["code/01_matplotlib_img2.py"].decode().rstrip("\n") == MPL
    assert files["code/02_bokeh_img3.py"].decode().rstrip("\n") == BOKEH
    # Bokeh passes the check and both libraries reach requirements.txt.
    assert problems(BOKEH) == []
    assert {"bokeh", "matplotlib", "vega_datasets"} <= set(files["requirements.txt"].decode().split())
    # The notebook runs each block right after its image.
    cells = ["".join(c["source"]) for c in json.loads(files["notebook.ipynb"])["cells"]]
    at = next(i for i, text in enumerate(cells) if "image:img2" in text or "img2.png" in text)
    assert cells[at + 1].startswith("**Run it:**") and cells[at + 2] == MPL


def test_covered_charts_are_not_sent_to_the_model_to_recreate() -> None:
    block = charts_block([], [], [("img2", "a stacked bar chart")])
    assert "`img2`" in block and "do NOT recreate" in block
    assert "no charts" not in block
    assert other_images([ProjectImage(project_id=1, slot_id="img2", kind="hands_on_viz", status="ready")], [], {"img2"}) == []


def test_experiment_prompts_are_one_exact_file_each(tmp_path: Path) -> None:
    project, images = _handson_post()
    prompt = "**Goal:** Make a chart.\n\n```python\nignored = 1\n```"
    _set_experiment(
        project,
        {
            "prompt": prompt,
            "scenarios": [
                {"id": "unspecified", "label": "No library specified", "status": "code_only", "code": MPL, "lines": 5, "chars": len(MPL)},
                {"id": "bokeh", "label": "Bokeh", "library": "bokeh", "addendum": "Use the Python library Bokeh.", "status": "code_only",
                 "code": BOKEH, "lines": 4, "chars": len(BOKEH)},
            ],
        },
    )  # fmt: skip
    for image in images:
        (tmp_path / image.file_name).write_bytes(b"png")
    design = KitDesign.model_validate(
        {"description": "d", "library": "auto", "learn": [], "prompts": [{"title": "x", "when": "y", "prompt": "z"}]}
    )
    files = kit_files(project, images, tmp_path, design, author="Me")
    assert "prompts/starter_prompts.md" not in files
    first = files["prompts/01_unspecified.md"].decode()
    second = files["prompts/02_bokeh.md"].decode()
    assert first.count("````text") == 1  # one block, fenced longer than the prompt's own fence
    assert prompt in first and f"{prompt}\n\nUse the Python library Bokeh." in second
    assert second.count("Use the Python library Bokeh.") == 1
    assert "01_unspecified.md" in files["prompts/README.md"].decode() and "02_bokeh.md" in files["prompts/README.md"].decode()
    readme_text = files["README.md"].decode()
    assert "| Bokeh |" in readme_text and "prompts/README.md" in readme_text
    assert [p.file for p in kit_prompts(project, design)] == ["prompts/01_unspecified.md", "prompts/02_bokeh.md"]
    assert kit_fit(project, []).recommended
    assert repo_name("   ") == "hands-on-kit"

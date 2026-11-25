"""The hands-on kit's pure parts: code checks, requirements, notebook pieces, fit and the follow-along link."""

from __future__ import annotations

from inferno_ghostwriter.db import Project, ProjectImage
from inferno_ghostwriter.kit import kit_fit
from inferno_ghostwriter.kit.build import Repo, blocks_of, chart_data, setup_code
from inferno_ghostwriter.kit.check import imports, problems, requirements
from inferno_ghostwriter.kit.design import KitDesign, drop_broken
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
    assert repo_name("   ") == "hands-on-kit"

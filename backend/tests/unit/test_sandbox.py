"""The sandbox's guards: what runs, with which environment and packages. (Real uv runs: `scripts/experiment_smoke.py`.)"""

from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

from inferno_ghostwriter.sandbox import LocalSandbox, NoSandbox, RunResult, autocrop, packages_for, scrubbed_env, tail


def run(sandbox: NoSandbox, code: str) -> RunResult:
    return asyncio.run(sandbox.run(code))


def test_packages_come_from_the_imports_with_the_helpers_that_save_a_picture() -> None:
    code = "import altair as alt\nimport seaborn as sns\nfrom vega_datasets import data\nimport json\n"
    assert packages_for(code) == sorted({"altair", "vl-convert-python", "seaborn", "pandas", "vega_datasets"}, key=str.lower)
    assert "kaleido" in packages_for("import plotly.express as px")
    assert packages_for("import bokeh.plotting") == ["bokeh"]
    assert packages_for("import json") == []


def test_the_environment_keeps_no_keys_or_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "ANTHROPIC_API_KEY": "sk-secret",
        "ANTHROPIC_AUTH_TOKEN": "tok",
        "OPENAI_API_KEY": "sk-other",
        "GITHUB_TOKEN": "ghp_x",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "INFERNO_GHOSTWRITER_DATA_DIR": "/data",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PATH", "/usr/bin")
    env = scrubbed_env({"EXTRA": "1"})
    words = ("KEY", "TOKEN", "SECRET", "ANTHROPIC", "OPENAI", "GITHUB", "INFERNO")
    assert [k for k in env if any(word in k.upper() for word in words)] == []
    assert env["PATH"] == "/usr/bin" and env["MPLBACKEND"] == "Agg" and env["EXTRA"] == "1"


def test_nosandbox_refuses_code_the_check_rejects() -> None:
    sandbox = NoSandbox()
    for bad in ("import subprocess\nsubprocess.run(['ls'])", "eval('1')", "import not_a_real_library", "def broken(:"):
        result = run(sandbox, bad)
        assert not result.ok and "not run" in result.error


def test_the_real_sandbox_checks_the_code_before_it_starts_anything() -> None:
    # The uv path does not exist: only a rejection that happens before any process starts can answer.
    for bad in ("import subprocess\nsubprocess.run(['ls'])", "import os\nos.system('dir')", "exec('1')"):
        result = asyncio.run(LocalSandbox("/no/such/uv").run(bad))
        assert not result.ok and result.error.startswith("The code was not run:")


def test_nosandbox_draws_a_stand_in_for_good_code() -> None:
    result = run(NoSandbox(), "import matplotlib.pyplot as plt\nplt.plot([1])\nplt.show()")
    assert result.ok and result.png is not None and result.png.startswith(b"\x89PNG")


def test_nosandbox_can_fail_first_or_be_unavailable() -> None:
    sandbox = NoSandbox(fail_first=1)
    assert not run(sandbox, "x = 1").ok
    assert run(sandbox, "x = 1").ok
    assert run(NoSandbox(unavailable="needs uv"), "x = 1").error == "needs uv"


def test_autocrop_trims_the_white_page_around_a_chart() -> None:
    image = Image.new("RGB", (400, 300), "white")
    image.paste(Image.new("RGB", (100, 50), "#440154"), (150, 120))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    with Image.open(io.BytesIO(autocrop(buffer.getvalue(), pad=10))) as cropped:
        assert cropped.size == (120, 70)
    blank = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(blank, format="PNG")
    assert autocrop(blank.getvalue()) == blank.getvalue()


def test_tail_keeps_the_end_of_long_output() -> None:
    assert tail("a" * 10) == "a" * 10
    assert tail("x" * 5000 + "END", 100).endswith("END") and len(tail("x" * 5000, 100)) == 101

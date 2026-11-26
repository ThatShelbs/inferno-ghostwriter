"""Run the code a model returned, on this computer, so the chart in the article is the chart the code makes.

This is the one place the app executes model-written code, and only when the author turns it on (``Experiment.run_code``).
It is a guarded local process, **not** a hard sandbox:

- the code is parsed first and must pass ``codecheck.problems`` (no shelling out, no ``eval``, known libraries only);
- it runs in a fresh, empty folder, in a throwaway environment made by ``uv run --no-project --with ...``;
- it gets a minimal environment (no API keys, tokens or the app's secrets), a time limit, and its whole process tree is
  killed on timeout.

The model's code is never edited. A small shim, started before it, turns ``plt.show()``, ``fig.show()``, ``chart.show()``
and Bokeh's ``show()`` into saved files, so the code stays exactly as returned (the article reports its line counts).
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image, ImageChops, ImageDraw

from inferno_ghostwriter.codecheck import PACKAGES, imports, problems

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 240
MAX_OUTPUT = 4000
BROWSER_BUDGET_MS = 8000

# Extra pip packages a library needs to save a picture, beyond the library itself.
COMPANIONS = {"altair": ["vl-convert-python"], "plotly": ["kaleido", "pandas"], "vega_datasets": ["pandas"], "seaborn": ["pandas"]}

SHIM = r"""
import atexit, json, os, runpy, sys

os.environ.setdefault("MPLBACKEND", "Agg")
CHART = "_shim_chart.png"
HTML = "chart.html"


def _patch():
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure

        def show(*args, **kwargs):
            if plt.get_fignums():
                plt.gcf().savefig(CHART, dpi=200, bbox_inches="tight")

        plt.show = show
        Figure.show = lambda self, *a, **k: self.savefig(CHART, dpi=200, bbox_inches="tight")
    except ImportError:
        pass
    try:
        import plotly.io as pio
        from plotly.basedatatypes import BaseFigure

        def show(fig, *args, **kwargs):
            pio.write_html(fig, HTML, include_plotlyjs=True, full_html=True)

        pio.show = show
        BaseFigure.show = lambda self, *a, **k: show(self)
    except ImportError:
        pass
    try:
        import altair as alt

        def show(self, *args, **kwargs):
            self.save(CHART, scale_factor=2)

        for name in ("Chart", "LayerChart", "ConcatChart", "HConcatChart", "VConcatChart", "FacetChart", "RepeatChart"):
            cls = getattr(alt, name, None)
            if cls is not None:
                cls.show = show
    except ImportError:
        pass
    try:
        import bokeh.io
        import bokeh.plotting
        from bokeh.resources import INLINE

        def show(obj, *args, **kwargs):
            bokeh.io.save(obj, filename=HTML, resources=INLINE, title="chart")

        def export_png(obj, *args, filename=None, **kwargs):
            show(obj)
            return filename or HTML

        for module in (bokeh.io, bokeh.plotting):
            module.show = show
        bokeh.io.export_png = export_png
        try:
            import bokeh.io.export as export

            export.export_png = export_png
        except ImportError:
            pass
    except ImportError:
        pass


def _rescue():
    # Code that builds a matplotlib/seaborn figure but never shows or saves it still has a chart: save the open one.
    import glob

    if glob.glob("*.png") or glob.glob("*.html"):
        return
    plt = sys.modules.get("matplotlib.pyplot")
    if plt is not None and plt.get_fignums():
        plt.gcf().savefig(CHART, dpi=200, bbox_inches="tight")


def _versions():
    try:
        _rescue()
    except Exception:
        pass
    found = {}
    for name in ("matplotlib", "seaborn", "plotly", "altair", "bokeh", "pandas", "numpy", "vega_datasets"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "__version__", None):
            found[name] = str(module.__version__)
    found["python"] = sys.version.split()[0]
    with open("_versions.json", "w", encoding="utf-8") as handle:
        json.dump(found, handle)


_patch()
atexit.register(_versions)
sys.argv = [sys.argv[1]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""

ENV_KEEP = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL",
    "UV_CACHE_DIR", "UV_PYTHON", "UV_PYTHON_INSTALL_DIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTP_PROXY",
    "HTTPS_PROXY", "NO_PROXY", "XDG_CACHE_HOME",
}  # fmt: skip


@dataclass
class RunResult:
    ok: bool
    png: bytes | None = None
    error: str = ""
    stdout: str = ""
    versions: dict[str, str] = field(default_factory=dict)


class Sandbox(Protocol):
    async def run(self, code: str) -> RunResult: ...


def packages_for(code: str) -> list[str]:
    """The pip packages the code needs (from its imports) and the helpers that let those libraries save a picture."""
    names: list[str] = []
    for module in sorted(imports(code)):
        if module in PACKAGES:
            names.append(PACKAGES[module])
            names += COMPANIONS.get(module, [])
    return sorted(set(names), key=str.lower)


def short_uv_cache() -> str | None:
    """A short uv cache folder on Windows, where plotly's long file names overflow the 260-character path limit.

    Without it ``uv run --with plotly`` fails with "The system cannot find the path specified". An existing
    ``UV_CACHE_DIR`` is respected; None means use uv's own default."""
    if sys.platform != "win32" or os.environ.get("UV_CACHE_DIR"):
        return None
    for root in (os.environ.get("SYSTEMDRIVE", "C:") + "\\", os.environ.get("PUBLIC", "")):
        if not root:
            continue
        folder = Path(root) / "gw-uv"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        return str(folder)
    return None


def scrubbed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Only what Python and uv need to run: no keys, tokens or anything the app keeps."""
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_KEEP}
    cache = short_uv_cache()
    if cache:
        env["UV_CACHE_DIR"] = cache
    env.update({"MPLBACKEND": "Agg", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra or {})
    return env


def find_browser() -> str | None:
    """An installed Edge or Chrome (for saving a Bokeh or Plotly page as a picture)."""
    candidates = [shutil.which(n) for n in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")]
    for root in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if root:
            candidates += [
                os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"),
            ]
    candidates += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=20, check=False)
        else:
            import signal

            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001 - the process may already be gone
        process.kill()


def _run_process(command: list[str], cwd: Path, env: dict[str, str], timeout: int) -> tuple[int | None, str, str]:
    """Run to completion; (None, ...) means it timed out and its whole tree was killed."""
    kwargs: dict[str, object] = {"start_new_session": True} if sys.platform != "win32" else {"creationflags": 0x08000000}
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **kwargs,  # type: ignore[call-overload]
    )
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        out, err = process.communicate()
        return None, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
    return process.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def autocrop(png: bytes, pad: int = 24) -> bytes:
    """Trim the white page around a browser screenshot of a chart."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    box = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255))).getbbox()
    if box is None:
        return png
    left, top, right, bottom = box
    image = image.crop((max(0, left - pad), max(0, top - pad), min(image.width, right + pad), min(image.height, bottom + pad)))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def tail(text: str, limit: int = MAX_OUTPUT) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


class LocalSandbox:
    """Runs code with uv in a scratch folder (see the module note for the limits)."""

    def __init__(self, uv: str, *, timeout: int = TIMEOUT_SECONDS) -> None:
        self.uv = uv
        self.timeout = timeout

    async def run(self, code: str) -> RunResult:
        issues = problems(code)
        if issues:
            return RunResult(False, error="The code was not run: " + "; ".join(issues))
        return await asyncio.to_thread(self._run, code)

    def _run(self, code: str) -> RunResult:
        with tempfile.TemporaryDirectory(prefix="ghostwriter-experiment-") as folder:
            work = Path(folder)
            (work / "script.py").write_text(code, encoding="utf-8")
            (work / "_shim.py").write_text(SHIM, encoding="utf-8")
            command = [self.uv, "run", "--no-project", "--quiet"]
            for package in packages_for(code):
                command += ["--with", package]
            command += ["python", "_shim.py", "script.py"]
            returncode, out, err = _run_process(command, work, scrubbed_env(), self.timeout)
            if returncode is None:
                return RunResult(False, error=f"The code ran longer than {self.timeout} seconds and was stopped.", stdout=tail(out))
            if returncode != 0:
                return RunResult(False, error=tail(err) or f"The code exited with status {returncode}.", stdout=tail(out))
            return self._collect(work, out)

    def _collect(self, work: Path, out: str) -> RunResult:
        try:
            versions = json.loads((work / "_versions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            versions = {}
        own = [p for p in work.glob("*.png") if p.name != "_shim_chart.png"]
        shim = work / "_shim_chart.png"
        # A picture the code saved itself wins over the one the shim saved for a show() call.
        if own:
            return RunResult(True, png=max(own, key=lambda p: p.stat().st_mtime).read_bytes(), stdout=tail(out), versions=versions)
        if shim.exists():
            return RunResult(True, png=shim.read_bytes(), stdout=tail(out), versions=versions)
        pages = sorted(work.glob("*.html"), key=lambda p: p.stat().st_mtime)
        if pages:
            return self._screenshot(pages[-1], work, out, versions)
        return RunResult(False, error="The code ran but did not save or show a chart.", stdout=tail(out), versions=versions)

    def _screenshot(self, page: Path, work: Path, out: str, versions: dict[str, str]) -> RunResult:
        browser = find_browser()
        if browser is None:
            return RunResult(
                False,
                error="This chart is an interactive page, and saving it as a picture needs Edge or Chrome installed.",
                versions=versions,
            )
        target = work / "_page.png"
        command = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
            f"--user-data-dir={work / '_profile'}", f"--screenshot={target}", "--window-size=1500,1000",
            f"--virtual-time-budget={BROWSER_BUDGET_MS}", page.as_uri(),
        ]  # fmt: skip
        returncode, _, err = _run_process(command, work, scrubbed_env(), 90)
        if returncode != 0 or not target.exists():
            return RunResult(False, error="Edge or Chrome could not save the chart page as a picture. " + tail(err, 500), versions=versions)
        return RunResult(True, png=autocrop(target.read_bytes()), stdout=tail(out), versions=versions)


class NoSandbox:
    """Tests and demo mode: no code is run; a stand-in picture shows where the real chart would go."""

    def __init__(self, *, fail_first: int = 0, unavailable: str = "") -> None:
        self.calls: list[str] = []
        self.fail_first = fail_first
        # Set when nothing can run code on this computer: every run then reports it instead of drawing a stand-in.
        self.unavailable = unavailable

    async def run(self, code: str) -> RunResult:
        if self.unavailable:
            return RunResult(False, error=self.unavailable)
        self.calls.append(code)
        issues = problems(code)
        if issues:
            return RunResult(False, error="The code was not run: " + "; ".join(issues))
        if self.fail_first > 0:
            self.fail_first -= 1
            return RunResult(False, error="Traceback (most recent call last):\nNameError: name 'df' is not defined")
        image = Image.new("RGB", (1200, 720), "#ffffff")
        draw = ImageDraw.Draw(image)
        for i, height in enumerate((220, 340, 280, 420, 360)):
            left = 120 + i * 200
            draw.rectangle((left, 640 - height, left + 140, 640), fill=("#440154", "#3b528b", "#21918c", "#5ec962", "#fde725")[i])
        out = io.BytesIO()
        image.save(out, format="PNG")
        return RunResult(True, png=out.getvalue(), versions={"python": sys.version.split()[0]})

"""Build the kit's files from the post, its images and the design. Pure code: nothing here calls a model or runs code."""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inferno_ghostwriter.db import Project, ProjectImage
from inferno_ghostwriter.export.render import Figure, figures_for, markdown_with_images
from inferno_ghostwriter.images import PLACEHOLDER_RE
from inferno_ghostwriter.kit.check import requirements
from inferno_ghostwriter.kit.design import COLORS, ChartData, KitDesign
from inferno_ghostwriter.writer import split_title

NOTEBOOK = "notebook.ipynb"
CLOSE_ROOMS = ("hero", "meme")


@dataclass
class Repo:
    """Where the kit lives on GitHub: decides the Colab link and how notebook images are linked."""

    owner: str
    name: str
    public: bool

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def colab_url(self) -> str:
        return f"https://colab.research.google.com/github/{self.owner}/{self.name}/blob/main/{NOTEBOOK}"

    @property
    def raw_base(self) -> str:
        return f"https://raw.githubusercontent.com/{self.owner}/{self.name}/main/"


# -- chart data ----------------------------------------------------------------------------------


def _values(spec: Any) -> list[dict[str, Any]] | None:
    """The inline rows of a Vega-Lite spec: top-level data, named datasets, or the first layer that has some."""
    if not isinstance(spec, dict):
        return None
    data = spec.get("data")
    if isinstance(data, dict) and isinstance(data.get("values"), list):
        return [row for row in data["values"] if isinstance(row, dict)]
    datasets = spec.get("datasets")
    if isinstance(datasets, dict):
        for rows in datasets.values():
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    for key in ("layer", "hconcat", "vconcat", "concat"):
        for part in spec.get(key) or []:
            found = _values(part)
            if found:
                return found
    return None


def chart_data(images: list[ProjectImage]) -> list[ChartData]:
    """The post's charts whose Vega-Lite spec carries its rows, in reading order."""
    out: list[ChartData] = []
    for image in sorted(images, key=lambda i: i.position):
        if image.kind != "chart" or image.status != "ready":
            continue
        try:
            rows = _values(json.loads(image.spec))
        except (ValueError, TypeError):
            continue
        if not rows:
            continue
        columns: list[str] = []
        for row in rows:
            columns.extend(k for k in row if k not in columns)
        out.append(
            ChartData(
                slot_id=image.slot_id, file=f"chart_{image.slot_id}.csv", columns=columns, rows=rows, caption=image.caption, alt=image.alt
            )
        )
    return out


def other_images(images: list[ProjectImage], charts: list[ChartData]) -> list[tuple[str, str, str]]:
    with_data = {c.slot_id for c in charts}
    return [
        (i.slot_id, i.kind, i.alt or i.purpose or i.caption)
        for i in sorted(images, key=lambda i: i.position)
        if i.status == "ready" and i.slot_id not in with_data and i.kind not in CLOSE_ROOMS and i.slot_id not in CLOSE_ROOMS
    ]


def _csv(chart: ChartData) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=chart.columns, lineterminator="\n")
    writer.writeheader()
    for row in chart.rows:
        writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    return out.getvalue().encode("utf-8")


# -- notebook ------------------------------------------------------------------------------------


def _norm(text: str) -> str:
    text = re.sub(r"[*_`>#\[\]()]", " ", text.lower())
    text = re.sub(r"[“”\"'’‘]", "", text)
    return re.sub(r"\s+", " ", text).strip(" .,;:!?…")


def blocks_of(markdown: str) -> list[str]:
    """The post split at blank lines, with fenced code kept whole."""
    blocks: list[str] = []
    current: list[str] = []
    fenced = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not line.strip() and not fenced:
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _anchor_index(anchor: str, blocks: list[str]) -> int | None:
    quote = _norm(anchor)
    if len(quote.split()) < 4:
        return None
    return next((i for i, block in enumerate(blocks) if quote in _norm(block)), None)


def _source(text: str) -> list[str]:
    lines = text.strip("\n").split("\n")
    return [line + "\n" for line in lines[:-1]] + [lines[-1]]


class _Notebook:
    def __init__(self) -> None:
        self.cells: list[dict[str, Any]] = []

    def markdown(self, text: str) -> None:
        if text.strip():
            self.cells.append({"cell_type": "markdown", "id": f"cell-{len(self.cells) + 1}", "metadata": {}, "source": _source(text)})

    def code(self, text: str) -> None:
        self.cells.append(
            {
                "cell_type": "code",
                "execution_count": None,
                "id": f"cell-{len(self.cells) + 1}",
                "metadata": {},
                "outputs": [],
                "source": _source(text),
            }
        )

    def json(self) -> bytes:
        notebook = {
            "cells": self.cells,
            "metadata": {
                "colab": {"provenance": []},
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python"},
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        return (json.dumps(notebook, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def setup_code(repo: Repo | None) -> str:
    colors = ", ".join(f'"{c}"' for c in COLORS)
    if repo is not None and repo.public:
        head = (
            "# In Google Colab, first fetch this repository so the data and images are here. On your own machine this does nothing.\n"
            "import sys\n\n"
            'if "google.colab" in sys.modules:\n'
            f"    !git clone --depth 1 {repo.url}.git\n"
            f"    %cd {repo.name}\n"
            "    %pip install -q -r requirements.txt\n\n"
        )
    else:
        head = "# Run this notebook from the repository folder so `data/` and `assets/` are next to it.\n\n"
    folder = 'from pathlib import Path\n\nPath("data").mkdir(exist_ok=True)  # where the data cells save their CSV files\n\n'
    return head + folder + f"# The kit's chart colors (inferno, dark to light). Every chart below uses them.\nCOLORS = [{colors}]"


def _figure_markdown(fig: Figure, src: str) -> str:
    caption = f"\n\n*{fig.full_caption}*" if fig.full_caption else ""
    return f"![{fig.alt}]({src}){caption}"


def notebook(
    project: Project,
    figures: dict[str, Figure],
    design: KitDesign,
    charts: list[ChartData],
    *,
    author: str,
    repo: Repo | None,
    article_url: str = "",
) -> bytes:
    title, _ = split_title(project.markdown)
    title = title or project.title or "this post"
    prefix = repo.raw_base if repo is not None and repo.public else ""
    blocks = blocks_of(project.markdown)

    # Code cells after the block they belong to; anything unplaced goes to the end.
    after: dict[int, list[tuple[str, str]]] = {}
    loose: list[tuple[str, str]] = []
    for cell in design.cells:
        at = _anchor_index(cell.anchor, blocks)
        (after.setdefault(at, []) if at is not None else loose).append((f"**Try it:** {cell.lead_in}", cell.code))
    image_at = {m.group(1): i for i, b in enumerate(blocks) if (m := PLACEHOLDER_RE.fullmatch(b.strip()))}
    for chart in design.charts:
        at = image_at.get(chart.slot_id)
        (after.setdefault(at, []) if at is not None else loose).append((f"**Rebuild this chart:** {chart.lead_in}", chart.code))

    nb = _Notebook()
    by = f" by {author}" if author else ""
    article = f"[*{title}*]({article_url})" if article_url else f"*{title}*"
    intro = f"> **Hands-on companion** to {article}{by}. The whole article is here; run the cells top to bottom to rebuild every chart.\n"
    if repo is not None and repo.public:
        intro += f">\n> [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)]({repo.colab_url})\n"
    nb.markdown(intro)
    nb.markdown("## Before you start")
    nb.code(setup_code(repo))
    if design.datasets or charts:
        lines = ["### Get the data"]
        if charts:
            lines.append("The charts read their numbers from the CSV files in `data/`, the same numbers as in the article.")
        if design.datasets:
            lines.append("These cells make the rest of the data (also in `make_data.py`).")
        nb.markdown("\n\n".join(lines))
        for dataset in design.datasets:
            nb.markdown(f"`data/{dataset.file}`: {dataset.description}")
            nb.code(dataset.code)
    nb.markdown("---")

    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            nb.markdown("\n\n".join(buffer))
            buffer.clear()

    for i, block in enumerate(blocks):
        placeholder = PLACEHOLDER_RE.fullmatch(block.strip())
        if placeholder:
            fig = figures.get(placeholder.group(1))
            if fig is None or not fig.file_name:
                continue
            block = _figure_markdown(fig, f"{prefix}assets/{fig.file_name}")
        elif block.lstrip().startswith("#"):
            flush()
        buffer.append(block)
        for lead_in, code in after.get(i, []):
            flush()
            nb.markdown(lead_in)
            nb.code(code)
    flush()

    ending = ["---", "## Keep going"]
    if design.prompts:
        ending.append("Starter prompts from this post are in `prompts/starter_prompts.md`.")
    if design.scripts:
        ending.append("Standalone scripts: " + ", ".join(f"`code/{s.file}`" for s in design.scripts) + ".")
    nb.markdown("\n\n".join(ending))
    for lead_in, code in loose:
        nb.markdown(lead_in)
        nb.code(code)
    return nb.json()


# -- the other files -----------------------------------------------------------------------------


def readme(project: Project, design: KitDesign, files: list[str], *, author: str, repo: Repo | None, article_url: str) -> str:
    title, subtitle = split_title(project.markdown)
    title = title or project.title or "Hands-on kit"
    out = [f"# {title}", ""]
    if subtitle:
        out += [f"*{subtitle}*", ""]
    badges = []
    if repo is not None and repo.public:
        badges.append(f"[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)]({repo.colab_url})")
    if article_url:
        badges.append(f"[Read the article]({article_url})")
    if badges:
        out += [" ".join(badges), ""]
    out += [
        f"The hands-on companion to the article{f' by {author}' if author else ''}: the whole post as a Jupyter notebook, with the "
        "code, data and images to run it and rebuild every chart yourself.",
        "",
    ]
    if design.learn:
        out += ["## What you'll learn", "", *[f"- {item}" for item in design.learn], ""]
    out += ["## Run it", ""]
    if repo is not None and repo.public:
        out += [f"**In your browser:** [open `{NOTEBOOK}` in Google Colab]({repo.colab_url}) and run the cells top to bottom.", ""]
    clone = f"git clone {repo.url}.git\ncd {repo.name}\n" if repo is not None else ""
    out += [
        "**On your machine** (Python 3.10+):",
        "",
        "```bash",
        f"{clone}python -m venv .venv",
        "source .venv/bin/activate   # Windows: .venv\\Scripts\\activate",
        "pip install -r requirements.txt jupyterlab",
        f"jupyter lab {NOTEBOOK}",
        "```",
        "",
    ]
    if "make_data.py" in files:
        out += ["`python make_data.py` rebuilds the data files on their own.", ""]
    guide = {
        NOTEBOOK: "the full article with runnable cells",
        "article.md": "the article as plain Markdown",
        "data/": "the CSV files behind the charts",
        "make_data.py": "makes the rest of the data",
        "code/": "the main examples as standalone scripts",
        "prompts/starter_prompts.md": "prompts from the post, ready to adapt",
        "assets/": "every image in the article",
        "requirements.txt": "the Python packages the code uses",
    }
    present = set(files) | {f.split("/")[0] + "/" for f in files if "/" in f}
    out += ["## What's inside", "", "| Path | What it is |", "| --- | --- |"]
    out += [f"| `{path}` | {about} |" for path, about in guide.items() if path in present]
    out += ["", "## License", "", "MIT: see `LICENSE`. Images are credited in `assets/credits.md`.", ""]
    return "\n".join(out)


def mit_license(author: str) -> str:
    return f"""MIT License

Copyright (c) {datetime.now(UTC).year} {author or "the author"}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def _prompts_md(title: str, design: KitDesign) -> str:
    out = ["# Starter prompts", "", f"Prompts from *{title}*, ready to adapt. Replace the [BRACKETED] parts with your own details.", ""]
    for prompt in design.prompts:
        out += [f"## {prompt.title}", "", f"_{prompt.when}_", "", "```text", prompt.prompt.strip(), "```", ""]
    return "\n".join(out)


def _make_data(design: KitDesign) -> str:
    out = [
        '"""Make the kit\'s data files. Run it from the repository root: python make_data.py"""',
        "",
        "from pathlib import Path",
        "",
        'Path("data").mkdir(exist_ok=True)',
    ]
    for dataset in design.datasets:
        out += ["", "", f"# data/{dataset.file}: {dataset.description}", dataset.code.strip()]
    return "\n".join(out) + "\n"


def _credits(figures: dict[str, Figure]) -> str:
    out = ["# Image credits", ""]
    out += [f"- `{f.file_name}`: {f.full_caption or f.alt}" for f in figures.values() if f.file_name]
    return "\n".join(out) + "\n"


GITIGNORE = ".ipynb_checkpoints/\n__pycache__/\n.venv/\n.env\n.DS_Store\n"


def kit_files(
    project: Project,
    images: list[ProjectImage],
    image_dir: Path,
    design: KitDesign,
    *,
    author: str,
    repo: Repo | None = None,
    article_url: str = "",
) -> dict[str, bytes]:
    """Every file of the kit, path -> bytes."""
    ready = [i for i in images if i.status == "ready" and i.file_name]
    figures = figures_for(ready, image_dir)
    charts = chart_data(ready)
    title, _ = split_title(project.markdown)
    title = title or project.title or "the post"
    files: dict[str, bytes] = {}
    for fig in figures.values():
        if fig.path is not None and fig.path.exists() and fig.file_name:
            files[f"assets/{fig.file_name}"] = fig.path.read_bytes()
    files["assets/credits.md"] = _credits(figures).encode()
    for chart in charts:
        files[f"data/{chart.file}"] = _csv(chart)
    if design.datasets:
        files["make_data.py"] = _make_data(design).encode()
    for script in design.scripts:
        files[f"code/{script.file}"] = (f'# {script.title}, from "{title}"\n\n' + script.code.strip() + "\n").encode()
    if design.prompts:
        files["prompts/starter_prompts.md"] = _prompts_md(title, design).encode()
    files["article.md"] = markdown_with_images(project.markdown, figures, prefix="assets/").encode()
    files[NOTEBOOK] = notebook(project, figures, design, charts, author=author, repo=repo, article_url=article_url)
    code = (
        [d.code for d in design.datasets]
        + [c.code for c in design.cells]
        + [c.code for c in design.charts]
        + [s.code for s in design.scripts]
    )
    files["requirements.txt"] = ("\n".join(requirements(code)) + "\n").encode()
    files["LICENSE"] = mit_license(author).encode()
    files[".gitignore"] = GITIGNORE.encode()
    files["README.md"] = readme(project, design, sorted(files), author=author, repo=repo, article_url=article_url).encode()
    return dict(sorted(files.items()))


def write_kit(folder: Path, files: dict[str, bytes]) -> None:
    """Replace the folder's contents with ``files``, keeping its ``.git`` history."""
    folder.mkdir(parents=True, exist_ok=True)
    for child in folder.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    for path, data in files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def zip_kit(slug: str, files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files.items():
            zf.writestr(f"{slug}/{path}", data)
    return buffer.getvalue()

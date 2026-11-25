"""Checks for the kit's code, without ever running it.

Model-written code is never executed by the app. Each block must parse as Python 3, may import only the standard
library and the beginner data stack below, and must not shell out. The reader runs it; the kit only promises it is
well formed.
"""

from __future__ import annotations

import ast
import sys

# Import name -> the pip package that provides it (for requirements.txt).
PACKAGES: dict[str, str] = {
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "altair": "altair",
    "vega_datasets": "vega_datasets",
    "sklearn": "scikit-learn",
    "scipy": "scipy",
    "statsmodels": "statsmodels",
    "requests": "requests",
    "IPython": "ipython",
    "tqdm": "tqdm",
    "pyarrow": "pyarrow",
    "polars": "polars",
    "networkx": "networkx",
    "duckdb": "duckdb",
    "anthropic": "anthropic",
    "openai": "openai",
}

# Standard-library modules a beginner notebook has no business with.
BLOCKED = {"subprocess", "ctypes", "socket", "shutil", "multiprocessing", "pty", "signal", "winreg"}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__"}

# IPython magics and shell lines are fine in a notebook but are not Python; they are ignored for the parse check.
_MAGIC = ("%", "!")


def _source(code: str) -> str:
    return "\n".join("" if line.lstrip().startswith(_MAGIC) else line for line in code.splitlines())


def imports(code: str) -> set[str]:
    """Top-level module names a block imports (empty if it does not parse)."""
    try:
        tree = ast.parse(_source(code))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def problems(code: str) -> list[str]:
    """Why a block cannot go in the kit; empty when it is fine."""
    if not code.strip():
        return ["the code is empty"]
    try:
        tree = ast.parse(_source(code))
    except SyntaxError as exc:
        return [f"syntax error on line {exc.lineno}: {exc.msg}"]
    out: list[str] = []
    for name in sorted(imports(code)):
        if name in BLOCKED:
            out.append(f"`{name}` is not allowed in a beginner kit")
        elif name not in PACKAGES and name not in sys.stdlib_module_names:
            out.append(f"`{name}` is not an allowed library (use: {', '.join(sorted(PACKAGES))})")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            out.append(f"`{node.func.id}()` is not allowed")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "system"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ):
            out.append("`os.system()` is not allowed")
    return out


def requirements(blocks: list[str]) -> list[str]:
    """The pip packages the kit's code imports, sorted, one per line of requirements.txt."""
    names: set[str] = set()
    for block in blocks:
        names.update(PACKAGES[name] for name in imports(block) if name in PACKAGES)
    if "plotly" in names:
        # Plotly Express needs pandas, and figures render in classic Jupyter with nbformat.
        names.update({"pandas", "nbformat"})
    return sorted(names, key=str.lower)

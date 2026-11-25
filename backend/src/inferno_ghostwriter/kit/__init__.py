"""The hands-on kit: a post's companion repository (notebook, data, code, prompts, images), downloadable or pushed to GitHub.

``fit`` says whether a post calls for one (no model call), ``design`` asks Claude for the code and prompts once,
``build`` writes the files by code, ``check`` vets the code without running it, ``github`` pushes with the author's
own GitHub CLI, and ``service`` ties them to the project.
"""

from inferno_ghostwriter.kit.design import LIBRARIES, LIBRARY_LABELS, KitDesign
from inferno_ghostwriter.kit.fit import KitFit, kit_fit
from inferno_ghostwriter.kit.github import GitHubCLI, GitHubError, GitHubStatus
from inferno_ghostwriter.kit.service import KIT_JOBS, KitContext, add_link, build_kit, kit_folder, push_kit, render_kit

__all__ = [
    "KIT_JOBS",
    "LIBRARIES",
    "LIBRARY_LABELS",
    "GitHubCLI",
    "GitHubError",
    "GitHubStatus",
    "KitContext",
    "KitDesign",
    "KitFit",
    "add_link",
    "build_kit",
    "kit_fit",
    "kit_folder",
    "push_kit",
    "render_kit",
]

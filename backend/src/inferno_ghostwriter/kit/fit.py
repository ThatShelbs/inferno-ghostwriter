"""Whether a post calls for a hands-on kit, read from the post itself with no model call."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from inferno_ghostwriter.db import Project, ProjectImage
from inferno_ghostwriter.writer.formulas import ARTICLE_TYPES, detect_article_type

# Article types readers follow along with.
HANDS_ON_TYPES = {"how_to", "tutorial", "hands_on", "tool_review", "case_study", "comparison"}
RECOMMEND_AT = 2

_FENCE = re.compile(r"```([\w+-]*)[^\n]*\n(.*?)```", re.DOTALL)
_PROMPT_LANGS = {"prompt", "text", "txt", "markdown", "md", ""}
_PROMPT_NEAR = re.compile(r"\bprompts?\b", re.IGNORECASE)
_DATA_WORDS = re.compile(
    r"\b(datasets?|data ?frames?|csv|regression|charts?|plots?|visuali[sz]\w*|notebooks?|jupyter|analysis|analy[sz]e|"
    r"distributions?|correlations?|experiments?|forecasts?|features?|python|sql|queries|pandas|numpy)\b",
    re.IGNORECASE,
)


@dataclass
class KitFit:
    recommended: bool
    article_type: str
    reasons: list[str] = field(default_factory=list)


def article_type_of(project: Project) -> str:
    chosen = str((project.dials or {}).get("article_type") or "auto")
    return chosen if chosen != "auto" else detect_article_type(project.prompt or "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def kit_fit(project: Project, images: list[ProjectImage]) -> KitFit:
    markdown = project.markdown or ""
    reasons: list[str] = []
    score = 0
    fences = _FENCE.findall(markdown)
    code = [body for lang, body in fences if lang.lower() in ("python", "py", "python3", "ipython", "sql", "bash", "sh")]
    if code:
        score += 2
        reasons.append(f"{_plural(len(code), 'code example')} readers can run")
    prompts = 0
    for match in _FENCE.finditer(markdown):
        before = markdown[max(0, match.start() - 200) : match.start()]
        if match.group(1).lower() in _PROMPT_LANGS and _PROMPT_NEAR.search(before + match.group(2)[:200]):
            prompts += 1
    if prompts:
        score += 1
        reasons.append(f"{_plural(prompts, 'prompt')} to keep as starters")
    charts = [i for i in images if i.kind == "chart" and i.status == "ready"]
    if charts:
        score += 2
        reasons.append(f"{_plural(len(charts), 'chart')} to recreate from data")
    handson = [i for i in images if i.kind == "hands_on_viz" and i.status == "ready"]
    if handson:
        score += 2
        reasons.append(f"{_plural(len(handson), 'chart')} drawn by the post's own code")
    if getattr(project, "experiment", None):
        score += RECOMMEND_AT
        reasons.append("a library experiment: every prompt and its code, ready to run")
    kind = article_type_of(project)
    if kind in HANDS_ON_TYPES:
        score += 2
        label = next((t.label for t in ARTICLE_TYPES if t.id == kind), kind)
        reasons.append(f"a {label.lower()} post")
    if len(_DATA_WORDS.findall(_FENCE.sub("", markdown))) >= 6:
        score += 1
        reasons.append("it works with data")
    return KitFit(recommended=score >= RECOMMEND_AT, article_type=kind, reasons=reasons)

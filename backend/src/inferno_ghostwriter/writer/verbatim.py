"""Blocks the author's brief shows (a prompt, a script, an output) must reach the post character for character.

The writer is told so; the editor is told which blocks are missing; and code puts a block back after its lead-in if it
still went missing. Fenced blocks are compared exactly. A long quoted block (three or more ``>`` lines) is compared line
by line, since the post may quote it differently indented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from inferno_ghostwriter.experiments.compose import fenced
from inferno_ghostwriter.images.codeblocks import code_blocks

MIN_CHARS = 20
MIN_QUOTE_LINES = 3
_HEADING = re.compile(r"^## ", re.MULTILINE)


@dataclass
class BriefBlock:
    """One block from the brief: its text, how to show it (language; "" for a quote) and the paragraph that led into it."""

    text: str
    language: str
    lead_in: str
    quoted: bool = False


def _unquote(line: str) -> str:
    return re.sub(r"^\s*>\s?", "", line)


def _paragraph_before(lines: list[str], index: int) -> str:
    """The prose paragraph right above line ``index`` of the brief (empty when there is none)."""
    end = index - 1
    while end >= 0 and not lines[end].strip():
        end -= 1
    start = end
    while start > 0 and lines[start - 1].strip():
        start -= 1
    if end < 0 or lines[end].lstrip().startswith(("```", "~~~", ">", "#")):
        return ""
    return " ".join(lines[start : end + 1]).strip()


def brief_blocks(prompt: str) -> list[BriefBlock]:
    """The blocks of the brief the post must carry: fenced code and prompts, and long quoted blocks."""
    lines = prompt.split("\n")
    found: list[BriefBlock] = []
    for block in code_blocks(prompt):
        if len(block.code.strip()) >= MIN_CHARS:
            found.append(BriefBlock(block.code, block.language, _paragraph_before(lines, block.start)))
    run: list[int] = []
    for i, line in enumerate([*lines, ""]):
        if line.lstrip().startswith(">"):
            run.append(i)
            continue
        if len(run) >= MIN_QUOTE_LINES:
            text = "\n".join(_unquote(lines[j]) for j in run).strip()
            if len(text) >= MIN_CHARS:
                found.append(BriefBlock(text, "", _paragraph_before(lines, run[0]), quoted=True))
        run = []
    return found


def _present(markdown: str, block: BriefBlock) -> bool:
    if not block.quoted:
        return fenced(block.text, block.language) in markdown or block.text in markdown
    plain = "\n".join(_unquote(line) for line in markdown.split("\n"))
    return all(line.strip() in plain for line in block.text.split("\n") if line.strip())


def missing_blocks(markdown: str, blocks: list[BriefBlock]) -> list[BriefBlock]:
    return [b for b in blocks if not _present(markdown, b)]


def format_missing(markdown: str, prompt: str) -> str:
    """The editor's note about brief blocks that are not in the draft; empty when none is missing."""
    missing = missing_blocks(markdown, brief_blocks(prompt))
    if not missing:
        return ""
    shown = "\n\n".join(f"```{b.language}\n{b.text}\n```" if not b.quoted else "> " + b.text.replace("\n", "\n> ") for b in missing)
    return (
        "\nThe author's brief contains blocks that must appear in the post exactly, character for character (a prompt, code "
        "or output the post shows). These are missing or changed; tell the reviser to put each one back as a fenced block "
        f"right after the sentence that introduces it, without editing a character:\n{shown}\n"
    )


def restore(markdown: str, prompt: str) -> str:
    """Put back every brief block that is missing: after its lead-in when that can be found, else before the closing section."""
    out = markdown
    for block in missing_blocks(markdown, brief_blocks(prompt)):
        shown = fenced(block.text, block.language) if not block.quoted else "> " + block.text.replace("\n", "\n> ")
        out = _insert(out, block, shown)
    return out


def _insert(markdown: str, block: BriefBlock, shown: str) -> str:
    sentence = re.split(r"(?<=[.!?:])\s+", block.lead_in)[-1].strip(" *_") if block.lead_in else ""
    at = markdown.find(sentence) if len(sentence) >= 12 else -1
    if at >= 0:
        end = markdown.find("\n\n", at)
        end = len(markdown) if end < 0 else end
        return markdown[:end] + "\n\n" + shown + markdown[end:]
    headings = list(_HEADING.finditer(markdown))
    if len(headings) > 1:
        cut = headings[-1].start()
        return markdown[:cut].rstrip() + "\n\n" + shown + "\n\n" + markdown[cut:]
    return markdown.rstrip() + "\n\n" + shown + "\n"

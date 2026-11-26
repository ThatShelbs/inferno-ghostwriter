"""Find the pieces of a post's Markdown (paragraphs, fenced code, images) and the code block right above an image.

Lives under ``images`` (not ``writer``) so the hands-on image builder can use it without importing the writer package.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from inferno_ghostwriter.images.base import PLACEHOLDER_RE

FENCE = re.compile(r"^\s*(```|~~~)")
LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
# A library experiment's marker (see experiments/compose.py): code puts the scenario's prompt, code and chart here.
EXPERIMENT_MARKER = re.compile(r"\{\{experiment:[A-Za-z0-9_\-]+\}\}")


@dataclass
class Block:
    start: int  # first line index
    end: int  # last line index
    kind: str  # prose | heading | subheading | code | list | table | quote | image
    text: str


def parse_blocks(lines: list[str]) -> list[Block]:
    out: list[Block] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if FENCE.match(line):
            j = i + 1
            while j < len(lines) and not FENCE.match(lines[j]):
                j += 1
            out.append(Block(i, min(j, len(lines) - 1), "code", ""))
            i = j + 1
            continue
        j = i
        while j + 1 < len(lines) and lines[j + 1].strip() and not FENCE.match(lines[j + 1]):
            j += 1
        text = "\n".join(lines[i : j + 1]).strip()
        first = lines[i].strip()
        if PLACEHOLDER_RE.fullmatch(first) or first.startswith("![") or EXPERIMENT_MARKER.fullmatch(first):
            kind = "image"
        elif first.startswith("## ") or first.startswith("# "):
            kind = "heading"
        elif first.startswith("#"):
            kind = "subheading"
        elif LIST.match(first):
            kind = "list"
        elif first.startswith("|"):
            kind = "table"
        elif first.startswith(">"):
            kind = "quote"
        elif first.startswith("<"):
            kind = "html"
        else:
            kind = "prose"
        out.append(Block(i, j, kind, text))
        i = j + 1
    return out


@dataclass
class CodeBlock:
    """A fenced code block in the post: its language, its exact body and where its fences are (line indexes)."""

    language: str
    code: str
    start: int
    end: int


def _code_block(lines: list[str], block: Block) -> CodeBlock:
    info = lines[block.start].strip().lstrip("`~").strip()
    closed = block.end > block.start and FENCE.match(lines[block.end]) is not None
    body = lines[block.start + 1 : block.end if closed else block.end + 1]
    return CodeBlock((info.split() or [""])[0].lower(), "\n".join(body), block.start, block.end)


def code_blocks(markdown: str) -> list[CodeBlock]:
    """Every fenced block, in order."""
    lines = markdown.split("\n")
    return [_code_block(lines, b) for b in parse_blocks(lines) if b.kind == "code"]


def code_before(markdown: str, slot_id: str) -> CodeBlock | None:
    """The fenced block directly above ``{{image:slot_id}}`` (nothing between them), or None."""
    lines = markdown.split("\n")
    found_blocks = parse_blocks(lines)
    for index, block in enumerate(found_blocks):
        found = PLACEHOLDER_RE.fullmatch(block.text.strip()) if block.kind == "image" else None
        if found and found.group(1) == slot_id:
            previous = found_blocks[index - 1] if index else None
            return _code_block(lines, previous) if previous is not None and previous.kind == "code" else None
    return None


def replace_code(markdown: str, block: CodeBlock, new_code: str) -> str:
    """The post with one block's body swapped for ``new_code`` (fences and everything else untouched)."""
    lines = markdown.split("\n")
    closed = block.end > block.start and FENCE.match(lines[block.end]) is not None
    stop = block.end if closed else block.end + 1
    return "\n".join([*lines[: block.start + 1], *new_code.strip("\n").split("\n"), *lines[stop:]])

"""Keeping image ideas tied to the story, and varied: anchors and angle cards.

* **Anchors.** Every pitch quotes the passage of the post it riffs on (``anchor``). Code checks the quote is really in
  the post (``anchored``); a pitch with a made-up anchor is ranked last, so the picture always serves a real moment.
* **Angle cards.** Before pitching, code deals a few seeded random cards into the prompt: two moments sampled from the
  post, a family mix and a tone. Every card must be covered, so two runs on the same post pitch different ideas while
  staying on the story. Pass a fresh ``seed`` on every redraw.
"""

from __future__ import annotations

import random
import re

from inferno_ghostwriter.images.base import PLACEHOLDER_RE

TONES = (
    "deadpan and dry",
    "warm and relatable",
    "nerdy and precise",
    "absurd escalation",
    "quietly confident",
    "self-deprecating",
)


def _norm(text: str) -> str:
    text = re.sub(r"[*_`>#\[\]()]", " ", text.lower())
    text = re.sub(r"[“”\"'’‘]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def anchored(anchor: str, markdown: str) -> bool:
    """Whether a pitch's quote appears in the post (ignoring case, punctuation marks, Markdown and spacing).

    An empty anchor is allowed (older pitches have none); a quote of three words or fewer proves nothing, so it passes."""
    quote = _norm(anchor).strip(" .,;:!?…")
    if len(quote.split()) <= 3:
        return True
    return quote in _norm(markdown)


def moments(markdown: str, count: int, rng: random.Random, *, max_chars: int = 320) -> list[str]:
    """``count`` passages sampled from the post's body paragraphs (not headings, code or image lines)."""
    body = PLACEHOLDER_RE.sub("", markdown)
    body = re.sub(r"```.*?```", "", body, flags=re.DOTALL)
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n", body) if len(p.strip()) > 80 and not p.lstrip().startswith(("#", "|", "-", "*", ">", "!["))
    ]
    if not paragraphs:
        return []
    picked = rng.sample(paragraphs, min(count, len(paragraphs)))
    return [p if len(p) <= max_chars else p[:max_chars].rsplit(" ", 1)[0] + " ..." for p in picked]


def deal(markdown: str, *, seed: int, families: dict[str, str] | None = None, humor: int = 5) -> str:
    """The angle cards for one pitching round, as a prompt block."""
    rng = random.Random(seed)
    lines = ["Angle cards for this round (dealt at random; cover every card, so this round differs from the last):"]
    for i, moment in enumerate(moments(markdown, 2, rng), start=1):
        lines.append(f"- Moment card {i}: at least one idea must riff on this passage:\n  > {moment}")
    if families:
        ids = list(families)
        picks = rng.sample(ids, min(3, len(ids)))
        lines.append("- Family card: include at least one idea from each of: " + ", ".join(f"`{f}` ({families[f]})" for f in picks))
    tone = rng.choice(TONES[:3] if humor <= 3 else TONES)
    lines.append(f"- Tone card: one idea is {tone}.")
    return "\n".join(lines)

"""The judge for every image: one call ranks the pitched ideas, one vision call ranks the drawn candidates.

1. ``rank_pitches`` scores every pitch as text (story fit, clarity at a glance, surprise) and may veto one that is
   false, off-topic or cannot be drawn well. For memes it may also punch up the winner's words.
2. ``judge_sheet`` looks at every drawn candidate at once (one image each, in order), together with the author's own
   reference images when the library has a match (``images/references.py``): "does this read as the original meme",
   "does this meet this bar". It says in one sentence what each picture shows to a stranger, scores it and gives one
   concrete fix. The best few are refined with their fix and shown to the author as finalists.

Optional judges contribute to the score. Claude's judgment has the larger share and controls vetoes and fixes.
Neither call ever fails an image: on an error (or a connection that cannot send pictures) the pitch order stands.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.llm.base import LLMImagesUnsupportedError, T, UsageSink
from inferno_ghostwriter.llm.router import lead_provider
from inferno_ghostwriter.llm.secondary import MODEL_IDS
from inferno_ghostwriter.prompts import raw, render

log = logging.getLogger(__name__)

MODELS = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"}


class SlotWords(BaseModel):
    slot: str
    text: str


class PitchScore(BaseModel):
    candidate: int = Field(description="Index of the pitch, from 0.")
    story_fit: int = Field(description="1-10: is it about THIS post's point, so a reader of the post nods?")
    clarity: int = Field(description="1-10: does a stranger get it in three seconds at phone size?")
    surprise: int = Field(description="1-10: is it fresh, funny or striking rather than the obvious picture?")
    veto: bool = Field(False, description="True only if it is false, off-topic, mean, or cannot be drawn well in its format.")
    note: str = Field(description="One line: the strongest point, then the biggest risk.")


class PitchRanking(BaseModel):
    scores: list[PitchScore] = Field(description="One entry per pitch, in order.")
    punch_up: list[SlotWords] = Field(
        default_factory=list, description="Memes only: sharper final words for your top pitch, every slot. Empty otherwise."
    )
    punch_for: int = Field(-1, description="The pitch the punch-up is for; -1 if none.")


class SheetScore(BaseModel):
    candidate: int = Field(description="Index of the candidate picture, from 0.")
    reads_as: str = Field(description="One sentence: what this picture says to a stranger scrolling past.")
    score: int = Field(description="1-10 overall: makes the point at a glance, polished, would be shared. Most are 4-7.")
    fidelity: int = Field(0, description="1-10 how faithfully it reads as the reference/original format; 0 when there is none.")
    fix: str = Field("", description="One concrete change that would most lift it (a word, a position, a color, a cut). '' if none.")


class SheetVerdict(BaseModel):
    scores: list[SheetScore] = Field(description="One entry per candidate, in order.")
    why: str = Field(description="One sentence on why the best one wins, naming it by its idea.")


@dataclass
class Ranking:
    totals: list[float]
    notes: list[str]
    vetoed: set[int] = field(default_factory=set)
    punch_up: list[SlotWords] = field(default_factory=list)
    punch_for: int = -1

    def order(self) -> list[int]:
        return sorted(range(len(self.totals)), key=lambda i: (i not in self.vetoed, self.totals[i]), reverse=True)

    def best(self) -> int | None:
        order = self.order()
        return order[0] if order else None

    def entry(self, i: int) -> dict[str, object]:
        """What one pitch stores about its judging (shown on the ideas board)."""
        return {"total": round(self.totals[i], 2), "vetoed": i in self.vetoed, "note": self.notes[i]}


@dataclass
class Sheet:
    scores: list[float]
    reads_as: list[str]
    fixes: list[str]
    fidelity: list[int]
    why: str = ""

    def order(self) -> list[int]:
        return sorted(range(len(self.scores)), key=lambda i: self.scores[i], reverse=True)


def _model(spec: str) -> tuple[str | None, str]:
    model, _, effort = spec.partition(":")
    return (MODELS.get(model, model) if model else None), (effort or "medium")


SYSTEM = [SystemBlock(raw("image_judge_system"), cache=True)]


async def _review(
    llm: LLM,
    settings: Settings,
    *,
    task: str,
    prompt: str,
    schema: type[T],
    usage: UsageSink | None,
    images: list[bytes] | None = None,
) -> tuple[T | None, list[T]]:
    model, effort = _model(settings.image_judge)

    async def ask(model_id: str | None, reasoning: str) -> T | None:
        try:
            return await llm.structured(
                task=task,
                system=SYSTEM,
                prompt=prompt,
                schema=schema,
                effort=reasoning,
                max_tokens=8000,
                usage=usage,
                images=images,
                model=model_id,
            )
        except LLMImagesUnsupportedError:
            return None
        except LLMError as exc:
            log.info("%s failed on %s: %s", task, model_id or "Claude", exc)
            return None

    # When image routing already sends the lead judgment to an optional model, it does not vote twice.
    lead = await lead_provider(llm, task, images)
    guests = [
        MODEL_IDS[provider]
        for provider in dict.fromkeys(settings.secondary.judges)
        if (not images or provider == "codex") and MODEL_IDS[provider] != model and provider != lead
    ]
    if not guests:
        return await ask(model, effort), []
    primary, *extra = await asyncio.gather(ask(model, effort), *(ask(model_id, "medium") for model_id in guests))
    return primary, [verdict for verdict in extra if verdict is not None]


def to_refine(scores: Sequence[float], ranked: Sequence[int], settings: Settings) -> list[int]:
    """The judge's best candidates worth another build with its fix: the top ``image_refine``, and only those
    scoring below ``image_refine_below`` (a picture that already works is shown as built)."""
    return [k for k in ranked[: max(0, settings.image_refine)] if scores[k] < settings.image_refine_below]


def _blend(primary: float | None, guests: list[float], default: float) -> float:
    if not guests:
        return primary if primary is not None else default
    extra = sum(guests) / len(guests)
    return (2 * primary + extra) / 3 if primary is not None else extra


def _pitch_total(score: PitchScore) -> float:
    fit, clarity, surprise = [max(1, min(10, value)) for value in (score.story_fit, score.clarity, score.surprise)]
    return fit * 0.4 + clarity * 0.35 + surprise * 0.25


async def rank_pitches(
    llm: LLM,
    settings: Settings,
    *,
    context: str,
    candidates: Sequence[str],
    punch_up: bool = False,
    usage: UsageSink | None = None,
) -> Ranking | None:
    """Score pitches, preserving Claude's veto and copy decisions."""
    if not candidates:
        return None
    verdict, guests = await _review(
        llm,
        settings,
        task="image pitch judge",
        prompt=render(
            "image_judge_pitches",
            context=context,
            candidates="\n".join(f"{i}. {c}" for i, c in enumerate(candidates)),
            count=len(candidates),
            punch_up=(
                "\nThese are memes: for your top pitch, also write sharper final words for every slot as `punch_up` "
                "(same slots, within each limit) and set `punch_for` to its index.\n"
                if punch_up
                else ""
            ),
        ),
        schema=PitchRanking,
        usage=usage,
    )
    by = {s.candidate: s for s in verdict.scores if 0 <= s.candidate < len(candidates)} if verdict else {}
    extra = [{s.candidate: s for s in guest.scores if 0 <= s.candidate < len(candidates)} for guest in guests]
    extra = [row for row in extra if len(row) == len(candidates)]
    if not by and not extra:
        return None
    totals, notes, vetoed = [], [], set()
    for i in range(len(candidates)):
        s = by.get(i)
        totals.append(_blend(_pitch_total(s) if s else None, [_pitch_total(row[i]) for row in extra], 5.0))
        notes.append(s.note.strip() if s else next((row[i].note.strip() for row in extra if row[i].note.strip()), ""))
        if s and s.veto:
            vetoed.add(i)
    return Ranking(
        totals, notes, vetoed, verdict.punch_up if verdict and punch_up else [], verdict.punch_for if verdict and punch_up else -1
    )


async def judge_sheet(
    llm: LLM,
    settings: Settings,
    *,
    context: str,
    candidates: Sequence[str],
    pngs: Sequence[bytes],
    references: Sequence[bytes] = (),
    reference_note: str = "",
    usage: UsageSink | None = None,
) -> Sheet | None:
    """Look at every drawn candidate at once; None when pictures cannot be sent or the judge did not answer."""
    if len(pngs) < 2 or len(pngs) != len(candidates):
        return None
    refs = list(references)
    shown = (
        f"The first {len(refs)} attached image(s) are REFERENCES ({reference_note or 'the quality bar'}); they are not candidates. "
        f"The next {len(pngs)} images are the candidates in order (candidate 0 first)."
        if refs
        else f"The {len(pngs)} attached images are the candidates in order (candidate 0 first)."
    )
    verdict, guests = await _review(
        llm,
        settings,
        task="image sheet judge",
        prompt=render(
            "image_judge_sheet",
            context=context,
            candidates="\n".join(f"{i}. {c}" for i, c in enumerate(candidates)),
            shown=shown,
            fidelity=(
                "Score `fidelity`: does each candidate read instantly as the referenced original (layout, poses, who looks "
                "where, signature colors, where the words sit)? A meme that does not read as its original fails.\n"
                if refs and reference_note.startswith("the original")
                else "Leave `fidelity` at 0 unless a reference is the original format.\n"
            ),
            count=len(pngs),
        ),
        schema=SheetVerdict,
        usage=usage,
        images=[*refs, *pngs],
    )
    by = {s.candidate: s for s in verdict.scores if 0 <= s.candidate < len(pngs)} if verdict else {}
    extra = [{s.candidate: s for s in guest.scores if 0 <= s.candidate < len(pngs)} for guest in guests]
    complete = [(guest, row) for guest, row in zip(guests, extra, strict=True) if len(row) == len(pngs)]
    if not by and not complete:
        return None
    lead = verdict if by else complete[0][0]

    def score(item: SheetScore) -> float:
        base = float(max(1, min(10, item.score)))
        fid = max(0, min(10, item.fidelity))
        return base * 0.6 + fid * 0.4 if fid else base

    scores, reads, fixes, fidelity = [], [], [], []
    for i in range(len(pngs)):
        s = by.get(i)
        scores.append(_blend(score(s) if s else None, [score(row[i]) for _, row in complete], 4.0))
        display = s or (complete[0][1][i] if complete else None)
        reads.append(display.reads_as.strip() if display else "")
        fixes.append(s.fix.strip() if s else "")
        fidelity.append(max(0, min(10, display.fidelity)) if display else 0)
    return Sheet(scores, reads, fixes, fidelity, lead.why.strip() if lead else "")

"""The meme room: pitch jokes, draw the best in code, let the judge compare them, and keep the best three.

1. **Pitch** (``MemeIdeas``): six or more concepts with final words, each quoting the passage it riffs on, shaped by
   seeded angle cards (``images/story.py``) so two runs differ.
2. **Rank** (``judge.rank_pitches``): one call scores the pitches as text and may punch up the winner's words.
3. **Draw**: every format is drawn by code from the pitch (no drawing call), so the best ``image_candidates`` are all
   drawn.
4. **Judge** (``judge.judge_sheet``): one vision call sees every drawing next to the original meme from the author's
   reference library, says what each reads as, scores it and names one fix.
5. **Refine and offer**: the best ``image_finalists`` get their fix (restaged, one call each, at once) and are kept as
   finalists; the author swaps between them with no model call.

With ChatGPT signed in, GPT may paint the meme whole instead (``meme_share`` of the slots; famous, comic and caption
formats only, while chart and artifact memes stay code-drawn): the pitch's words are quoted in the prompt, the judge
checks the spelling, and a painting that fails is drawn by code. A painted meme keeps the same state plus ``painted``.

Concepts are kept on the image, so the ideas board moves between pitches without another pitching call, Redraw draws
the same joke again (applying the redraw critique by restaging), and the author can retype the words with no model call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images import board, raster
from inferno_ghostwriter.images.base import PLACEHOLDER_RE, Drawn, ImageProviderError, draw_with_retry, guest_pitches, thumbnail_png
from inferno_ghostwriter.images.judge import Ranking, judge_sheet, rank_pitches, to_refine
from inferno_ghostwriter.images.memes.compose import compose, scheme_for
from inferno_ghostwriter.images.memes.formats import FALLBACK, FAMILIES, MemeFormat, build_spec, get_format, menu
from inferno_ghostwriter.images.memes.settings import configure as configure_settings
from inferno_ghostwriter.images.memes.specs import (
    CastPick,
    MemeBuild,
    MemeConcept,
    MemeDatum,
    MemeIdeas,
    MemeStagingEdit,
    MemeText,
    PanelPick,
)
from inferno_ghostwriter.images.palettes import Scheme, from_id
from inferno_ghostwriter.images.palettes import pick as pick_colors
from inferno_ghostwriter.images.references import ReferenceLibrary, load_png
from inferno_ghostwriter.images.remix import ImprovementPlan, Tweak, variation_for
from inferno_ghostwriter.images.story import anchored, condense, deal
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.llm.base import UsageSink
from inferno_ghostwriter.prompts import raw, render

log = logging.getLogger(__name__)

STATE_VERSION = 2
POST_LIMIT = 10000
POST_TAIL = 3000
MIN_PITCHES = 6
MADE_UP = "(data: entirely made up)"
PAINT_OFF = "GPT image generation is unavailable. Sign in to Codex in Settings, or Redraw to let code draw it."
OLD_MEME = "This meme was made by an older version; click New idea to make one that can be edited."

HUMOR_GUIDE = {
    range(0, 3): "Dry and gentle: a wry chart joke, Venn or artifact; one quiet twist, nothing absurd.",
    range(3, 6): "Clever and relatable: one clean twist on something every practitioner has lived through.",
    range(6, 9): "Playful: famous formats, comics and puns are all welcome.",
    range(9, 11): "Go big: absurd escalation, shameless puns, callbacks to the post's running gags.",
}

Built = tuple[MemeBuild, bytes, int, int]


@dataclass
class MemeContext:
    """What the meme room knows about the post."""

    title: str
    markdown: str
    voice_profile: str
    brief: str
    joke: str = ""
    callbacks: str = ""
    humor: int = 5
    # Formats this author's last memes used, newest first: the room avoids repeating them.
    recent_formats: tuple[str, ...] = ()
    # The post's formula as the room should read it (``writer.formulas.meme_note``); "" when none is in force.
    formula: str = ""
    # "closing" (the last image) or "opening" (the first image and thumbnail, see ``images.opening``).
    position: str = "closing"
    # For a closing meme when the post also opens with one (a meme sandwich): the opener's format and premise.
    opening: str = ""
    # Color schemes ("ramp:surface") this author's latest images used, newest first: a new one rotates away from them.
    recent_schemes: tuple[str, ...] = ()
    # The author's steer for this run ("more like the original", "about the deployment bit").
    note: str = ""
    # Seeds the angle cards; a new one each run keeps pitches fresh.
    seed: int | None = None


def position_guide(post: MemeContext) -> str:
    """What the room is pitching: the closer, the closer of a meme sandwich, or the opener."""
    if post.position == "opening":
        return (
            "Pitch the opening meme for this post: the first thing a reader sees, and the post's thumbnail. It sets up the "
            "tension, pain or question the post resolves, so it must land for someone who has not read the post yet: no "
            "spoilers and no callbacks to things the post explains later. Favor formats that still read as a wide thumbnail. "
            "The post closes with its own meme, so save the big payoff for the ending."
        )
    if post.opening:
        return (
            "Pitch the closing meme for this post. The post also opens with a meme, so this is a meme sandwich. The opener: "
            f"{post.opening}. Use a different format family from the opener and never repeat its joke; the best closer pays "
            "it off (a bookend) now that the reader has the whole story."
        )
    return "Pitch the closing meme for this post."


@dataclass
class ArtDirection:
    """How the drawings should look."""

    visual_style: str
    brand: str = ""
    image_guidance: str = ""
    palette: tuple[str, ...] = ()
    # A redraw's critique and twists (see images/remix.py), and the cast it asks for ("" = the house cast).
    improvement: ImprovementPlan | None = None
    tweaks: tuple[Tweak, ...] = ()
    cast: str = ""
    # The author's edit instructions for the image being redrawn: when set, a redraw builds on the edited picture.
    edits: tuple[str, ...] = ()
    # The author's steer for this redraw, in their words.
    note: str = ""
    # A style reference the author attached ("make it like this"), as PNG bytes.
    reference: bytes | None = None


# The meme room returns the shared result type.
MemeResult = Drawn


def humor_guide(level: int) -> str:
    return next(text for span, text in HUMOR_GUIDE.items() if max(0, min(10, level)) in span)


def voice_section(voice_profile: str, heading: str) -> str:
    """The body of the voice profile's ``## <heading>...`` section ('' when there is none)."""
    match = re.search(rf"^##\s+{heading}.*?$(.*?)(?=^##\s|\Z)", voice_profile, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def plan_callbacks(plan: dict[str, Any] | None) -> str:
    """The plan's running jokes and key concepts: the best raw material for a closing callback."""
    lines = []
    for item in (plan or {}).get("callbacks") or []:
        if isinstance(item, dict) and item.get("idea"):
            kind = "Running joke" if item.get("kind") == "running_joke" else "Key concept"
            payoff = f" (payoff: {item['payoff']})" if item.get("payoff") else ""
            lines.append(f"- {kind}: {item['idea']}{payoff}")
    return "\n".join(lines)


def clip_post(markdown: str, limit: int = POST_LIMIT, tail: int = POST_TAIL) -> str:
    """The post without image placeholders, at most about ``limit`` characters.

    A long post is condensed by code (:func:`~inferno_ghostwriter.images.story.condense`: every section, each
    paragraph's opening sentences) rather than cut, so the whole story arrives in fewer tokens. ``tail`` keeps
    up to that many characters of the ending word for word, where the callbacks pay off.
    """
    text = PLACEHOLDER_RE.sub("", markdown).strip()
    if len(text) <= limit:
        return text
    if tail <= 0:
        return condense(text, limit)
    cut = text.find("\n\n", len(text) - tail)
    head, end = (text[:cut], text[cut:].strip()) if cut > 0 else (text[:-tail], text[-tail:])
    return f"{condense(head, max(limit - len(end), limit // 2))}\n\n[... the ending, word for word ...]\n\n{end}"


def load_state(spec: str) -> dict[str, Any] | None:
    """The meme's stored concepts and build, or None for older memes (plain SVG + captions)."""
    try:
        state = json.loads(spec) if spec else None
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) and state.get("version") == STATE_VERSION else None


def load_concepts(state: dict[str, Any]) -> list[MemeConcept]:
    """The stored pitches (older ones lack chart data, a caption or an anchor and get empty ones)."""
    return [MemeConcept.model_validate({"data": [], "caption": "", **c}) for c in state.get("concepts", [])]


def total(concept: MemeConcept) -> tuple[int, int]:
    s = concept.scores
    return (s.relevance + s.recognizability + s.surprise + s.clarity + s.voice_fit + s.standalone, s.relevance + s.clarity)


def panel_scores(state: dict[str, Any], count: int) -> list[float] | None:
    """The judge's score per stored concept (a joke it ruled out scores far below the rest), or None."""
    scores = (state.get("panel") or {}).get("scores")
    return [float(x) for x in scores] if isinstance(scores, list) and len(scores) == count else None


def pick(concepts: list[MemeConcept], preferred: int | None, skip: set[int], panel: list[float] | None = None) -> int | None:
    """The preferred concept if usable, else the best-scoring untried concept with a known format.

    The judge's scores rank the concepts when there are any; the writers' own scores break ties and stand in without."""
    usable = [i for i, c in enumerate(concepts) if i not in skip and get_format(c.format)]
    if preferred in usable:
        return preferred
    return max(usable, key=lambda i: ((panel[i] if panel else 0), total(concepts[i])), default=None)


def ranking(state: dict[str, Any], skip: set[int] | None = None) -> list[int]:
    concepts = load_concepts(state)
    panel = panel_scores(state, len(concepts))
    usable = [i for i, c in enumerate(concepts) if i not in (skip or set()) and get_format(c.format)]
    return sorted(usable, key=lambda i: ((panel[i] if panel else 0), total(concepts[i])), reverse=True)


def punched_up(fmt: MemeFormat, concept: MemeConcept, punch: list[MemeText]) -> list[MemeText] | None:
    """The judge's sharper words, when they cover every required slot and fit every limit; else None."""
    words = {t.slot: t.text.strip() for t in punch}
    old = {t.slot: t for t in concept.texts}
    texts = []
    for slot in fmt.slots:
        text = words.get(slot.name, "")
        if not text and not slot.optional:
            return None
        if len(text) > slot.max_chars:
            return None
        if text:
            texts.append(MemeText(slot=slot.name, text=text, speaker=old[slot.name].speaker if slot.name in old else ""))
    return texts


def validate(fmt: MemeFormat, build: MemeBuild) -> tuple[list[str], list[str]]:
    """(blocking problems, style problems). Overlong text still renders (it is shrunk to fit) but reads worse."""
    texts = {t.slot: t.text.strip() for t in build.texts}
    art = {a.region: a.svg.strip() for a in build.art}
    blocking, style = [], []
    for slot in fmt.slots:
        text = texts.get(slot.name, "")
        if not text and not slot.optional:
            blocking.append(f"Text slot `{slot.name}` is empty.")
        elif len(text) > slot.max_chars * 1.25:
            style.append(f"Text slot `{slot.name}` has {len(text)} characters; the limit is {slot.max_chars}.")
    blocking += [f"Art region `{r.name}` has no drawing." for r in fmt.regions if not art.get(r.name)]
    if fmt.id in ("joke_pie_3d", "joke_pie", "joke_bar") and sum(1 for d in build.data if d.value > 0) < 2:
        blocking.append("The chart needs 2-6 entries with positive values in `data`.")
    if fmt.id == "spurious_correlation" and len({d.series for d in build.data}) < 2:
        blocking.append("The correlation chart needs two series ('a' and 'b') in `data`.")
    return blocking, style


def cast_dict(cast: list[CastPick]) -> dict[str, dict[str, str]]:
    return {c.role: {"kind": c.kind, "expression": c.expression, "accessory": c.accessory} for c in cast if c.role}


def scheme_of(state: dict[str, Any] | None, palette: tuple[str, ...]) -> Scheme:
    """The colors a meme is drawn in: a brand palette first, then the stored scheme, then the house default."""
    return scheme_for(palette, from_id(str((state or {}).get("scheme") or "")))


def pick_scheme(post: MemeContext, palette: tuple[str, ...], avoid: str = "") -> Scheme:
    """A new meme's colors: the brand palette, else a ramp and surface the author's latest images did not use."""
    return pick_colors(palette, post.recent_schemes, avoid=[avoid] if avoid else ())


def render_build(fmt: MemeFormat, build: MemeBuild, palette: tuple[str, ...] = (), sch: Scheme | None = None) -> tuple[bytes, int, int]:
    return compose(
        fmt,
        {t.slot: t for t in build.texts},
        {a.region: a.svg for a in build.art},
        build.cast_defs,
        build.data,
        palette=palette,
        sch=sch,
        cast=cast_dict(build.cast),
        panels=[p.model_dump() for p in build.panels],
    )


def alt_text(
    fmt: MemeFormat,
    texts: list[MemeText],
    data: list[MemeDatum],
    cast: list[CastPick] | None = None,
    panels: list[PanelPick] | None = None,
) -> str:
    """Alt text written from the meme's own parts, so it is always right: the format, who is in it and every word."""
    words = " / ".join(t.text.strip() for t in texts if t.text.strip())
    chart = "; ".join(f"{d.label}: {d.value:g}" for d in data)
    who = ""
    if panels:
        who = " " + " ".join(
            f"Panel {i + 1}: " + ", ".join(f"a {c.expression.replace('_', ' ')} {c.kind}" for c in p.characters) + "."
            for i, p in enumerate(panels)
        )
    elif fmt.staged and fmt.family != "comic":
        who = f" {fmt.recognizable}"
    return f"{fmt.name} meme.{who} Text: {words}." + (f" Data: {chart}." if chart else "")


def concept_build(fmt: MemeFormat, concept: MemeConcept) -> MemeBuild:
    """Every format is drawn by code: the pitch already has its words, data and caption."""
    return MemeBuild(
        texts=concept.texts,
        cast_defs="",
        art=[],
        data=concept.data,
        alt=alt_text(fmt, concept.texts, concept.data, concept.cast, concept.panels),
        caption=concept.caption,
        cast=concept.cast,
        panels=concept.panels,
    )


def fallback_build(concept: MemeConcept | None) -> MemeBuild:
    """The classic caption meme: used when no pitch can be drawn."""
    words = [t.text.strip() for t in (concept.texts if concept else []) if t.text.strip()]
    top, bottom = (words[0], words[-1]) if len(words) > 1 else ("", words[0] if words else "This is fine")
    return MemeBuild(
        texts=[MemeText(slot="top", text=top[:80], speaker=""), MemeText(slot="bottom", text=bottom[:90], speaker="")],
        cast_defs="",
        art=[],
        data=[],
        alt="A caption meme: " + " / ".join(w for w in (top, bottom) if w),
        caption=(concept.caption or concept.premise) if concept else "",
    )


# Meme families GPT may paint whole; chart and artifact memes need exact numbers and long text, so code draws them.
PAINTED_FAMILIES = ("classic", "comic", "caption")
# At most this many painted candidates per meme (each is one GPT image generation).
MAX_PAINTED = 3
GPT_LABEL = " (generated by GPT: check every word is spelled exactly as quoted)"


def paintable(fmt: MemeFormat, concept: MemeConcept) -> bool:
    """Whether GPT may paint this pitch whole (a famous, comic or caption format with no chart data)."""
    return fmt.family in PAINTED_FAMILIES and not concept.data and any(t.text.strip() for t in concept.texts)


def paint_prompt(fmt: MemeFormat, build: MemeBuild, title: str, sch: Scheme | None, palette: tuple[str, ...]) -> str:
    """The painting prompt for a whole meme: the format, its cast and every word, quoted exactly."""
    texts = {t.slot: t.text.strip() for t in build.texts}
    words = "\n".join(f'- {slot.name} ({slot.hint}): "{texts[slot.name]}"' for slot in fmt.slots if texts.get(slot.name))
    cast = "; ".join(f"{c.role} is a {c.kind}" for c in build.cast)
    subject = (
        f"A '{fmt.name}' meme"
        + (f" for a technical blog post titled '{title}'" if title else "")
        + f". The format: {fmt.recognizable}\n"
        + (f"Cast: {cast}.\n" if cast else "")
        + f"The words, each in its place in the format:\n{words}"
    )
    width, height = fmt.size
    return raster.prompt_for(subject, scheme=sch, palette=palette, shape=raster.aspect(width, height), rules=raster.MEME_RULES)


@dataclass
class _Candidate:
    index: int
    concept: MemeConcept
    fmt: MemeFormat
    built: Built
    reads_as: str = ""
    score: float | None = None
    fix: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    # The painting prompt when GPT painted this candidate ("" when code drew it).
    prompt: str = ""


class MemeMaker:
    def __init__(self, llm: LLM, settings: Settings) -> None:
        self.llm = llm
        self.settings = settings
        self.system = [SystemBlock(raw("meme_system"), cache=True)]
        self.references = ReferenceLibrary(settings.image_reference_dir)
        configure_settings(settings.image_reference_dir)

    async def make(
        self,
        spec: str,
        post: MemeContext,
        art: ArtDirection,
        *,
        redraw: bool = False,
        rethink: bool = False,
        meme_format: str | None = None,
        concept_index: int | None = None,
        finalists: bool = True,
        pitch: bool = False,
        usage: UsageSink | None = None,
    ) -> MemeResult:
        """Make the meme.

        A fresh meme, a rethink that ran out of pitches, or another ``meme_format`` pitches again and runs the whole
        room (draw, judge, refine, finalists); ``finalists=False`` draws only the best pitch (used for an opening meme,
        which the opening room judges). ``concept_index`` draws that stored pitch; a redraw draws the same joke again;
        ``pitch`` pitches a new round. New rounds are added to the board (``images/board.py``), never swapped in."""
        state = load_state(spec)
        index: int | None = None
        run = False
        if concept_index is not None:
            if state is None or not 0 <= concept_index < len(state.get("concepts", [])):
                raise ImageProviderError("That idea is no longer available. Click New idea for fresh pitches.")
            index = concept_index
        elif state is not None and state.get("brief") == post.brief and not meme_format and not pitch and (redraw or rethink):
            order = ranking(state, set(state.get("tried", []))) if rethink else ranking(state)
            if not rethink and isinstance(state.get("chosen"), int) and state["chosen"] in ranking(state):
                order = [state["chosen"]]
            index = order[0] if order else None
            if index is None:
                # Every pitch has been used: ask the room for a new round that avoids them.
                state = await self._ideate_more(state, post, None, usage)
                run = True
        elif state is not None and state.get("brief") == post.brief:
            state = await self._ideate_more(state, post, meme_format, usage)
            run = True
        else:
            state = await self._ideate(post, meme_format, [], usage)
            run = True
        assert state is not None
        new = list(state.pop("_new", None) or [])

        state.pop("fallback_from", None)
        state.pop("review", None)
        previous_scheme = str(state.get("scheme") or "")
        sch = pick_scheme(post, art.palette, avoid=previous_scheme if (redraw or rethink) else "")
        state["scheme"] = sch.id
        if run and finalists:
            return await self._run(state, post, art, sch, usage, among=new)

        concepts = load_concepts(state)
        if index is None:
            order = ranking(state)
            order = [i for i in order if i in set(new)] or order
            index = order[0] if order else None
        concept = concepts[index] if index is not None else None
        tried = {*state.get("tried", []), *([index] if index is not None else [])}
        fmt = (get_format(concept.format) if concept else None) or FALLBACK
        built: Built | None = None
        painted = ""
        if concept is not None:
            # A redraw of an edited meme keeps the edits: its current words and casting are the starting point.
            current = state.get("build") if art.edits and redraw and concept_index is None and not rethink else None
            same = redraw and concept_index is None and not rethink
            painting: tuple[Built, str] | None = None
            if same and isinstance(state.get("painted"), dict):
                # A painted meme is painted again, with the redraw's twist; code draws it only if painting is off.
                build = MemeBuild.model_validate(current) if current else concept_build(fmt, concept)
                twist = self._remix_instruction(art) if (art.improvement or art.tweaks or art.note or art.cast) else ""
                prompt = str(state["painted"].get("prompt") or "")
                painting = await self._paint(fmt, build, post.title, sch, art, prompt=prompt, note=twist, usage=usage)
            elif not same and paintable(fmt, concept) and await raster.use_native(self.llm, self.settings, self._paint_seed(post), "meme"):
                painting = await self._paint(fmt, concept_build(fmt, concept), post.title, sch, art, usage=usage)
            if painting is not None:
                built, painted = painting
            built = built or (self._from_current(fmt, current, art, sch) if current else None)
            built = built or self._direct(fmt, concept, art, strict=False, sch=sch)
            if built is not None and not painted and redraw and (art.improvement or art.tweaks or art.note or art.cast):
                # Remix: the redraw's critique and twist reach the meme by restaging its words and cast.
                again = await self._restage(state, fmt, built[0], self._remix_instruction(art), art, usage, sch=sch)
                built = again or built
        if built is None and concept is not None:
            # The format could not be drawn: another pitch keeps a whole joke; a caption meme is the last resort.
            state["fallback_from"] = fmt.id
            for other in ranking(state, {index} if index is not None else set()):
                other_fmt = get_format(concepts[other].format)
                direct = self._direct(other_fmt, concepts[other], art, strict=False, sch=sch) if other_fmt else None
                if direct is not None and other_fmt is not None:
                    index, concept, fmt, built = other, concepts[other], other_fmt, direct
                    tried.add(other)
                    break
        state["chosen"] = index
        state["tried"] = sorted(tried)
        return self._finish(state, fmt, concept, built, art, painted=painted)

    @staticmethod
    def _paint_seed(post: MemeContext) -> str:
        return f"meme:{post.position}:{post.title}"

    async def _paint(
        self,
        fmt: MemeFormat,
        build: MemeBuild,
        title: str,
        sch: Scheme | None,
        art: ArtDirection,
        *,
        prompt: str = "",
        note: str = "",
        current: bytes | None = None,
        usage: UsageSink | None,
    ) -> tuple[Built, str] | None:
        """GPT paints the whole meme from ``build`` (or from a stored ``prompt``); returns what was painted and the
        prompt to store, or None when painting is off or fails. ``note`` with ``current`` changes that picture."""
        base = prompt or paint_prompt(fmt, build, title, sch, art.palette)
        text, shown = base, [art.reference] if art.reference is not None else None
        if note.strip() and current is not None:
            text = f"{base}\nChange the attached picture as follows and keep everything else exactly as it is: {note.strip()}"
            shown = [current]
        elif note.strip():
            text = f"{base}\n{note.strip()}"
        width, height = fmt.size
        png = await raster.paint(self.llm, text, size=(width, height), images=shown, usage=usage)
        if png is None:
            return None
        return (build, png, width, height), base

    async def _run(
        self,
        state: dict[str, Any],
        post: MemeContext,
        art: ArtDirection,
        sch: Scheme,
        usage: UsageSink | None,
        *,
        among: list[int] | None = None,
    ) -> MemeResult:
        """Draw the best pitches, let the judge compare them with the originals, refine the best and keep them.

        ``among`` limits the candidates to those pitches (a new round added to the board)."""
        concepts = load_concepts(state)
        drawn: list[_Candidate] = []
        order = ranking(state)
        if among:
            order = [i for i in order if i in set(among)] or order
        fits = [i for i in order if (f := get_format(concepts[i].format)) is not None and paintable(f, concepts[i])]
        if fits and await raster.use_native(self.llm, self.settings, self._paint_seed(post), "meme"):
            # GPT paints the best paintable pitches whole instead of code drawing them: every candidate is painted.
            chosen = fits[: max(1, min(self.settings.image_candidates, MAX_PAINTED))]
            fmts = [get_format(concepts[i].format) or FALLBACK for i in chosen]
            made = await asyncio.gather(
                *(
                    self._paint(f, concept_build(f, concepts[i]), post.title, sch, art, usage=usage)
                    for i, f in zip(chosen, fmts, strict=True)
                )
            )
            for i, f, one in zip(chosen, fmts, made, strict=True):
                if one is not None:
                    drawn.append(_Candidate(i, concepts[i], f, one[0], prompt=one[1]))
        for i in () if drawn else order:  # a drawn meme, or every painting failed: code draws the pitches
            if len(drawn) >= max(1, self.settings.image_candidates):
                break
            fmt = get_format(concepts[i].format)
            built = self._direct(fmt, concepts[i], art, strict=False, sch=sch) if fmt else None
            if built is not None and fmt is not None:
                drawn.append(_Candidate(i, concepts[i], fmt, built))
        if not drawn:
            state["chosen"] = None
            state["fallback_from"] = "all"
            return self._finish(state, FALLBACK, concepts[0] if concepts else None, None, art)

        keep = max(1, self.settings.image_finalists)
        refs, ref_note = self._meme_references([c.fmt.id for c in drawn])
        if art.reference is not None:
            refs, ref_note = [*refs, art.reference], (ref_note + "; " if ref_note else "") + "the last one is the author's style reference"
        sheet = await judge_sheet(
            self.llm,
            self.settings,
            context=self._context(post),
            candidates=[f"[{c.fmt.name}] {c.concept.premise}" + (GPT_LABEL if c.prompt else "") for c in drawn],
            pngs=[thumbnail_png(c.built[1]) for c in drawn],
            references=refs,
            reference_note=ref_note,
            usage=usage,
        )
        if sheet is not None:
            for k, cand in enumerate(drawn):
                cand.score, cand.reads_as, cand.fix = round(sheet.scores[k], 2), sheet.reads_as[k], sheet.fixes[k]
            best = [drawn[k] for k in sheet.order()[:keep]]
            state["review"] = {"why": sheet.why, "candidates": [c.index for c in drawn]}

            async def refine(cand: _Candidate) -> None:
                if cand.fix and cand.prompt:
                    again = await self._paint(
                        cand.fmt, cand.built[0], post.title, sch, art, prompt=cand.prompt, note=cand.fix, current=cand.built[1], usage=usage
                    )
                    if again is not None:
                        cand.built = again[0]
                        cand.extra["refined"] = cand.fix
                    return
                if cand.fix and cand.fmt.staged:
                    fixed = await self._restage(state, cand.fmt, cand.built[0], cand.fix, art, usage, sch=sch)
                    if fixed is not None:
                        cand.built = fixed
                        cand.extra["refined"] = cand.fix

            order = sheet.order()[:keep]
            await asyncio.gather(*(refine(drawn[k]) for k in to_refine(sheet.scores, order, self.settings)))
        else:
            best = drawn[:keep]
            state["review"] = {"skipped": True, "note": "Ranked from the pitches (this connection cannot show Claude pictures)."}
        for cand in drawn:
            if cand.reads_as:
                state["concepts"][cand.index]["reads_as"] = cand.reads_as
        state["tried"] = sorted({*state.get("tried", []), *(c.index for c in best)})
        results = []
        for cand in best:
            snapshot = json.loads(json.dumps(state))
            snapshot["chosen"] = cand.index
            result = self._finish(snapshot, cand.fmt, cand.concept, cand.built, art, painted=cand.prompt)
            label = f"{cand.fmt.name}: {cand.concept.premise}" + (" (generated by GPT)" if cand.prompt else "")
            result.label, result.score, result.reads_as = label, cand.score, cand.reads_as
            result.fix = "" if cand.extra.get("refined") else cand.fix
            results.append(result)
        main = results[0]
        main.finalists = results if len(results) > 1 else []
        return main

    def _meme_references(self, format_ids: list[str]) -> tuple[list[bytes], str]:
        paths: list[Path] = []
        names: list[str] = []
        for fid in dict.fromkeys(format_ids):
            path = self.references.for_meme(fid)
            fmt = get_format(fid)
            if path is not None and fmt is not None and len(paths) < 4:
                paths.append(path)
                names.append(fmt.name)
        cast = self.references.cast_sheet()
        if not paths and not cast:
            return [], ""
        note = "the original memes, in order: " + "; ".join(names) if paths else ""
        if cast:
            note = (note + "; then " if note else "") + "the house character style sheet (the cast's look to aim for)"
        return load_png([*paths, *cast], 768), note

    @staticmethod
    def _remix_instruction(art: ArtDirection) -> str:
        lines = [variation_for(art) or "This is a redraw: make it land harder."]
        if art.cast:
            lines.append(f"Recast it: {art.cast}")
        if art.note:
            lines.append(f"The author asked: {art.note}")
        lines.append("Keep the joke and the format; tighten the words and recast only where it helps.")
        return "\n".join(lines)

    async def edit(
        self, spec: str, instruction: str, art: ArtDirection, *, usage: UsageSink | None = None, current_png: bytes | None = None
    ) -> MemeResult:
        """Change the current meme as the author asks ("make the cat look more smug"), keeping the rest. GPT changes a
        painted meme (shown ``current_png``)."""
        state = load_state(spec)
        if state is None or not state.get("build"):
            raise ImageProviderError(OLD_MEME)
        fmt = get_format(str(state.get("format", ""))) or FALLBACK
        current = MemeBuild.model_validate(state["build"])
        sch = scheme_of(state, art.palette)
        if isinstance(state.get("painted"), dict):
            prompt = str(state["painted"].get("prompt") or "")
            again = await self._paint(fmt, current, "", sch, art, prompt=prompt, note=instruction, current=current_png, usage=usage)
            if again is None:
                raise ImageProviderError(PAINT_OFF)
            return self._finish(state, fmt, None, again[0], art, painted=again[1])
        if fmt.staged and not current.data:
            built = await self._restage(state, fmt, current, instruction, art, usage, sch=sch)
        else:
            built = await self._revise(fmt, current, instruction, art, usage, sch)
        if built is None:
            raise ImageProviderError("Claude's edit could not be drawn. Try rewording the instruction.")
        return self._finish(state, fmt, None, built, art)

    async def reword(
        self, spec: str, words: dict[str, str], art: ArtDirection, *, current_png: bytes | None = None, usage: UsageSink | None = None
    ) -> MemeResult:
        """Set the meme's words as the author typed them and draw it again: no model call for a code-drawn meme, while
        GPT paints a painted one again with the new words (shown ``current_png``, so the rest stays)."""
        state = load_state(spec)
        if state is None or not state.get("build"):
            raise ImageProviderError(OLD_MEME)
        fmt = get_format(str(state.get("format", ""))) or FALLBACK
        current = MemeBuild.model_validate(state["build"])
        old = {t.slot: t for t in current.texts}
        texts = [
            MemeText(
                slot=s.name,
                text=words.get(s.name, old[s.name].text if s.name in old else "").strip(),
                speaker=old[s.name].speaker if s.name in old else "",
            )
            for s in fmt.slots
        ]
        build = current.model_copy(update={"texts": texts, "alt": alt_text(fmt, texts, current.data, current.cast, current.panels)})
        blocking, _ = validate(fmt, build)
        if blocking:
            raise ImageProviderError(" ".join(blocking))
        sch = scheme_of(state, art.palette)
        if isinstance(state.get("painted"), dict):
            # The words are part of the painting: paint it again with the new words quoted, keeping everything else.
            prompt = paint_prompt(fmt, build, "", sch, art.palette)
            note = "Replace the words with the ones quoted above, each in its place; keep the picture otherwise exactly as it is."
            again = await self._paint(fmt, build, "", sch, art, prompt=prompt, note=note, current=current_png, usage=usage)
            if again is None:
                raise ImageProviderError(PAINT_OFF)
            return self._finish(state, fmt, None, again[0], art, painted=again[1])
        png, width, height = render_build(fmt, build, art.palette, sch)
        return self._finish(state, fmt, None, (build, png, width, height), art)

    def _finish(
        self,
        state: dict[str, Any],
        fmt: MemeFormat,
        concept: MemeConcept | None,
        built: Built | None,
        art: ArtDirection,
        *,
        painted: str = "",
    ) -> MemeResult:
        """The meme result; ``painted`` is the painting prompt when GPT painted ``built`` ("" when code drew it)."""
        if built is None:
            painted = ""
            fmt = FALLBACK
            build = fallback_build(concept)
            png, width, height = render_build(fmt, build, art.palette, scheme_of(state, art.palette))
        else:
            build, png, width, height = built
        caption = build.caption.strip()
        if fmt.family == "chart" and build.data and not re.search(r"made up|illustrative|fake", caption, re.IGNORECASE):
            caption = f"{caption} {MADE_UP}".strip()
        state.update(format=fmt.id, build=build.model_dump())
        # The chosen pitch keeps the final words, so a redraw or the ideas board never brings back an older wording.
        chosen, pitches = state.get("chosen"), state.get("concepts", [])
        if isinstance(chosen, int) and 0 <= chosen < len(pitches) and pitches[chosen].get("format") == fmt.id:
            pitches[chosen]["texts"] = [t.model_dump() for t in build.texts if t.text.strip()]
        if painted:
            state["painted"] = {"prompt": painted}
        else:
            state.pop("painted", None)
        provider = raster.PROVIDER if painted else "vega-lite" if fmt.id == "spurious_correlation" else "claude-meme"
        return Drawn(png, width, height, provider, json.dumps(state), build.alt, caption)

    async def _ideate(self, post: MemeContext, only: str | None, exclude: list[str], usage: UsageSink | None) -> dict[str, Any]:
        avoid = "\n".join(f"- {p}" for p in exclude)
        recent = ", ".join(post.recent_formats)
        opening = post.position == "opening"
        count = max(MIN_PITCHES, self.settings.image_candidates)
        seed = post.seed if post.seed is not None else random.randrange(1 << 30)
        prompt = render(
            "meme_ideas",
            position_guide=position_guide(post),
            title=post.title,
            joke=post.joke or "(none given)",
            callbacks=post.callbacks or "(none planned)",
            brief=post.brief
            or ("A joke that sets up the problem this post solves." if opening else "A funny, relevant joke that lands the ending."),
            humor=post.humor,
            humor_guide=humor_guide(post.humor),
            formula=f"\n{post.formula}\n" if post.formula else "",
            humor_section=voice_section(post.voice_profile, "Humor") or "(not described: use dry, specific, good-natured humor)",
            # The opener is pitched from the post's beginning; the closer keeps its ending, where callbacks pay off.
            post=clip_post(post.markdown, tail=0) if opening else clip_post(post.markdown),
            menu=menu(only),
            kit=_kit_menu(),
            count=count,
            cards="" if only else deal(post.markdown, seed=seed, families=FAMILIES, humor=post.humor),
            note=f"\nThe author's direction for this meme: {post.note}\n" if post.note else "",
            constraint=f"\nOnly use the format `{only}`: all {count} concepts must use it, each with a different joke.\n" if only else "",
            exclude=f"\nThese premises were already used; pitch different jokes:\n{avoid}\n" if exclude else "",
            recent=(
                f"\nThis author's last memes used: {recent}. Readers notice a repeated format, so prefer other formats "
                "unless one of these is clearly the funniest fit.\n"
                if recent and not only
                else ""
            ),
        )
        ideas = await self.llm.structured(
            task="meme ideas",
            system=self.system,
            prompt=prompt,
            schema=MemeIdeas,
            effort=self.settings.effort_meme_ideas,
            max_tokens=20000,
            usage=usage,
        )
        concepts = [c.model_copy(update={"format": only}) for c in ideas.concepts] if only else list(ideas.concepts)
        if not concepts:
            raise ImageProviderError("Claude did not pitch any meme ideas. Click New idea to try again.")
        if self.settings.secondary.ideation:
            used = {c.premise.strip().casefold() for c in concepts}
            pitch = (
                prompt + "\n\nFor this guest round pitch two alternative jokes. Keep the format constraint if present. "
                "Avoid these existing premises:\n" + "\n".join(f"- {c.premise}" for c in concepts)
            )
            for guest in await guest_pitches(
                self.llm, self.settings, task="meme ideas", system=self.system, prompt=pitch, schema=MemeIdeas, usage=usage
            ):
                for concept in guest.concepts[:2]:
                    key = concept.premise.strip().casefold()
                    if key and key not in used and get_format(only or concept.format):
                        used.add(key)
                        concepts.append(concept.model_copy(update={"format": only}) if only else concept)
        state: dict[str, Any] = {"version": STATE_VERSION, "brief": post.brief, "tried": [], "seed": seed}
        ranking_ = await rank_pitches(
            self.llm, self.settings, context=self._context(post), candidates=self._pitch_lines(concepts), punch_up=True, usage=usage
        )
        entries = [c.model_dump() for c in concepts]
        for i, concept in enumerate(concepts):
            entries[i]["anchored"] = anchored(concept.anchor, post.markdown)
        scores = self._scores(concepts, entries, ranking_)
        chosen = max(range(len(concepts)), key=lambda i: (scores[i], total(concepts[i])))
        words = None
        fmt = get_format(concepts[chosen].format)
        if ranking_ is not None and ranking_.punch_for == chosen and fmt is not None and ranking_.punch_up:
            words = punched_up(fmt, concepts[chosen], [MemeText(slot=w.slot, text=w.text, speaker="") for w in ranking_.punch_up])
        if words is not None:
            entries[chosen]["texts"] = [w.model_dump() for w in words]
        state["panel"] = {
            "scores": scores,
            "notes": [ranking_.notes[i] if ranking_ else "" for i in range(len(concepts))],
            "vetoed": sorted(ranking_.vetoed) if ranking_ else [],
            "punched_up": words is not None,
        }
        why = ranking_.notes[chosen] if ranking_ and ranking_.notes[chosen] else ideas.why
        state.update(concepts=entries, chosen=chosen, why=why)
        return state

    async def _ideate_more(self, state: dict[str, Any], post: MemeContext, only: str | None, usage: UsageSink | None) -> dict[str, Any]:
        """Pitch a new round and add it to the board; earlier pitches keep their place, marks and scores."""
        old = list(state.get("concepts", []))
        fresh = await self._ideate(post, only, [str(c.get("premise") or "") for c in old], usage)
        chosen = state.get("chosen")
        keep = {*state.get("tried", []), *([chosen] if isinstance(chosen, int) else [])}
        entries, mapping, new = board.merge(old, fresh["concepts"], keep=keep)
        survivors = sorted(mapping, key=mapping.__getitem__)
        old_panel, new_panel = state.get("panel") or {}, fresh.get("panel") or {}
        old_scores = panel_scores(state, len(old)) or [0.0] * len(old)
        old_notes = [*(str(n) for n in old_panel.get("notes") or []), *[""] * len(old)]
        offset = len(survivors)
        return {
            **state,
            "seed": fresh.get("seed"),
            "why": fresh.get("why", ""),
            "concepts": entries,
            "tried": board.remap(state.get("tried", []), mapping),
            "chosen": board.remap_one(chosen, mapping),
            "panel": {
                "scores": [old_scores[i] for i in survivors] + list(new_panel.get("scores") or [0.0] * len(new)),
                "notes": [old_notes[i] for i in survivors] + [str(n) for n in new_panel.get("notes") or [""] * len(new)],
                "vetoed": board.remap(old_panel.get("vetoed") or [], mapping) + [offset + int(v) for v in new_panel.get("vetoed") or []],
                "punched_up": bool(new_panel.get("punched_up")),
            },
            "_new": new,
        }

    @staticmethod
    def _scores(concepts: list[MemeConcept], entries: list[dict[str, Any]], ranking_: Ranking | None) -> list[float]:
        """One score per pitch: the judge's (writers' own as a stand-in), with vetoed and unanchored pitches last."""
        scores = []
        for i, concept in enumerate(concepts):
            score = ranking_.totals[i] if ranking_ else total(concept)[0] / 3
            if ranking_ and i in ranking_.vetoed:
                score -= 100
            if not entries[i]["anchored"]:
                score -= 50
            if not get_format(concept.format):
                score -= 200
            scores.append(round(score, 2))
        return scores

    def _pitch_lines(self, concepts: list[MemeConcept]) -> list[str]:
        lines = []
        for c in concepts:
            fmt = get_format(c.format)
            words = " | ".join(f"{t.slot}: {t.text}" for t in c.texts if t.text.strip())
            data = "; ".join(f"{d.label}: {d.value:g}" for d in c.data)
            lines.append(
                f"[{fmt.name if fmt else c.format}] {c.premise}\n   Riffs on: {c.anchor or c.callback}\n   Words: {words}"
                + (f"\n   Chart data: {data}" if data else "")
                + (f"\n   Format limits: {', '.join(f'{sl.name} <= {sl.max_chars}' for sl in fmt.slots)}" if fmt else "")
            )
        return lines

    def _context(self, post: MemeContext) -> str:
        opening = post.position == "opening"
        humor = voice_section(post.voice_profile, "Humor") or "(dry, specific, good-natured)"
        return (
            f"{position_guide(post)}\n\nPost title: {post.title}\nHumor level {post.humor}/10: {humor_guide(post.humor)}\n"
            f"The author's sense of humor:\n<humor>\n{humor}\n</humor>\n"
            + (f"The author asked: {post.note}\n" if post.note else "")
            + f"The post:\n<post>\n{clip_post(post.markdown, 6000, 0 if opening else 2000)}\n</post>"
        )

    def _direct(
        self, fmt: MemeFormat, concept: MemeConcept, art: ArtDirection, *, strict: bool = True, sch: Scheme | None = None
    ) -> Built | None:
        """Draw a pitch with code; None when it is not ready to draw. ``strict`` also turns down words that run long."""
        if fmt.regions and not fmt.staged:
            return None
        build = concept_build(fmt, concept)
        blocking, style = validate(fmt, build)
        if blocking or (strict and style):
            return None
        try:
            return (build, *render_build(fmt, build, art.palette, sch))
        except ImageProviderError:
            return None

    @staticmethod
    def _from_current(fmt: MemeFormat, current: dict[str, Any], art: ArtDirection, sch: Scheme) -> Built | None:
        try:
            build = MemeBuild.model_validate(current)
            return (build, *render_build(fmt, build, art.palette, sch))
        except (ImageProviderError, ValueError):
            return None

    async def _revise(
        self, fmt: MemeFormat, current: MemeBuild, instruction: str, art: ArtDirection, usage: UsageSink | None, sch: Scheme | None = None
    ) -> Built | None:
        """Change a built meme's words and data as asked, keeping the rest; None when the change could not be drawn."""
        prompt = render(
            "meme_edit",
            instruction=instruction.strip(),
            spec=build_spec(fmt),
            current=current.model_dump_json(indent=1),
            brand=art.brand,
        )

        async def ask(note: str) -> MemeBuild:
            return await self.llm.structured(
                task=f"meme edit ({fmt.id})",
                system=self.system,
                prompt=prompt + note,
                schema=MemeBuild,
                effort=self.settings.effort_images,
                max_tokens=16000,
                usage=usage,
            )

        def draw(build: MemeBuild, last: bool) -> tuple[bytes, int, int]:
            build.art, build.cast_defs = [], ""
            blocking, style = validate(fmt, build)
            if blocking or (style and not last):
                raise ImageProviderError("\n".join(blocking + style))
            return render_build(fmt, build, art.palette, sch)

        try:
            build, (png, width, height) = await draw_with_retry(ask, draw)
        except ImageProviderError as exc:
            log.info("Meme %s edit could not be drawn: %s", fmt.id, exc)
            return None
        return build, png, width, height

    async def _restage(
        self,
        state: dict[str, Any],
        fmt: MemeFormat,
        current: MemeBuild,
        instruction: str,
        art: ArtDirection,
        usage: UsageSink | None,
        *,
        sch: Scheme | None = None,
    ) -> Built | None:
        """Change a code-drawn meme: Claude changes the words, the casting or the comic panels; code redraws it."""
        snapshot = {
            "texts": [t.model_dump() for t in current.texts],
            "cast": [c.model_dump() for c in current.cast],
            "panels": [p.model_dump() for p in current.panels],
        }
        prompt = render(
            "meme_restage",
            instruction=instruction.strip(),
            spec=build_spec(fmt),
            current=json.dumps(snapshot, indent=1),
            kit=_kit_menu(),
        )
        try:
            edit = await self.llm.structured(
                task=f"meme edit ({fmt.id})",
                system=self.system,
                prompt=prompt,
                schema=MemeStagingEdit,
                effort=self.settings.effort_images,
                max_tokens=8000,
                usage=usage,
            )
        except LLMError as exc:
            log.info("Meme restage failed: %s", exc)
            return None
        build = current.model_copy(
            update={
                "texts": edit.texts or current.texts,
                "cast": edit.cast or current.cast,
                "panels": edit.panels if fmt.family == "comic" and edit.panels else current.panels,
            }
        )
        build = build.model_copy(update={"alt": alt_text(fmt, build.texts, build.data, build.cast, build.panels)})
        blocking, _ = validate(fmt, build)
        if blocking:
            return None
        try:
            return (build, *render_build(fmt, build, art.palette, sch or scheme_of(state, art.palette)))
        except ImageProviderError:
            return None


def _kit_menu() -> str:
    from inferno_ghostwriter.images.kit.props import menu as props_menu
    from inferno_ghostwriter.images.memes.cast import menu as cast_menu

    return cast_menu() + "\n" + props_menu()

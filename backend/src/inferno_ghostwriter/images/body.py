"""The room for in-body images (illustration, diagram, chart, screenshot, icon): the same flow as the opener and closer.

1. **Pitch** (``BodyIdeas``): a few different ways to show this spot of the post (a diagram vs. a chart vs. an
   illustrated metaphor), each quoting the passage it serves; seeded angle cards keep runs varied.
2. **Draw** the best ``image_body_candidates`` at once (one design call each, Claude SVG or Vega-Lite, linted and
   snapped to the post's colors).
3. **Judge** them as pictures (``judge.judge_sheet``) against the author's reference diagrams, refine the best one
   with its fix, and keep the best ``image_finalists`` for the author to swap between.

The pitches live in ``ProjectImage.ideas`` so the ideas board, Redraw and picking an idea need no new pitching call.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images.base import Drawn, ImageProviderError, draw_with_retry, thumbnail_png
from inferno_ghostwriter.images.judge import judge_sheet
from inferno_ghostwriter.images.lint import lint
from inferno_ghostwriter.images.palettes import Scheme
from inferno_ghostwriter.images.references import ReferenceLibrary, load_png
from inferno_ghostwriter.images.render import svg_to_png, vega_to_png
from inferno_ghostwriter.images.specs import ChartSpec, SvgSpec
from inferno_ghostwriter.images.story import anchored, deal
from inferno_ghostwriter.llm import LLM, LLMError, SystemBlock
from inferno_ghostwriter.llm.base import LLMImagesUnsupportedError, UsageSink
from inferno_ghostwriter.prompts import raw, render

log = logging.getLogger(__name__)

RENDER_WIDTH = {"illustration": 1600, "diagram": 1600, "screenshot": 1600, "icon": 768, "chart": 1600}
# How a slot of each kind may be drawn: a diagram may become a chart or an illustrated metaphor, never the reverse of a
# screenshot (that shows a real screen) or an icon (it anchors a list).
KIND_OPTIONS = {
    "illustration": ("illustration", "diagram"),
    "diagram": ("diagram", "illustration", "chart"),
    "chart": ("chart", "diagram"),
    "screenshot": ("screenshot",),
    "icon": ("icon",),
}
PITCHES = 4


class BodyIdea(BaseModel):
    kind: str = Field(description="How to draw it: one of the kinds allowed for this slot.")
    hook: str = Field(description="What this image adds for the reader, in one sentence.")
    concept: str = Field(description="What the picture shows, concretely enough to draw: layout, elements, labels, data.")
    reader_takeaway: str = Field(description="At a glance a reader sees ___ and understands ___.")
    anchor: str = Field("", description="5-15 words copied exactly from the post that this image serves.")
    figures: str = Field("none", description="'none', or 'simple' for a few simple flat figures where a person helps the idea.")


class BodyIdeas(BaseModel):
    concepts: list[BodyIdea] = Field(description="Distinct ideas, as many as asked, each a different way to show it.")


@dataclass
class BodyContext:
    kind: str
    slot_id: str
    title: str
    purpose: str
    brief: str
    visual_style: str
    brand: str
    image_guidance: str
    siblings: str
    builds_on: str
    context: str
    markdown: str
    palette: tuple[str, ...] = ()
    scheme: Scheme | None = None
    note: str = ""
    seed: int | None = None
    reference: bytes | None = None


def _canvas(svg: str) -> tuple[int, int]:
    match = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', svg)
    return (round(float(match.group(1))), round(float(match.group(2)))) if match else (1600, 900)


def concept_text(idea: dict[str, Any]) -> str:
    parts = [f"Draw it as: {idea.get('kind')}", f"Idea: {idea.get('concept')}", f"Reader takeaway: {idea.get('reader_takeaway')}"]
    if idea.get("figures") == "simple":
        parts.append("Use a few simple flat figures (round heads, soft rounded bodies, dot eyes, no real likenesses).")
    return "\n".join(p for p in parts if not p.endswith(": None"))


class BodyRoom:
    def __init__(self, llm: LLM, settings: Settings) -> None:
        self.llm = llm
        self.settings = settings
        self.system = [SystemBlock(raw("image_system"), cache=True)]
        self.references = ReferenceLibrary(settings.image_reference_dir)

    # -- pitching -------------------------------------------------------------------------

    async def pitch(self, ctx: BodyContext, exclude: list[str], usage: UsageSink | None) -> dict[str, Any]:
        kinds = KIND_OPTIONS.get(ctx.kind, (ctx.kind,))
        seed = ctx.seed if ctx.seed is not None else random.randrange(1 << 30)
        prompt = render(
            "image_ideas",
            kind=ctx.kind,
            kinds=", ".join(f"`{k}`" for k in kinds),
            count=PITCHES,
            title=ctx.title,
            purpose=ctx.purpose,
            brief=ctx.brief,
            note=f"The author's direction for this image: {ctx.note}\n" if ctx.note else "",
            exclude=("These ideas were already used; pitch different ones:\n" + "\n".join(f"- {e}" for e in exclude) + "\n")
            if exclude
            else "",
            cards=deal(ctx.context, seed=seed),
            siblings=ctx.siblings,
            context=ctx.context,
        )
        ideas = await self.llm.structured(
            task=f"{ctx.kind} image ideas",
            system=self.system,
            prompt=prompt,
            schema=BodyIdeas,
            effort=self.settings.effort_images,
            max_tokens=8000,
            usage=usage,
        )
        concepts = []
        for idea in ideas.concepts:
            entry = idea.model_dump()
            entry["kind"] = idea.kind if idea.kind in kinds else kinds[0]
            entry["anchored"] = anchored(idea.anchor, ctx.markdown)
            concepts.append(entry)
        if not concepts:
            raise ImageProviderError("Claude did not pitch any ideas for this image. Click Redraw to try again.")
        # Ideas whose quote is not in the post go last; otherwise the pitcher's order stands until the judge sees them.
        order = sorted(range(len(concepts)), key=lambda i: not concepts[i]["anchored"])
        return {"brief": ctx.brief, "concepts": [concepts[i] for i in order], "chosen": None, "tried": [], "seed": seed}

    # -- drawing ---------------------------------------------------------------------------

    async def run(self, ideas: dict[str, Any], ctx: BodyContext, usage: UsageSink | None) -> tuple[Drawn, int]:
        """Draw the best ideas, judge them, refine the winner; returns the winner (with finalists) and its index."""
        concepts = ideas["concepts"]
        count = max(1, self.settings.image_body_candidates)
        picks = [i for i in range(len(concepts)) if i not in set(ideas.get("tried", []))][:count] or [0]
        results = await asyncio.gather(*(self._safe_draw(concepts[i], ctx, "", usage) for i in picks))
        options = [(i, d) for i, d in zip(picks, results, strict=True) if d is not None]
        if not options:
            raise ImageProviderError("None of the ideas for this image could be drawn. Click Redraw to try again.")
        keep = max(1, self.settings.image_finalists)
        refs = self.references.for_category("diagram", 2) if ctx.kind != "screenshot" else []
        sheet = await judge_sheet(
            self.llm,
            self.settings,
            context=f"An in-body {ctx.kind} for the post '{ctx.title}'. Its job: {ctx.purpose}\nAround it:\n{ctx.context[:3000]}",
            candidates=[concept_text(concepts[i]) for i, _ in options],
            pngs=[thumbnail_png(d.png) for _, d in options],
            references=[*(load_png(refs, 512) if refs else []), *([ctx.reference] if ctx.reference else [])],
            reference_note="the author's own diagrams: the quality and style to aim for",
            usage=usage,
        )
        if sheet is not None:
            order = sheet.order()[:keep]
            for k, (i, d) in enumerate(options):
                d.score, d.reads_as = round(sheet.scores[k], 2), sheet.reads_as[k]
                concepts[i]["reads_as"] = sheet.reads_as[k]
            best_k = order[0]
            if sheet.fixes[best_k]:
                i, current = options[best_k]
                fixed = await self._safe_draw(concepts[i], ctx, self._fix_note(sheet.fixes[best_k], current), usage)
                if fixed is not None:
                    fixed.score, fixed.reads_as = current.score, current.reads_as
                    options[best_k] = (i, fixed)
        else:
            order = list(range(min(keep, len(options))))
        finalists = []
        for k in order:
            i, d = options[k]
            d.label = concepts[i].get("hook") or concepts[i].get("concept", "")
            finalists.append((i, d))
        ideas["tried"] = sorted({*ideas.get("tried", []), *(i for i, _ in options)})
        winner_index, winner = finalists[0]
        winner.finalists = [d for _, d in finalists] if len(finalists) > 1 else []
        return winner, winner_index

    @staticmethod
    def _fix_note(fix: str, current: Drawn) -> str:
        return (
            "\nThe judge looked at the finished picture and asked for one change; keep everything else exactly as it is:\n"
            f"<instruction>\n{fix}\n</instruction>\nThe current design:\n<current>\n{current.spec[:20000]}\n</current>\n"
        )

    async def _safe_draw(self, idea: dict[str, Any], ctx: BodyContext, extra: str, usage: UsageSink | None) -> Drawn | None:
        try:
            return await self.draw(idea, ctx, extra, usage)
        except (ImageProviderError, LLMError) as exc:
            log.info("Body idea could not be drawn: %s", exc)
            return None

    async def draw(self, idea: dict[str, Any] | None, ctx: BodyContext, variation: str, usage: UsageSink | None) -> Drawn:
        """One design call for one idea (or the slot's own brief when there is none)."""
        kind = str((idea or {}).get("kind") or ctx.kind)
        brief = concept_text(idea) if idea else ctx.brief
        prompt = render(
            "image_spec",
            kind=kind,
            slot_id=ctx.slot_id,
            title=ctx.title,
            purpose=ctx.purpose,
            brief=brief,
            visual_style=ctx.visual_style,
            brand=ctx.brand + (f"\nColors: {ctx.scheme.describe()}" if ctx.scheme is not None and kind != "chart" else ""),
            variation=variation + (f"\nThe author asked: {ctx.note}" if ctx.note else ""),
            image_guidance=ctx.image_guidance,
            siblings=ctx.siblings,
            builds_on=ctx.builds_on,
            context=ctx.context,
        )
        if ctx.reference is not None:
            prompt += (
                "\nThe author attached the image shown as a style reference: match its look (layout style, color use, "
                "shapes, type, polish), not its content.\n"
            )
        return await self.design(
            kind, prompt, task=f"{kind} image design", palette=ctx.palette, scheme=ctx.scheme, reference=ctx.reference, usage=usage
        )

    async def design(
        self,
        kind: str,
        prompt: str,
        *,
        task: str,
        palette: tuple[str, ...] = (),
        scheme: Scheme | None = None,
        reference: bytes | None = None,
        usage: UsageSink | None,
    ) -> Drawn:
        """Ask Claude for the design and draw it; a design that cannot be drawn gets one more try with the error quoted."""

        async def design[S: BaseModel](
            schema: type[S], draw: Callable[[S, bool], tuple[bytes, int, int]]
        ) -> tuple[S, tuple[bytes, int, int]]:
            async def ask(note: str) -> S:
                kwargs: dict[str, Any] = {
                    "task": task,
                    "system": self.system,
                    "prompt": prompt + note,
                    "schema": schema,
                    "effort": self.settings.effort_images,
                    "max_tokens": 24000,
                    "usage": usage,
                }
                if reference is None:
                    return await self.llm.structured(**kwargs)
                try:
                    return await self.llm.structured(**kwargs, images=[reference])
                except LLMImagesUnsupportedError:
                    return await self.llm.structured(**kwargs)

            return await draw_with_retry(ask, draw)

        if kind == "chart":
            chart, (png, w, h) = await design(
                ChartSpec, lambda c, _last: vega_to_png(c.vega_lite_json, palette=palette, illustrative=c.data_is_illustrative)
            )
            caption = chart.caption
            if chart.data_is_illustrative and "illustrative" not in caption.lower():
                caption = f"{caption} (illustrative data)"
            return Drawn(png, w, h, "vega-lite", chart.vega_lite_json, chart.alt, caption)

        def draw_svg(made: SvgSpec, last: bool) -> tuple[bytes, int, int]:
            if scheme is not None and kind in ("illustration", "diagram", "icon"):
                report = lint(made.svg, size=_canvas(made.svg), allowed_colors=scheme.allowed, what=f"the {kind}")
                if report.problems and not last:
                    raise ImageProviderError("\n".join(report.problems))
                made.svg = report.svg
            return svg_to_png(made.svg, width=RENDER_WIDTH.get(kind, 1600))

        svg, (png, w, h) = await design(SvgSpec, draw_svg)
        return Drawn(png, w, h, "claude-svg", svg.svg, svg.alt, svg.caption)

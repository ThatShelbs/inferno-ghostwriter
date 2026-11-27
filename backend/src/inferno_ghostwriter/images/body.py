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
import json
import logging
import random
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.images import raster
from inferno_ghostwriter.images.base import Drawn, ImageProviderError, draw_with_retry, guest_pitches, thumbnail_png
from inferno_ghostwriter.images.diagrams import TEMPLATES, DiagramSpec, render_diagram_png
from inferno_ghostwriter.images.diagrams import menu as diagram_menu
from inferno_ghostwriter.images.figures import FigureColors, catalog_text
from inferno_ghostwriter.images.figures import inject as inject_figures
from inferno_ghostwriter.images.judge import judge_sheet, rank_pitches, to_refine
from inferno_ghostwriter.images.kinds import BODY_KINDS, KINDS
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

# Views of the kind table (``images/kinds.py``): in-body kinds GPT may paint instead of Claude drawing them (wordless
# pictures) and their size, the width each kind's SVG is rendered at, and how a slot of each kind may be drawn (a
# diagram may become a chart or an illustrated metaphor; a screenshot shows a real screen, an icon anchors a list).
PAINTABLE = tuple(k for k in BODY_KINDS if KINDS[k].paintable)
PAINT_SIZE = {k: KINDS[k].paint_size for k in PAINTABLE}
RENDER_WIDTH = {k: KINDS[k].render_width for k in BODY_KINDS}
KIND_OPTIONS = {k: KINDS[k].redraw_as for k in BODY_KINDS}
PITCHES = 4


class BodyIdea(BaseModel):
    kind: str = Field(description="How to draw it: one of the kinds allowed for this slot.")
    hook: str = Field(description="What this image adds for the reader, in one sentence.")
    concept: str = Field(description="What the picture shows, concretely enough to draw: layout, elements, labels, data.")
    reader_takeaway: str = Field(description="At a glance a reader sees ___ and understands ___.")
    anchor: str = Field("", description="5-15 words copied exactly from the post that this image serves.")
    figures: str = Field("none", description="'none', or 'simple' for a few simple flat figures where a person helps the idea.")
    template: str = Field("", description="For a diagram: a template id from the list (code draws it cleanly), or '' to draw freehand.")


class DiagramDesign(BaseModel):
    """A diagram template filled with the post's words (code lays it out; see images/diagrams)."""

    diagram: DiagramSpec
    caption: str = Field(description="Caption in the author's style, without the credit.")


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
            templates=diagram_menu() if "diagram" in kinds else "(none: this kind is drawn freehand)",
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
        pitches = list(ideas.concepts)
        if pitches and self.settings.secondary.ideation:
            used = {idea.concept.strip().casefold() for idea in pitches}
            guest_prompt = prompt + "\n\nPitch two alternatives to these existing ideas:\n" + "\n".join(idea.concept for idea in pitches)
            results = await guest_pitches(
                self.llm,
                self.settings,
                task=f"{ctx.kind} image ideas",
                system=self.system,
                prompt=guest_prompt,
                schema=BodyIdeas,
                usage=usage,
            )
            for guest in results:
                for idea in guest.concepts[:2]:
                    key = idea.concept.strip().casefold()
                    if key and key not in used and idea.kind in kinds and anchored(idea.anchor, ctx.markdown):
                        used.add(key)
                        pitches.append(idea)
        concepts = []
        for idea in pitches:
            entry = idea.model_dump()
            entry["kind"] = idea.kind if idea.kind in kinds else kinds[0]
            entry["anchored"] = anchored(idea.anchor, ctx.markdown)
            concepts.append(entry)
        if not concepts:
            raise ImageProviderError("Claude did not pitch any ideas for this image. Click Redraw to try again.")
        # Ideas whose quote is not in the post go last; otherwise the pitcher's order stands until the judge sees them.
        order = list(range(len(concepts)))
        if self.settings.secondary.judges:
            ranking = await rank_pitches(
                self.llm, self.settings, context=ctx.context, candidates=[concept_text(idea) for idea in concepts], usage=usage
            )
            if ranking is not None:
                order = ranking.order()
        order.sort(key=lambda i: not concepts[i]["anchored"])
        return {"brief": ctx.brief, "concepts": [concepts[i] for i in order], "chosen": None, "tried": [], "seed": seed}

    # -- drawing ---------------------------------------------------------------------------

    async def run(
        self, ideas: dict[str, Any], ctx: BodyContext, usage: UsageSink | None, *, among: list[int] | None = None
    ) -> tuple[Drawn, int]:
        """Draw the best ideas, judge them, refine the winner; returns the winner (with finalists) and its index.

        ``among`` limits the candidates to those ideas (a new round added to the board)."""
        concepts = ideas["concepts"]
        count = max(1, self.settings.image_body_candidates)
        pool = among if among else list(range(len(concepts)))
        picks = [i for i in pool if i not in set(ideas.get("tried", []))][:count] or pool[:1] or [0]
        options: list[tuple[int, Drawn]] = []
        if ctx.kind in PAINTABLE and await raster.use_native(self.llm, self.settings, f"body:{ctx.title}:{ctx.slot_id}"):
            # GPT generates this slot instead of Claude drawing it: the same number of candidates, all native.
            ideas_ok = [i for i in picks if concepts[i].get("kind", ctx.kind) == ctx.kind] or picks[:1]
            made = await asyncio.gather(*(self._painted(concepts[i], ctx, usage) for i in ideas_ok))
            options = [(i, d) for i, d in zip(ideas_ok, made, strict=True) if d is not None]
        if not options:  # drawn slot, or generation failed: Claude draws the same pitches
            results = await asyncio.gather(*(self._safe_draw(concepts[i], ctx, "", usage) for i in picks))
            options = [(i, d) for i, d in zip(picks, results, strict=True) if d is not None]
        if not options:
            raise ImageProviderError("None of the ideas for this image could be drawn. Click Redraw to try again.")
        keep = max(1, self.settings.image_finalists)
        refs = self.references.for_category("diagram", 2) if ctx.kind != "screenshot" else []
        if any(concepts[i].get("figures") == "simple" for i, _ in options):
            refs = [*refs, *self.references.cast_sheet()]
        sheet = await judge_sheet(
            self.llm,
            self.settings,
            context=f"An in-body {ctx.kind} for the post '{ctx.title}'. Its job: {ctx.purpose}\nAround it:\n{ctx.context[:3000]}",
            candidates=[concept_text(concepts[i]) + (" (generated by GPT)" if d.provider == raster.PROVIDER else "") for i, d in options],
            pngs=[thumbnail_png(d.png) for _, d in options],
            references=[*(load_png(refs, 512) if refs else []), *([ctx.reference] if ctx.reference else [])],
            reference_note="the author's own diagrams: the quality and style to aim for",
            usage=usage,
        )
        if sheet is not None:
            order = sheet.order()[:keep]
            for k, (i, d) in enumerate(options):
                d.score, d.reads_as, d.fix = round(sheet.scores[k], 2), sheet.reads_as[k], sheet.fixes[k]
                concepts[i]["reads_as"] = sheet.reads_as[k]
            for best_k in to_refine(sheet.scores, order, self.settings):
                if not sheet.fixes[best_k]:
                    continue
                i, current = options[best_k]
                if current.provider == raster.PROVIDER:
                    try:
                        fixed: Drawn | None = await self.repaint(current.spec, sheet.fixes[best_k], current.png, usage)
                    except ImageProviderError:
                        fixed = None
                else:
                    fixed = await self._safe_draw(concepts[i], ctx, self._fix_note(sheet.fixes[best_k], current), usage)
                if fixed is not None:
                    fixed.score, fixed.reads_as = current.score, current.reads_as  # its fix is applied: none left
                    options[best_k] = (i, fixed)
        else:
            order = list(range(min(keep, len(options))))
        finalists = []
        for k in order:
            i, d = options[k]
            d.label = (concepts[i].get("hook") or concepts[i].get("concept", "")) + (
                " (generated by GPT)" if d.provider == raster.PROVIDER else ""
            )
            finalists.append((i, d))
        ideas["tried"] = sorted({*ideas.get("tried", []), *(i for i, _ in options)})
        winner_index, winner = finalists[0]
        winner.finalists = [d for _, d in finalists] if len(finalists) > 1 else []
        return winner, winner_index

    async def _painted(self, idea: dict[str, Any], ctx: BodyContext, usage: UsageSink | None) -> Drawn | None:
        """A natively generated illustration or icon from the pitch (None when generation is unavailable or fails)."""
        what = "A simple, bold icon (one subject, no background clutter)" if ctx.kind == "icon" else "An illustration"
        subject = f"{what} for a blog post titled '{ctx.title}'. Its job: {ctx.purpose}\n{concept_text(idea)}"
        extra = "\n".join(
            x for x in (ctx.visual_style and f"Visual style: {ctx.visual_style}", ctx.note and f"The author asked: {ctx.note}") if x
        )
        width, height = PAINT_SIZE.get(ctx.kind, (1600, 900))
        prompt = raster.prompt_for(subject, scheme=ctx.scheme, palette=ctx.palette, extra=extra, shape=raster.aspect(width, height))
        png = await raster.paint(self.llm, prompt, size=(width, height), images=[ctx.reference] if ctx.reference else None, usage=usage)
        if png is None:
            return None
        alt = str(idea.get("reader_takeaway") or idea.get("concept") or ctx.purpose)
        return Drawn(png, width, height, raster.PROVIDER, raster.spec(prompt, alt=alt, size=[width, height]), alt, "")

    async def repaint(self, spec: str, instruction: str, current: bytes | None, usage: UsageSink | None) -> Drawn:
        """Paint a painting again from its stored prompt. With ``current`` (an edit, or the judge's fix) GPT changes
        that picture as ``instruction`` asks and keeps the rest; without it (a redraw) ``instruction`` is the twist."""
        stored = raster.load(spec) or {}
        base = str(stored.get("prompt") or "")
        if not base:
            raise ImageProviderError("This painting has no stored prompt. Redraw it instead.")
        prompt, note, shown = base, instruction.strip(), None
        if note and current is not None:
            prompt, shown = f"{base}\nChange the attached picture as follows and keep everything else exactly as it is: {note}", [current]
        elif note:
            prompt = f"{base}\n{note}"
        size = stored.get("size")
        width, height = (int(size[0]), int(size[1])) if isinstance(size, list) and len(size) == 2 else (1600, 900)
        png = await raster.paint(self.llm, prompt, size=(width, height), images=shown, usage=usage)
        if png is None:
            raise ImageProviderError("GPT image generation is unavailable. Sign in to Codex in Settings, or Redraw to let Claude draw it.")
        # The stored prompt stays the original: an edit changes the picture, not what it is of.
        spec_text = raster.spec(base, alt=stored.get("alt", ""), size=[width, height])
        return Drawn(png, width, height, raster.PROVIDER, spec_text, str(stored.get("alt") or ""), "")

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
        template = str((idea or {}).get("template") or "")
        if kind == "diagram" and template in TEMPLATES and not ctx.builds_on:
            return await self.diagram(template, concept_text(idea or {}), ctx, variation, usage)
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
        if (idea or {}).get("figures") == "simple" or kind == "illustration":
            prompt += "\n" + catalog_text() + "\n"
        if ctx.reference is not None:
            prompt += (
                "\nThe author attached the image shown as a style reference: match its look (layout style, color use, "
                "shapes, type, polish), not its content.\n"
            )
        return await self.design(
            kind, prompt, task=f"{kind} image design", palette=ctx.palette, scheme=ctx.scheme, reference=ctx.reference, usage=usage
        )

    async def diagram(self, template: str, idea: str, ctx: BodyContext, variation: str, usage: UsageSink | None) -> Drawn:
        """A code-drawn diagram: Claude fills the template with the post's words (one call), code lays it out."""
        t = TEMPLATES[template]
        prompt = render(
            "image_diagram",
            template=template,
            title=ctx.title,
            purpose=ctx.purpose,
            idea=idea,
            variation=variation + (f"\nThe author asked: {ctx.note}" if ctx.note else ""),
            template_line=f"`{t.id}`: {t.name}. Use when {t.use_when}. Set `diagram.template` to `{t.id}`.",
            context=ctx.context,
        )
        if ctx.reference is not None:
            prompt += "\nThe author attached the image shown as a style reference: match its emphasis and density, not its content.\n"
        return await self.fill_diagram(template, prompt, ctx.scheme, usage, reference=ctx.reference)

    async def fill_diagram(
        self, template: str, prompt: str, scheme: Scheme | None, usage: UsageSink | None, *, reference: bytes | None = None
    ) -> Drawn:
        from inferno_ghostwriter.images.palettes import scheme as house_scheme

        async def ask(note: str) -> DiagramDesign:
            kwargs: dict[str, Any] = {
                "task": "diagram design",
                "system": self.system,
                "prompt": prompt + note,
                "schema": DiagramDesign,
                "effort": self.settings.effort_images,
                "max_tokens": 8000,
                "usage": usage,
            }
            if reference is None:
                return await self.llm.structured(**kwargs)
            try:
                return await self.llm.structured(**kwargs, images=[reference])
            except LLMImagesUnsupportedError:
                return await self.llm.structured(**kwargs)

        def draw(made: DiagramDesign, _last: bool) -> tuple[bytes, int, int]:
            if made.diagram.template != template:
                raise ImageProviderError(f"Fill the `{template}` template (you returned `{made.diagram.template}`).")
            return render_diagram_png(made.diagram, scheme or house_scheme("inferno", "white"))

        made, (png, w, h) = await draw_with_retry(ask, draw)
        return Drawn(png, w, h, "claude-diagram", made.diagram.model_dump_json(), made.diagram.alt or made.caption, made.caption)

    async def edit_diagram(self, spec: str, instruction: str, scheme: Scheme | None, usage: UsageSink | None) -> Drawn:
        """Change a code-drawn diagram's words, numbers or emphasis as the author asks; the layout stays code's."""
        template = str(json.loads(spec).get("template") or "")
        if template not in TEMPLATES:
            raise ImageProviderError("This diagram can no longer be edited; Redraw it instead.")
        prompt = (
            f"Edit this `{template}` diagram exactly as the author asks; keep everything the instruction does not mention.\n"
            f"<instruction>\n{instruction.strip()}\n</instruction>\nThe current diagram:\n<current>\n{spec}\n</current>\n"
            "Return the whole edited diagram and a caption."
        )
        return await self.fill_diagram(template, prompt, scheme, usage)

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
                ChartSpec,
                lambda c, _last: vega_to_png(c.vega_lite_json, palette=palette, scheme=scheme, illustrative=c.data_is_illustrative),
            )
            caption = chart.caption
            if chart.data_is_illustrative and "illustrative" not in caption.lower():
                caption = f"{caption} (illustrative data)"
            return Drawn(png, w, h, "vega-lite", chart.vega_lite_json, chart.alt, caption)

        check = KINDS[kind].lint if kind in KINDS else None

        def draw_svg(made: SvgSpec, last: bool) -> tuple[bytes, int, int]:
            # Free checks before anything is judged: strays, off-canvas shapes and dead references are fixed in code;
            # "scheme" kinds are also snapped onto the post's colors (a screen mock keeps its own greys).
            if check is not None and (check == "structure" or scheme is not None):
                colors = scheme.allowed if check == "scheme" and scheme is not None else ()
                report = lint(made.svg, size=_canvas(made.svg), allowed_colors=colors, what=f"the {kind}")
                if report.problems and not last:
                    raise ImageProviderError("\n".join(report.problems))
                made.svg = report.svg
            made.svg = inject_figures(made.svg, FigureColors.from_scheme(scheme) if scheme is not None else None)
            return svg_to_png(made.svg, width=RENDER_WIDTH.get(kind, 1600))

        svg, (png, w, h) = await design(SvgSpec, draw_svg)
        return Drawn(png, w, h, "claude-svg", svg.svg, svg.alt, svg.caption)

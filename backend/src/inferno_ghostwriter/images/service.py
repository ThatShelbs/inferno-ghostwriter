"""Design and render every image in a post, with credits, finalists and redraw history.

Every image goes through a room with the same flow (pitch, draw candidates, judge, refine, keep finalists):
``OpeningRoom`` for the opening image, ``MemeMaker`` for the closing meme and ``BodyRoom`` for in-body images. All are
rendered locally. Model-generated code runs only for ``hands_on_viz`` images (``handson.py``), and only when the author
turned "Run example code" on.
"""

from __future__ import annotations

import json
import logging
import random
import re
import traceback
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Persona, Project, ProjectImage
from inferno_ghostwriter.experiments.models import MONTAGE_SLOT, Scenario
from inferno_ghostwriter.experiments.models import load as load_experiment
from inferno_ghostwriter.experiments.models import measure as measure_code
from inferno_ghostwriter.images import handson, raster
from inferno_ghostwriter.images import remix as remixing
from inferno_ghostwriter.images.base import PLACEHOLDER_RE, Drawn, ImageProviderError, thumbnail_png
from inferno_ghostwriter.images.body import BodyContext, BodyRoom
from inferno_ghostwriter.images.codeblocks import code_before, replace_code
from inferno_ghostwriter.images.handson import HandsOn
from inferno_ghostwriter.images.memes import (
    ArtDirection,
    MemeContext,
    MemeMaker,
    get_format,
    load_state,
    plan_callbacks,
    voice_section,
)
from inferno_ghostwriter.images.montage import HEIGHT, MIN_TILES, WIDTH, Tile, make_montage
from inferno_ghostwriter.images.opening.room import OpeningContext, OpeningRoom, opening_meme_spec
from inferno_ghostwriter.images.opening.room import load_state as load_opening_state
from inferno_ghostwriter.images.opening.styles import BY_ID as OPENING_STYLES
from inferno_ghostwriter.images.palettes import Scheme, brand_scheme, from_id, house_ramp, scheme
from inferno_ghostwriter.images.render import add_meme_text, svg_to_png
from inferno_ghostwriter.images.specs import SvgMemeSpec
from inferno_ghostwriter.llm import LLM, LLMError
from inferno_ghostwriter.llm.base import UsageSink
from inferno_ghostwriter.llm.router import lead_provider
from inferno_ghostwriter.llm.secondary import LABELS, MODEL_IDS
from inferno_ghostwriter.prompts import render
from inferno_ghostwriter.sandbox import Sandbox
from inferno_ghostwriter.storage import Storage

log = logging.getLogger(__name__)

MAX_EDIT_NOTES = 8
MAX_EDIT_SPEC = 20000
STALE_PENDING = "Generation stopped before this image was made. Click Redraw to create it."
HISTORY_FIELDS = ("file_name", "provider", "seed", "prompt", "spec", "alt", "caption", "credit", "width", "height", "edits")


# The task that designs each kind of drawing: with image routing on, an optional model may design it, and the
# credit then names that model (code still draws it).
MAKER_TASKS = {
    "vega-lite": "chart image design",
    "claude-diagram": "diagram design",
    "claude-art": "opening data art",
    "claude-opening": "opening template build",
    "claude-meme": "meme ideas",
    "claude-svg": "illustration image design",
}
OPTIONAL_LABELS = {MODEL_IDS[p]: LABELS[p].split(" (")[0] for p in MODEL_IDS}
# Who designed each kind in the image being made (set per image in ``create``; read by ``_result``).
_makers: ContextVar[dict[str, str] | None] = ContextVar("image_makers", default=None)


def model_label(model: str) -> str:
    """'claude-opus-5-5' -> 'Claude Opus 5.5', an optional model's id -> its name (others are returned unchanged)."""
    if model in OPTIONAL_LABELS:
        return OPTIONAL_LABELS[model]
    match = re.fullmatch(r"claude-([a-z]+)-(\d+)-(\d+)(?:-\d{8})?", model)
    if not match:
        return model
    family, major, minor = match.groups()
    return f"Claude {family.capitalize()} {major}.{minor}"


def tool_label(provider: str, model: str) -> str:
    """The credit names who designed the image, never the drawing tool (a tool name can contradict the post's code)."""
    claude = model_label(model)
    return {
        raster.PROVIDER: raster.TOOL_LABEL,
        handson.MONTAGE_PROVIDER: "Inferno Ghostwriter",
        "placeholder": "Inferno Ghostwriter",
    }.get(provider, claude)


def credit_line(persona: Persona, provider: str, model: str = "claude-opus-5-5") -> str:
    name = persona.display_name or persona.name
    if provider == "upload":
        return f"Image by {name}"
    tool = tool_label(provider, model)
    try:
        return persona.credit_template.format(name=name, tool=tool)
    except (KeyError, IndexError, ValueError):
        return f"Author: {name}; Made with {tool}"


def image_context(markdown: str, slot_id: str, before: int = 1500, after: int = 700) -> str:
    marker = f"{{{{image:{slot_id}}}}}"
    index = markdown.find(marker)
    if index < 0:
        return markdown[:before]
    start = max(0, index - before)
    snippet = markdown[start:index] + ">>> IMAGE HERE <<<" + markdown[index + len(marker) : index + len(marker) + after]
    return PLACEHOLDER_RE.sub("", snippet).strip()


DEFAULT_VISUAL_STYLE = "clean, polished flat-vector editorial style"


def brand_guidance(brand_kit: dict[str, Any] | None, persona: Persona) -> tuple[str, str]:
    """The post's brand kit as (visual style, extra art direction); empty fields fall back to the persona."""
    kit = brand_kit or {}
    style = str(kit.get("style") or "").strip() or persona.visual_style or DEFAULT_VISUAL_STYLE
    lines = []
    if palette := [str(c) for c in kit.get("palette") or []]:
        lines.append(f"Brand palette for this post (use these colors instead of the inferno palette): {' '.join(palette)}")
    if font := str(kit.get("font") or "").strip():
        lines.append(f"Brand font for any text in the image: {font} (fall back to Segoe UI, Helvetica, Arial, sans-serif)")
    if motif := str(kit.get("motif") or "").strip():
        lines.append(f"Recurring motif to weave into every image of this post: {motif}")
    return style, "\n".join(lines)


def image_guidance(voice_profile: str) -> str:
    return voice_section(voice_profile, "Images") or "Use clear, relevant images with short captions and a credit."


def brand_palette(brand_kit: dict[str, Any] | None) -> tuple[str, ...]:
    return tuple(str(c) for c in (brand_kit or {}).get("palette") or [])


def _resolved(dials: dict[str, Any], persona: Persona, brief: str) -> Any:
    """The post's dials resolved the way the writer resolved them; None for dials an older version saved."""
    # Imported here because the writer package imports this one.
    from inferno_ghostwriter.writer.dials import Dials, resolve

    try:
        return resolve(Dials(**dials), persona, brief, default_revisions=0)
    except ValueError:
        return None


def _formula_note(dials: dict[str, Any], persona: Persona, brief: str) -> str:
    """The post's formula as the meme room should read it: the same one the writer followed."""
    from inferno_ghostwriter.writer.formulas import NOTE_FIELDS, PART_FIELDS, ResolvedFormula, meme_note

    resolved = _resolved(dials, persona, brief)
    if resolved is None:  # dials saved by an older version: the meme is pitched without the formula
        return ""
    return meme_note(ResolvedFormula(**{field: getattr(resolved, field) for field in (*PART_FIELDS, *NOTE_FIELDS)}))


def is_meme(image: ProjectImage) -> bool:
    """A closing meme, or an opening image that is a meme (a meme sandwich): both have meme words and pitches."""
    return image.kind == "meme" or (image.kind == "hero" and opening_meme_spec(image.spec) is not None)


def meme_spec(image: ProjectImage) -> str:
    """The meme state of a meme image, whichever end of the post it is on."""
    if image.kind == "hero":
        return opening_meme_spec(image.spec) or ""
    return image.spec


def remix_dimensions(image: ProjectImage) -> tuple[str, ...]:
    """What a redraw of this image may vary (colors, cast, staging, medium): it depends on the kind and opening style."""
    if image.kind == "hands_on_viz":
        return ()  # the picture is the code's output: nothing to restyle at random
    if is_meme(image):
        return remixing.KIND_DIMENSIONS["meme"]
    style = str((load_opening_state(image.spec) or {}).get("style") or "") if image.kind == "hero" else ""
    return remixing.dimensions_for(image.kind, style)


class ImageService:
    def __init__(
        self, *, engine: Engine, llm: LLM, settings: Settings, storage: Storage, sandbox: Callable[[], Sandbox | None] | None = None
    ) -> None:
        self.engine = engine
        self.llm = llm
        self.settings = settings
        self.storage = storage
        self.memes = MemeMaker(llm, settings)
        self.opening = OpeningRoom(llm, settings, self.memes)
        self.body = BodyRoom(llm, settings)
        # Runs the code above a hands-on image; None (or a sandbox that is off) means those images explain how to turn it on.
        self.handson = HandsOn(llm, settings, sandbox or (lambda: None))

    async def create(
        self,
        image_id: int,
        *,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        redraw: bool = False,
        rethink: bool = False,
        brand_kit: dict[str, Any] | None = None,
        instruction: str = "",
        concept: int | None = None,
        format: str | None = None,
        note: str = "",
        tweaks: dict[str, str] | None = None,
        improve: bool = True,
        remix: bool = True,
        usage: UsageSink | None = None,
    ) -> ProjectImage:
        """Design and render one image, then persist the result.

        A fresh image (or a rethink that ran out of ideas, or another ``format``) runs the whole room and keeps its
        finalists. A redraw critiques the current image first and adds a twist (``improve``; see ``images/remix.py``);
        ``tweaks`` pins parts of the twist and ``remix=False`` redraws plainly (Redraw all). ``concept`` draws that
        stored idea; ``note`` is the author's steer in their own words. With an ``instruction`` the current image is
        edited instead of redrawn.
        """
        with Session(self.engine) as session:
            image = session.get(ProjectImage, image_id)
            if image is None:
                raise KeyError(image_id)
        makers = {}
        for provider, task in MAKER_TASKS.items():
            lead = await lead_provider(self.llm, task)
            makers[provider] = MODEL_IDS.get(lead, self.settings.model)  # type: ignore[call-overload]
        _makers.set(makers)
        try:
            if image.kind == "hands_on_viz":
                # No pitches or judging: the picture is whatever the code above it draws.
                updates = await self._hands_on(image, persona=persona, markdown=markdown, instruction=instruction, usage=usage)
                if instruction.strip():
                    updates["edits"] = [*(image.edits or []), instruction.strip()][-MAX_EDIT_NOTES:]
            elif instruction.strip():
                updates = await self._edit(image, persona=persona, instruction=instruction, brand_kit=brand_kit, usage=usage)
                updates["edits"] = [*(image.edits or []), instruction.strip()][-MAX_EDIT_NOTES:]
            else:
                updates = await self._produce(
                    image,
                    persona=persona,
                    title=title,
                    markdown=markdown,
                    voice_profile=voice_profile,
                    redraw=redraw,
                    rethink=rethink,
                    brand_kit=brand_kit,
                    concept=concept,
                    format=format,
                    note=note.strip(),
                    tweaks=tweaks,
                    improve=improve,
                    remix=remix,
                    usage=usage,
                )
            if updates.get("file_name") and "finalists" not in updates and image.finalists:
                updates["finalists"] = self._refreshed_finalists(image, updates)
            updates["status"] = "ready"
            updates["error"] = None
        except (ImageProviderError, LLMError) as exc:
            updates = {"status": "error", "error": str(exc)}
        except Exception as exc:
            # One broken image must never take down the post (or leave a spinner running forever).
            log.exception("Image %s failed", image_id)
            tb = traceback.extract_tb(exc.__traceback__)
            where = f" at {Path(tb[-1].filename).name}:{tb[-1].lineno}" if tb else ""
            updates = {"status": "error", "error": f"Could not create this image ({exc!r}{where}). Click Redraw to try again."}
        saved = self._save(image_id, updates)
        if (
            saved.kind == "hands_on_viz"
            and saved.status == "ready"
            and saved.slot_id != MONTAGE_SLOT
            and saved.provider == handson.PROVIDER
        ):
            self._refresh_montage(saved.project_id, persona)
        return saved

    async def _hands_on(
        self, image: ProjectImage, *, persona: Persona, markdown: str, instruction: str, usage: UsageSink | None
    ) -> dict[str, Any]:
        """Run the code above the image (after changing it as the author asked) and keep the chart it draws."""
        if image.provider == handson.MONTAGE_PROVIDER or image.slot_id == MONTAGE_SLOT:
            return self._result(image, self._montage(image), persona)
        # The post as it is now (the caller's copy may predate another image's fix or the author's own edit of the code).
        with Session(self.engine) as session:
            project = session.get(Project, image.project_id)
        current = project.markdown if project is not None and project.markdown else markdown
        result = await self.handson.make(
            slot_id=image.slot_id, markdown=current, purpose=image.purpose or image.prompt, instruction=instruction, usage=usage
        )
        if result.changed:
            # The post must show the code that made the picture: its block is replaced, with an undo point.
            self._save_code(image.project_id, image.slot_id, result.code, f"Example code for {image.slot_id}: {result.note or 'fixed'}")
        self._sync_scenario(image.project_id, image.slot_id, result.code)
        updates = self._result(image, result.drawn, persona)
        updates["edits"] = list(image.edits or []) if instruction.strip() else []
        return updates

    def _montage(self, image: ProjectImage) -> Drawn:
        """Every chart of the experiment on one labeled sheet, drawn by code from the charts as they are now."""
        with Session(self.engine) as session:
            project = session.get(Project, image.project_id)
            rows = {r.slot_id: r for r in session.exec(select(ProjectImage).where(col(ProjectImage.project_id) == image.project_id))}
        experiment = load_experiment(project.experiment) if project is not None else None
        if experiment is None:
            raise ImageProviderError("This image belongs to an experiment, and this post has none.")
        tiles = []
        for scenario in experiment.scenarios:
            row = rows.get(scenario.slot_id) if scenario.slot_id else None
            path = self.storage.image_dir(image.project_id) / row.file_name if row is not None and row.file_name else None
            if row is not None and row.status == "ready" and path is not None and path.exists():
                tiles.append(Tile(scenario.label, f"{scenario.lines:,} lines \u00b7 {scenario.chars:,} characters", path.read_bytes()))
        if len(tiles) < MIN_TILES:
            raise ImageProviderError("The side-by-side image needs at least two charts from the experiment.")
        png = make_montage(tiles, f"One prompt, {len(tiles)} ways", self._post_scheme(image.project_id, ()))
        spec = json.dumps({"slots": [s.slot_id for s in experiment.scenarios if s.slot_id]}, separators=(",", ":"))
        return Drawn(
            png, WIDTH, HEIGHT, handson.MONTAGE_PROVIDER, spec,
            alt=f"The charts from {len(tiles)} libraries side by side",
            caption=f"The same prompt answered with {len(tiles)} different libraries, side by side",
        )  # fmt: skip

    def _sync_scenario(self, project_id: int, slot_id: str, code: str) -> None:
        """Keep the experiment's record of a scenario in step with the code that now draws its chart."""
        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            experiment = load_experiment(project.experiment) if project is not None else None
            scenario = next((s for s in experiment.scenarios if s.slot_id == slot_id), None) if experiment is not None else None
            if project is None or experiment is None or scenario is None or scenario.code.strip() == code.strip():
                return
            lines, chars = measure_code(code)
            scenarios = [
                s.model_copy(update={"code": code, "lines": lines, "chars": chars}) if s is scenario else s for s in experiment.scenarios
            ]
            project.experiment = experiment.model_copy(update={"scenarios": scenarios}).model_dump()
            session.add(project)
            session.commit()

    def _refresh_montage(self, project_id: int, persona: Persona) -> None:
        """A chart changed: the side-by-side image is drawn again from the charts as they are now (never fails the chart)."""
        with Session(self.engine) as session:
            montage = session.exec(
                select(ProjectImage).where(col(ProjectImage.project_id) == project_id, col(ProjectImage.slot_id) == MONTAGE_SLOT)
            ).first()
        if montage is None or montage.id is None:
            return
        try:
            self._save(montage.id, {**self._result(montage, self._montage(montage), persona), "status": "ready", "error": None})
        except ImageProviderError as exc:
            log.info("Side-by-side image not refreshed: %s", exc)

    def save_experiment_image(self, image_id: int, png: bytes, scenario: Scenario, persona: Persona, model: str) -> ProjectImage:
        """Store the chart a scenario's code really drew: the same record a hands-on image makes, so Rerun and Edit code just work."""
        image = self._get(image_id)
        png, width, height = handson.png_size(png)
        library = handson.library_of(scenario.code)
        spec = json.dumps(
            {
                "code_hash": handson.code_hash(scenario.code),
                "library": library,
                "lines": scenario.lines,
                "chars": scenario.chars,
                "versions": {},
            },
            separators=(",", ":"),
        )
        return self._save(
            image_id,
            {
                "file_name": self._write(image.project_id, image.slot_id, png),
                "provider": handson.PROVIDER,
                "spec": spec,
                "alt": image.purpose or f"The chart the {scenario.label} code draws",
                "caption": handson.caption_for(library, scenario.lines, scenario.chars),
                "credit": credit_line(persona, handson.PROVIDER, model),
                "width": width,
                "height": height,
                "seed": None,
                "edits": [],
                "status": "ready",
                "error": None,
            },
        )

    def _save_code(self, project_id: int, slot_id: str, code: str, label: str) -> None:
        """Swap the code block above ``slot_id`` for ``code`` in the post as it is now (other images may be fixing theirs too)."""
        from inferno_ghostwriter.writer.revisions import push_revision  # the writer package imports this one

        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            block = code_before(project.markdown, slot_id) if project is not None else None
            if project is None or block is None or block.code.strip() == code.strip():
                return
            push_revision(project, label, "image")
            project.markdown = replace_code(project.markdown, block, code)
            project.updated_at = datetime.now(UTC)
            session.add(project)
            session.commit()

    def fail_pending(self, project_id: int | None = None, reason: str = STALE_PENDING) -> int:
        """Mark images still waiting to be drawn as errors (their job is gone); returns how many."""
        with Session(self.engine) as session:
            query = select(ProjectImage).where(ProjectImage.status == "pending")
            if project_id is not None:
                query = query.where(col(ProjectImage.project_id) == project_id)
            rows = list(session.exec(query))
            for row in rows:
                row.status = "error"
                row.error = reason
                session.add(row)
            session.commit()
            return len(rows)

    def save_upload(self, image_id: int, png: bytes, width: int, height: int, persona: Persona) -> ProjectImage:
        image = self._get(image_id)
        file_name = self._write(image.project_id, image.slot_id, png)
        return self._save(
            image_id,
            {
                "file_name": file_name,
                "provider": "upload",
                "edits": [],
                "seed": None,
                "width": width,
                "height": height,
                "credit": credit_line(persona, "upload"),
                "status": "ready",
                "error": None,
            },
        )

    async def set_words(
        self, image_id: int, words: dict[str, str], *, persona: Persona, brand_kit: dict[str, Any] | None = None
    ) -> ProjectImage:
        """Retype an image's words (a meme, or a code-drawn opening image) and draw it again without asking Claude (a
        meme GPT painted is painted again with the new words).

        Raises ImageProviderError when the image has no words to retype or cannot be drawn."""
        image = self._get(image_id)
        art = self._art_direction(brand_kit, persona, "")
        if is_meme(image):
            meme = await self.memes.reword(meme_spec(image), words, art, current_png=self._current_png(image))
            drawn = self.opening.with_meme(image.spec, meme) if image.kind == "hero" else meme
        elif image.kind == "hero":
            drawn = self.opening.reword(image.spec, words, art)
        else:
            raise ImageProviderError("This image has no words to retype; use Edit instead.")
        return self._save(image_id, {**self._result(image, drawn, persona), "status": "ready", "error": None})

    def pick(self, image_id: int, index: int) -> ProjectImage:
        """Show another finalist of the last fresh run. No model call: each finalist has its own file and source."""
        image = self._get(image_id)
        finalists = list(image.finalists or [])
        if not 0 <= index < len(finalists):
            raise IndexError(index)
        chosen = finalists[index]
        fields: dict[str, Any] = {
            k: chosen[k] for k in ("file_name", "provider", "spec", "alt", "caption", "width", "height") if k in chosen
        }
        if chosen.get("ideas") is not None:
            fields["ideas"] = chosen["ideas"]
        return self._save(image_id, {**fields, "edits": [], "status": "ready", "error": None})

    def revert(self, image_id: int, index: int) -> ProjectImage:
        with Session(self.engine) as session:
            image = session.get(ProjectImage, image_id)
            if image is None:
                raise KeyError(image_id)
            if not 0 <= index < len(image.history):
                raise IndexError(index)
            entry = image.history[index]
        fields: dict[str, Any] = {k: entry[k] for k in HISTORY_FIELDS if k in entry}
        return self._save(image_id, {**fields, "status": "ready", "error": None}, record=False)

    def opening_may_be_meme(self, project_id: int, persona: Persona) -> bool:
        """Whether the opening image could be a meme (then the closing meme must wait for it: meme sandwich)."""
        from inferno_ghostwriter.images.opening.styles import may_be_meme

        _, dials, brief, _ = self._post_info(project_id)
        resolved = _resolved(dials, persona, brief)
        if resolved is None:  # dials saved by an older version: keep the safe order
            return True
        return may_be_meme(resolved.opening_style, resolved.opening_eligible)

    def set_reference(self, image_id: int, png: bytes | None) -> ProjectImage:
        """Attach (or with None, remove) a style reference for this image's next draws."""
        image = self._get(image_id)
        name = ""
        if png is not None:
            name = f"{image.slot_id}-reference-{uuid4().hex[:8]}.png"
            (self.storage.image_dir(image.project_id) / name).write_bytes(png)
        return self._save(image_id, {"reference": name}, record=False)

    # -- internals -------------------------------------------------------------

    def _reference(self, image: ProjectImage) -> bytes | None:
        if not image.reference:
            return None
        path = self.storage.image_dir(image.project_id) / image.reference
        return thumbnail_png(path.read_bytes()) if path.exists() else None

    def _get(self, image_id: int) -> ProjectImage:
        with Session(self.engine) as session:
            image = session.get(ProjectImage, image_id)
            if image is None:
                raise KeyError(image_id)
            return image

    async def _produce(
        self,
        image: ProjectImage,
        *,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        redraw: bool,
        rethink: bool,
        brand_kit: dict[str, Any] | None,
        concept: int | None,
        format: str | None,
        note: str,
        tweaks: dict[str, str] | None,
        improve: bool,
        remix: bool,
        usage: UsageSink | None,
    ) -> dict[str, Any]:
        art = replace(self._art_direction(brand_kit, persona, voice_profile), note=note, reference=self._reference(image))
        remixed: dict[str, Any] | None = None
        picked = concept is not None or format is not None
        # A redraw or remix builds on the author's edits; picking another idea or rethinking starts over.
        keep_edits = (
            bool(image.edits) and bool(image.spec) and not rethink and not picked and image.provider not in ("upload", "placeholder")
        )
        if keep_edits:
            art = replace(art, edits=tuple(image.edits))
        if remix and (redraw or rethink or tweaks):
            art, remixed = await self._remix(
                image, art, title=title, markdown=markdown, brand_kit=brand_kit, pins=tweaks, brainstorm=improve and not picked, usage=usage
            )
        # Each new version rolls again for GPT painting, so a redraw can switch between painting and drawing.
        with raster.paint_round(len(image.history or [])):
            drawn, extra = await self._draw(
                image,
                art,
                persona=persona,
                title=title,
                markdown=markdown,
                voice_profile=voice_profile,
                redraw=redraw,
                rethink=rethink,
                concept=concept,
                format=format,
                note=note,
                usage=usage,
            )
        updates = {**self._result(image, drawn, persona), **extra}
        if drawn.finalists:
            updates["finalists"] = [self._finalist(image, f, extra.get("ideas")) for f in drawn.finalists]
            # The shown image is the first finalist: point it at the same file.
            updates["file_name"] = updates["finalists"][0]["file_name"]
        if remixed is not None:
            updates["remix"] = remixed
        if image.edits and not keep_edits:
            updates["edits"] = []
        return updates

    async def _remix(
        self,
        image: ProjectImage,
        art: ArtDirection,
        *,
        title: str,
        markdown: str,
        brand_kit: dict[str, Any] | None,
        pins: dict[str, str] | None,
        brainstorm: bool,
        usage: UsageSink | None,
    ) -> tuple[ArtDirection, dict[str, Any]]:
        """Critique the current image and choose this redraw's twist; returns the art direction carrying both."""
        previous = dict(image.remix or {})
        kind = image.kind
        chosen = remixing.choose_tweaks(
            remix_dimensions(image),
            recent=[str(e) for e in previous.get("recent", [])],
            pinned=remixing.pins_from(pins),
            keep_palette=bool(brand_palette(brand_kit)),
            house_only=kind in ("hero", "meme"),
        )
        plan = None
        if brainstorm:
            png = None
            if image.file_name:
                path = self.storage.image_dir(image.project_id) / image.file_name
                png = path.read_bytes() if path.exists() else None
            plan = await remixing.brainstorm(
                self.llm,
                self.settings,
                kind=kind,
                title=title,
                caption=image.caption,
                design=image.spec,
                png=png,
                context=image_context(markdown, image.slot_id, 900, 500),
                previous=previous,
                usage=usage,
            )
        return remixing.apply_to_art(art, plan, chosen), remixing.to_remix(plan, chosen, previous)

    async def _draw(
        self,
        image: ProjectImage,
        art: ArtDirection,
        *,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        redraw: bool,
        rethink: bool,
        concept: int | None,
        format: str | None,
        note: str,
        usage: UsageSink | None,
    ) -> tuple[Drawn, dict[str, Any]]:
        """Route to the image's room; returns the drawing and any extra fields to store."""
        kind = image.kind
        seed = random.randrange(1 << 30)
        # "Pitch new ideas" with a steer starts the room over instead of moving to the next stored idea.
        restart = rethink and bool(note)
        spec = "" if restart else image.spec
        meme_format = format if format is not None and get_format(format) else None
        if kind == "hero":
            opening_style = format if format in OPENING_STYLES else None
            if format is not None and opening_style is None and meme_format is None:
                raise ImageProviderError(f"Unknown opening style or meme format: {format}")
            context = self._opening_context(image, persona, title, markdown, voice_profile, note=note, seed=seed)
            result = await self.opening.make(
                spec if load_opening_state(spec) else "",
                context,
                art,
                redraw=redraw,
                rethink=rethink,
                style=opening_style,
                concept_index=concept,
                meme_format=meme_format,
                usage=usage,
            )
            return result, {}
        if kind == "meme":
            if format is not None and meme_format is None:
                raise ImageProviderError(f"Unknown meme format: {format}")
            post = self._meme_context(image, persona, title, markdown, voice_profile, note=note, seed=seed)
            meme = await self.memes.make(
                spec, post, art, redraw=redraw, rethink=rethink, meme_format=meme_format, concept_index=concept, usage=usage
            )
            return meme, {}
        return await self._draw_body(
            image, art, persona=persona, title=title, markdown=markdown, voice_profile=voice_profile,
            redraw=redraw, rethink=rethink, concept=concept, format=format, note=note, seed=seed, usage=usage,
        )  # fmt: skip

    async def _draw_body(
        self,
        image: ProjectImage,
        art: ArtDirection,
        *,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        redraw: bool,
        rethink: bool,
        concept: int | None,
        format: str | None,
        note: str,
        seed: int,
        usage: UsageSink | None,
    ) -> tuple[Drawn, dict[str, Any]]:
        ctx = self._body_context(image, art, title=title, markdown=markdown, voice_profile=voice_profile, note=note, seed=seed)
        ideas = {} if rethink and note else dict(image.ideas or {})
        stored = ideas if ideas.get("concepts") and ideas.get("brief") == ctx.brief else {}
        concepts: list[dict[str, Any]] = list(stored.get("concepts") or [])
        variation = self._body_variation(image, art, redraw=redraw, rethink=rethink)

        if concept is not None:
            if not 0 <= concept < len(concepts):
                raise ImageProviderError("That idea is no longer available. Click Ideas for fresh pitches.")
            stored["chosen"], stored["tried"] = concept, sorted({*stored.get("tried", []), concept})
            drawn = await self.body.draw(concepts[concept], ctx, "", usage)
            return drawn, {"ideas": stored}
        if format is not None:
            # Another way to draw it (a diagram as a chart): one idea in that kind, from the chosen idea or the brief.
            base = dict(concepts[stored["chosen"]]) if isinstance(stored.get("chosen"), int) else {"concept": ctx.brief}
            drawn = await self.body.draw({**base, "kind": format}, ctx, variation, usage)
            return drawn, {}
        fresh_room = self.settings.image_body_candidates > 1 and not image.builds_on
        if redraw and not rethink and image.provider == raster.PROVIDER:
            # A painting is painted again from its prompt, with the redraw's critique and twist; Claude draws it
            # instead only when painting is unavailable.
            try:
                return await self.body.repaint(image.spec, variation, None, usage), {}
            except ImageProviderError:
                pass
        if redraw and not rethink and stored and isinstance(stored.get("chosen"), int):
            # Redraw the idea on show (with the redraw's critique and twist).
            return await self.body.draw(concepts[stored["chosen"]], ctx, variation, usage), {}
        if rethink and stored:
            untried = [i for i in range(len(concepts)) if i not in set(stored.get("tried", []))]
            if untried:
                i = untried[0]
                stored["chosen"], stored["tried"] = i, sorted({*stored.get("tried", []), i})
                return await self.body.draw(concepts[i], ctx, variation, usage), {"ideas": stored}
        if not fresh_room:
            # An image that builds on another (or a one-candidate setting) is drawn straight from its brief.
            return await self.body.draw(None, ctx, variation, usage), {}
        exclude = [str(c.get("concept", "")) for c in concepts] if rethink else []
        pitched = await self.body.pitch(ctx, exclude, usage)
        drawn, index = await self.body.run(pitched, ctx, usage)
        pitched["chosen"] = index
        return drawn, {"ideas": pitched}

    def _body_variation(self, image: ProjectImage, art: ArtDirection, *, redraw: bool, rethink: bool) -> str:
        kind = image.kind
        variation = ""
        if rethink:
            variation = (
                "This is a rethink: throw out the previous concept and design a completely different idea that serves the same purpose "
                f"(previous caption: {image.caption!r})."
            )
        elif redraw:
            variation = (
                "This is a redraw: keep the same idea but give it a clearly different composition, metaphor or visual treatment "
                f"(previous caption: {image.caption!r})."
            )
        if planned := remixing.variation_for(art, remixing.dimensions_for(kind), kind=kind):
            rethought = "\nThrow out the previous concept and design a completely different idea that serves the same purpose."
            variation = planned + (rethought if rethink else "")
        if art.edits and image.spec and not rethink:
            variation += remixing.edit_note(art.edits, image.spec[:MAX_EDIT_SPEC])
        return variation

    def _body_context(
        self, image: ProjectImage, art: ArtDirection, *, title: str, markdown: str, voice_profile: str, note: str, seed: int
    ) -> BodyContext:
        return BodyContext(
            kind=image.kind,
            slot_id=image.slot_id,
            title=title,
            purpose=image.purpose,
            brief=image.prompt or image.purpose,
            visual_style=art.visual_style,
            brand=art.brand,
            image_guidance=art.image_guidance or image_guidance(voice_profile),
            siblings=self._siblings(image),
            builds_on=self._builds_on(image),
            context=image_context(markdown, image.slot_id),
            markdown=markdown,
            palette=art.palette,
            scheme=self._post_scheme(image.project_id, art.palette),
            note=note,
            seed=seed,
            reference=art.reference,
        )

    def _post_scheme(self, project_id: int, palette: tuple[str, ...]) -> Scheme:
        """One color ramp for every image of a post: the brand palette, else the opening image's ramp on white."""
        if len(palette) >= 3 and house_ramp(palette) is None:
            return brand_scheme(palette)
        with Session(self.engine) as session:
            hero = session.exec(
                select(ProjectImage).where(col(ProjectImage.project_id) == project_id, col(ProjectImage.kind) == "hero")
            ).first()
        found = from_id(str((load_opening_state(hero.spec) or {}).get("scheme") or "")) if hero else None
        return scheme(found.ramp_id if found is not None and found.ramp_id != "brand" else "inferno", "white")

    async def _edit(
        self,
        image: ProjectImage,
        *,
        persona: Persona,
        instruction: str,
        brand_kit: dict[str, Any] | None,
        usage: UsageSink | None,
    ) -> dict[str, Any]:
        """Change the current design as the author asks, keeping everything else about it."""
        if image.provider in ("upload", "placeholder") or not image.spec:
            raise ImageProviderError("Only images Claude drew can be edited by instruction. Redraw or upload this one instead.")
        if image.provider == raster.PROVIDER and raster.load(image.spec):
            current = self._current_png(image)
            return self._result(image, await self.body.repaint(image.spec, instruction, current, usage), persona)
        art = self._art_direction(brand_kit, persona, "")
        if image.kind == "meme" and load_state(image.spec):
            meme = await self.memes.edit(image.spec, instruction, art, usage=usage, current_png=self._current_png(image))
            return self._result(image, meme, persona)
        if image.kind == "hero" and load_opening_state(image.spec):
            with Session(self.engine) as session:
                project = session.get(Project, image.project_id)
                title, markdown = (project.title, project.markdown) if project else ("", "")
            context = self._opening_context(image, persona, title, markdown, "")
            current = self._current_png(image)
            return self._result(
                image, await self.opening.edit(image.spec, instruction, context, art, usage=usage, current=current), persona
            )
        _, brand = brand_guidance(brand_kit, persona)
        prompt = render(
            "image_edit",
            kind=image.kind,
            slot_id=image.slot_id,
            instruction=instruction.strip(),
            caption=image.caption,
            alt=image.alt,
            spec=image.spec,
            brand=brand,
        )
        if image.kind == "meme":  # an older meme: plain SVG with captions on top
            meme, _ = await self._legacy_meme(prompt, usage)
            return self._result(image, meme, persona)
        if image.provider == "claude-diagram":
            scheme_ = self._post_scheme(image.project_id, brand_palette(brand_kit))
            return self._result(image, await self.body.edit_diagram(image.spec, instruction, scheme_, usage), persona)
        kind = "chart" if image.provider == "vega-lite" else image.kind
        drawn = await self.body.design(kind, prompt, task=f"{image.kind} image edit", palette=brand_palette(brand_kit), usage=usage)
        return self._result(image, drawn, persona)

    def _current_png(self, image: ProjectImage) -> bytes | None:
        """The picture on show, as stored (None when there is none)."""
        path = self.storage.image_dir(image.project_id) / image.file_name if image.file_name else None
        return path.read_bytes() if path is not None and path.exists() else None

    async def _legacy_meme(self, prompt: str, usage: UsageSink | None) -> tuple[Drawn, SvgMemeSpec]:
        meme = await self.llm.structured(
            task="meme image edit", system=self.body.system, prompt=prompt, schema=SvgMemeSpec,
            effort=self.settings.effort_images, max_tokens=24000, usage=usage,
        )  # fmt: skip
        png, w, h = svg_to_png(meme.svg, width=1080)
        png = add_meme_text(png, meme.top_text, meme.bottom_text)
        spec = json.dumps({"svg": meme.svg, "top": meme.top_text, "bottom": meme.bottom_text})
        return Drawn(png, w, h, "claude-svg", spec, meme.alt, meme.caption), meme

    def _post_info(self, project_id: int) -> tuple[dict[str, Any], dict[str, Any], str, list[str]]:
        """The project's plan, dials, brief and pinned titles."""
        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            if project is None:
                return {}, {}, "", []
            return dict(project.plan or {}), dict(project.dials or {}), project.prompt, list(project.pinned_titles or [])

    def _meme_context(
        self,
        image: ProjectImage,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        *,
        position: str = "closing",
        note: str = "",
        seed: int | None = None,
    ) -> MemeContext:
        plan, dials, brief, _ = self._post_info(image.project_id)
        humor = dials.get("humor")
        return MemeContext(
            title=title,
            markdown=markdown,
            voice_profile=voice_profile,
            brief=(image.prompt or image.purpose) if position == "closing" else "",
            joke=str(plan.get("joke") or "") if position == "closing" else "",
            callbacks=plan_callbacks(plan),
            humor=int(humor) if humor is not None else persona.default_humor,
            recent_formats=self._recent_meme_formats(persona, image.project_id),
            formula=_formula_note(dials, persona, brief),
            position=position,
            opening=self._opening_meme_note(image.project_id) if position == "closing" else "",
            recent_schemes=self._recent_schemes(persona, image.project_id),
            note=note,
            seed=seed,
        )

    def _opening_context(
        self,
        image: ProjectImage,
        persona: Persona,
        title: str,
        markdown: str,
        voice_profile: str,
        *,
        note: str = "",
        seed: int | None = None,
    ) -> OpeningContext:
        plan, dials, brief, pinned = self._post_info(image.project_id)
        resolved = _resolved(dials, persona, brief)
        humor = resolved.humor if resolved is not None else persona.default_humor
        formula = ""
        if resolved is not None and (resolved.article_type != "auto" or resolved.opener != "auto"):
            formula = f"The post's formula: {resolved.formula_label}."
        dial_note = resolved.opening_note if resolved is not None else ""
        return OpeningContext(
            title=title,
            markdown=markdown,
            voice_profile=voice_profile,
            brief=image.prompt or image.purpose,
            post_brief=brief,
            hook=str(plan.get("hook") or ""),
            titles=tuple(t for t in [*pinned, *(plan.get("title_options") or [])] if t and t != title)[:4],
            humor=humor,
            style=resolved.opening_style if resolved is not None else "auto",
            note=" ".join(n for n in (dial_note, note) if n),
            suggested=tuple(resolved.opening_suggested) if resolved is not None else (),
            eligible=tuple(resolved.opening_eligible) if resolved is not None else (),
            formula=formula,
            recent_styles=self._recent_opening_styles(persona, image.project_id),
            meme_context=self._meme_context(image, persona, title, markdown, voice_profile, position="opening", note=note, seed=seed),
            recent_schemes=self._recent_schemes(persona, image.project_id),
            seed=seed,
        )

    def _opening_meme_note(self, project_id: int) -> str:
        """The post's opening meme in one line (format and premise), for the closing meme of a meme sandwich."""
        with Session(self.engine) as session:
            hero = session.exec(
                select(ProjectImage).where(col(ProjectImage.project_id) == project_id, col(ProjectImage.kind) == "hero")
            ).first()
        state = load_state(opening_meme_spec(hero.spec) or "") if hero else None
        if not state:
            return ""
        fmt = get_format(str(state.get("format", "")))
        concepts, chosen = state.get("concepts") or [], state.get("chosen")
        premise = concepts[chosen].get("premise", "") if isinstance(chosen, int) and 0 <= chosen < len(concepts) else ""
        words = " / ".join(str(t.get("text", "")) for t in (state.get("build") or {}).get("texts") or [] if t.get("text"))
        return f"a {fmt.name if fmt else 'meme'} meme: {premise} (words: {words})".strip()

    def _recent_schemes(self, persona: Persona, project_id: int, limit: int = 4) -> tuple[str, ...]:
        """The color schemes ("ramp:surface") of this author's latest opening images and memes, newest first."""
        with Session(self.engine) as session:
            specs = session.exec(
                select(ProjectImage.spec)
                .join(Project, col(Project.id) == col(ProjectImage.project_id))
                .where(col(Project.persona_id) == persona.id, col(ProjectImage.kind).in_(("meme", "hero")))
                .order_by(col(Project.updated_at).desc())
                .limit(limit * 3)
            ).all()
        schemes: list[str] = []
        for spec in specs:
            try:
                state = json.loads(spec) if spec else {}
            except json.JSONDecodeError:
                continue
            found = str(state.get("scheme") or "") if isinstance(state, dict) else ""
            if ":" in found:
                schemes.append(found)
        return tuple(schemes[:limit])

    def _recent_opening_styles(self, persona: Persona, project_id: int, limit: int = 3) -> tuple[str, ...]:
        """The styles of this author's latest opening images in other posts, newest first."""
        with Session(self.engine) as session:
            specs = session.exec(
                select(ProjectImage.spec)
                .join(Project, col(Project.id) == col(ProjectImage.project_id))
                .where(col(Project.persona_id) == persona.id, col(ProjectImage.kind) == "hero", col(Project.id) != project_id)
                .order_by(col(Project.updated_at).desc())
                .limit(limit * 2)
            ).all()
        styles: list[str] = []
        for spec in specs:
            style = str((load_opening_state(spec) or {}).get("style") or "")
            if style and style not in styles:
                styles.append(style)
        return tuple(styles[:limit])

    def _recent_meme_formats(self, persona: Persona, project_id: int, limit: int = 3) -> tuple[str, ...]:
        """The formats of this author's latest memes in other posts, newest first."""
        with Session(self.engine) as session:
            specs = session.exec(
                select(ProjectImage.spec)
                .join(Project, col(Project.id) == col(ProjectImage.project_id))
                .where(col(Project.persona_id) == persona.id, col(ProjectImage.kind) == "meme", col(Project.id) != project_id)
                .order_by(col(Project.updated_at).desc())
                .limit(limit * 2)
            ).all()
        names: list[str] = []
        for spec in specs:
            fmt = get_format(str((load_state(spec) or {}).get("format", "")))
            if fmt and fmt.name not in names:
                names.append(fmt.name)
        return tuple(names[:limit])

    @staticmethod
    def _art_direction(brand_kit: dict[str, Any] | None, persona: Persona, voice_profile: str) -> ArtDirection:
        visual_style, brand = brand_guidance(brand_kit, persona)
        return ArtDirection(
            visual_style=visual_style, brand=brand, image_guidance=image_guidance(voice_profile), palette=brand_palette(brand_kit)
        )

    def _siblings(self, image: ProjectImage) -> str:
        """The post's other images, one per line, so each drawing knows what the rest of the set shows."""
        with Session(self.engine) as session:
            rows = session.exec(
                select(ProjectImage).where(ProjectImage.project_id == image.project_id).order_by(col(ProjectImage.position))
            ).all()
        lines = [f"- {row.kind} `{row.slot_id}`: {row.purpose or row.prompt}" for row in rows if row.id != image.id]
        return "\n".join(lines) or "(none)"

    def _builds_on(self, image: ProjectImage) -> str:
        """The instruction (and source) for an image that extends an earlier one, or "" when it stands alone."""
        if not image.builds_on:
            return ""
        with Session(self.engine) as session:
            base = session.exec(
                select(ProjectImage).where(col(ProjectImage.project_id) == image.project_id, col(ProjectImage.slot_id) == image.builds_on)
            ).first()
        if base is None or not base.spec or base.provider in ("upload", "placeholder") or base.position >= image.position:
            return ""
        reuse = {
            "chart": (
                "Copy the base chart's `data.values` rows exactly (same rows, same numbers, same field names), its scales, "
                "axis domains, colors, fonts and size, then add what this image adds (another field to split by, an extra layer "
                "or annotation, a fitted line per group). Do not invent a new dataset or reshuffle the old one: the reader must "
                "see the same points again."
            ),
        }.get(
            image.kind,
            "Reuse its palette, shapes, labels and layout where they carry over, keeping every element the reader already "
            "met in the same place and style, then add what this image adds. Do not restyle what is unchanged.",
        )
        return (
            f"\nThis image BUILDS ON the earlier image `{base.slot_id}` ({base.caption or base.purpose}): the reader has just seen "
            f"it and must feel this is the same picture taken further. {reuse}\n"
            f"The base image's source:\n<base>\n{base.spec[:12000]}\n</base>\n"
        )

    def _result(self, image: ProjectImage, drawn: Drawn, persona: Persona) -> dict[str, Any]:
        return {
            "file_name": self._write(image.project_id, image.slot_id, drawn.png),
            "provider": drawn.provider,
            "width": drawn.width,
            "height": drawn.height,
            "credit": credit_line(persona, drawn.provider, (_makers.get() or {}).get(drawn.provider, self.settings.model)),
            "seed": None,
            "spec": drawn.spec,
            "alt": drawn.alt,
            "caption": drawn.caption,
        }

    @staticmethod
    def _refreshed_finalists(image: ProjectImage, updates: dict[str, Any]) -> list[dict[str, Any]]:
        """The finalist strip after a redraw, remix, edit or picked idea made one new picture: it takes the place of
        the finalist it came from and the other finalists stay as alternatives. When the image on show was no
        finalist (an earlier version or an upload) the strip is stale and goes; Versions keeps every picture."""
        finalists = list(image.finalists or [])
        at = next((i for i, f in enumerate(finalists) if f.get("file_name") and f.get("file_name") == image.file_name), None)
        if at is None:
            return []
        entry: dict[str, Any] = {
            k: updates[k] for k in ("file_name", "provider", "spec", "alt", "caption", "width", "height") if k in updates
        }
        if updates.get("ideas") is not None:
            entry["ideas"] = updates["ideas"]
        finalists[at] = {**entry, "label": "Your latest version", "score": None, "reads_as": ""}
        return finalists

    def _finalist(self, image: ProjectImage, drawn: Drawn, ideas: dict[str, Any] | None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "file_name": self._write(image.project_id, image.slot_id, drawn.png),
            "provider": drawn.provider,
            "spec": drawn.spec,
            "alt": drawn.alt,
            "caption": drawn.caption,
            "width": drawn.width,
            "height": drawn.height,
            "label": drawn.label,
            "score": drawn.score,
            "reads_as": drawn.reads_as,
        }
        if ideas is not None:
            entry["ideas"] = ideas
        return entry

    def _write(self, project_id: int, slot_id: str, png: bytes) -> str:
        name = f"{slot_id}-{uuid4().hex[:8]}.png"
        (self.storage.image_dir(project_id) / name).write_bytes(png)
        return name

    def _save(self, image_id: int, updates: dict[str, Any], *, record: bool = True) -> ProjectImage:
        with Session(self.engine) as session:
            image = session.get(ProjectImage, image_id)
            if image is None:
                raise KeyError(image_id)
            for key, value in updates.items():
                setattr(image, key, value)
            if record and updates.get("file_name"):
                entry = {k: getattr(image, k) for k in HISTORY_FIELDS}
                entry["created_at"] = datetime.now(UTC).isoformat()
                image.history = [*image.history, entry]
            session.add(image)
            session.commit()
            session.refresh(image)
            return image

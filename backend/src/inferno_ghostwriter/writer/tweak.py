"""Tweak a finished post from the author's feedback: surgical edits, not a rewrite.

Claude returns only find/replace edits (and, when asked, new briefs for specific images),
so the untouched text and images stay byte-for-byte the same, output tokens stay small,
and the cached voice-profile + exemplar prefix is shared with generation.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from inferno_ghostwriter.authenticity import analyze, author_profile
from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Persona, Project, ProjectImage, Sample, utcnow
from inferno_ghostwriter.experiments.compose import broken_by
from inferno_ghostwriter.experiments.models import load as load_experiment
from inferno_ghostwriter.images import PLACEHOLDER_RE, ImageService
from inferno_ghostwriter.jobs import JobContext
from inferno_ghostwriter.llm import LLM
from inferno_ghostwriter.prompts import render
from inferno_ghostwriter.voice import current_voice_profile, format_exemplars, select_exemplars
from inferno_ghostwriter.voice.lessons import format_lessons, record_feedback
from inferno_ghostwriter.voice.playbook import format_playbook
from inferno_ghostwriter.writer.dials import Dials, resolve
from inferno_ghostwriter.writer.pipeline import (
    WriterError,
    ensure_placeholders,
    measure,
    prompt_settings,
    split_title,
    writer_system,
)
from inferno_ghostwriter.writer.revisions import push_revision
from inferno_ghostwriter.writer.schemas import ImageSlot, PostEdits, TextEdit

MAX_NEW_IMAGES_TOTAL = 22  # same cap as add_image.MAX_IMAGES

# Jobs that change a post's text; only one runs per project at a time.
TEXT_JOBS = (
    "generate_post",
    "tweak_post",
    "enrich_post",
    "add_reference_url",
    "redraw_reference",
    "ab_generate",
    "ab_decide",
    "add_image",
    "interview",
    "run_experiment",
)


def locate(markdown: str, text: str) -> tuple[int, int] | None:
    """Where ``text`` first appears in the post: exactly, or word by word when the model reflowed its whitespace."""
    if not text.strip():
        return None
    start = markdown.find(text)
    if start >= 0:
        return start, start + len(text)
    pattern = r"\s+".join(re.escape(word) for word in text.split())
    match = re.search(pattern, markdown)
    return match.span() if match else None


def apply_edits(markdown: str, edits: list[TextEdit]) -> tuple[str, int, list[str]]:
    """Apply find/replace edits in order; returns (markdown, applied count, edits that could not be placed)."""
    applied = 0
    skipped: list[str] = []
    for edit in edits:
        if not edit.find.strip() or edit.find == edit.replace:
            continue
        span = locate(markdown, edit.find)
        if span is None:
            skipped.append(edit.find[:120])
            continue
        start, end = span
        markdown = markdown[:start] + edit.replace + markdown[end:]
        applied += 1
    return markdown, applied, skipped


def _keep_experiment_intact(project: Project, edits: list[TextEdit]) -> tuple[list[TextEdit], list[str]]:
    """In a library experiment the prompts and code are printed word for word: an edit that would change one is held back."""
    experiment = load_experiment(project.experiment)
    if experiment is None:
        return edits, []
    kept: list[TextEdit] = []
    held: list[str] = []
    current = project.markdown
    for edit in edits:
        trial, applied, _ = apply_edits(current, [edit])
        if applied and broken_by(current, trial, experiment):
            held.append(edit.find[:120])
            continue
        kept.append(edit)
        current = trial
    return kept, held


def plan_slots(plan: dict[str, Any] | None) -> list[ImageSlot]:
    return [ImageSlot.model_validate(slot) for slot in (plan or {}).get("image_slots", [])]


def finish_text(markdown: str, plan: dict[str, Any] | None) -> str:
    """Put back any image placeholder an edit dropped, and drop captions next to them."""
    slots = plan_slots(plan)
    return ensure_placeholders(markdown, slots) if slots else markdown


def _image_list(images: list[ProjectImage]) -> str:
    lines = [
        f"- `{{{{image:{img.slot_id}}}}}` ({img.kind}): {img.purpose or img.prompt}"
        + (f" Current caption: {img.caption!r}." if img.caption else "")
        for img in images
    ]
    return "\n".join(lines) or "(none)"


def _other_post(markdown: str) -> str:
    if not markdown.strip():
        return ""
    return (
        "The author compared this post with another version of it and may ask for parts of that version. Take from it "
        "only what the feedback asks for, never its image placeholders:\n\n<other_version>\n" + markdown.strip() + "\n</other_version>\n"
    )


async def tweak_post(
    *,
    engine: Engine,
    llm: LLM,
    settings: Settings,
    images: ImageService,
    project_id: int,
    feedback: str,
    ctx: JobContext,
    other_post: str = "",
    learn: bool = True,
) -> dict[str, Any]:
    """``other_post`` is the losing post of an A/B test, for feedback that borrows from it; such feedback is about
    that one comparison, so it is not kept as a lesson (``learn=False``)."""
    with Session(engine, expire_on_commit=False) as session:
        project = session.get(Project, project_id)
        if project is None:
            raise WriterError("Project not found.")
        persona = session.get(Persona, project.persona_id)
        voice_profile = current_voice_profile(session, project.persona_id)
        samples = list(session.exec(select(Sample).where(Sample.persona_id == project.persona_id)))
        image_rows = list(
            session.exec(select(ProjectImage).where(ProjectImage.project_id == project_id).order_by(col(ProjectImage.position)))
        )
    if persona is None:
        raise WriterError("The project's persona no longer exists.")
    if voice_profile is None:
        raise WriterError("This persona has no voice profile yet.")
    if not project.markdown:
        raise WriterError("Generate the post before tweaking it.")

    dials = resolve(
        Dials(**(project.dials or {})),
        persona,
        project.prompt,
        default_revisions=settings.revision_passes,
        code_runs=settings.allow_code_execution,
    )
    # Same system blocks as generation, so the voice profile and exemplars come from the prompt cache.
    system = writer_system(
        voice_profile.markdown,
        format_exemplars(select_exemplars(project.prompt, samples)),
        format_lessons(persona.edit_lessons),
        format_playbook(persona.playbook),
    )

    await ctx.progress(0.1, "Working your feedback into the post")
    result = await llm.structured(
        task="post tweak",
        system=system,
        prompt=render(
            "tweak",
            feedback=feedback.strip(),
            markdown=project.markdown,
            images=_image_list(image_rows),
            room_for_images=max(0, MAX_NEW_IMAGES_TOTAL - len(image_rows)),
            other_post=_other_post(other_post),
            **prompt_settings(dials),
        ),
        schema=PostEdits,
        effort=settings.effort_critique,
        max_tokens=32000,
        usage=ctx.add_usage,
    )

    edits, held_back = _keep_experiment_intact(project, result.edits)
    markdown, applied, skipped = apply_edits(project.markdown, edits)
    skipped = [*skipped, *held_back]
    by_slot = {img.slot_id: img for img in image_rows}
    changes = [c for c in result.image_changes if c.slot_id in by_slot and c.brief.strip()]
    plan = project.plan
    added: list[tuple[str, ImageSlot]] = []
    if result.new_images:
        # Imported here because add_image imports this module.
        from inferno_ghostwriter.writer.add_image import _slots_for, next_slot_id, place_placeholder
        from inferno_ghostwriter.writer.examples import _section_index

        slots = _slots_for(project, image_rows)
        taken = {r.slot_id for r in image_rows} | {s.slot_id for s in slots} | set(PLACEHOLDER_RE.findall(markdown))
        for new in result.new_images[: max(0, MAX_NEW_IMAGES_TOTAL - len(image_rows))]:
            if not new.brief.strip():
                continue
            span = locate(markdown, new.anchor_text)
            if span is None:
                continue
            slot_id = next_slot_id(taken)
            taken.add(slot_id)
            tag = f"{{{{image:{slot_id}}}}}"
            markdown = place_placeholder(markdown, span[1], tag)
            lines = markdown.split("\n")
            slot = ImageSlot(
                slot_id=slot_id,
                kind=new.kind,
                section_index=_section_index(lines, lines.index(tag)),
                purpose=new.purpose.strip()[:300] or "Illustrates the passage",
                brief=new.brief.strip()[:1200],
            )
            slots.append(slot)
            added.append((slot_id, slot))
        if added:
            order = {s: i for i, s in enumerate(PLACEHOLDER_RE.findall(markdown))}
            slots.sort(key=lambda s: order.get(s.slot_id, len(order)))
            plan = {**(project.plan or {}), "image_slots": [s.model_dump() for s in slots]}
    if not applied and not changes and not added:
        raise WriterError("Claude couldn't find where to make that change. Try quoting the sentence you mean, or naming the section.")

    title, subtitle = project.title, project.subtitle
    new_ids: list[int] = []
    if applied or added:
        markdown = finish_text(markdown, plan)
        new_title, new_subtitle = split_title(markdown)
        title, subtitle = new_title or title, new_subtitle or subtitle
        await ctx.progress(0.5, "Checking how human the post reads")
        authenticity = await analyze(
            llm=llm,
            settings=settings,
            markdown=markdown,
            voice_profile=voice_profile.markdown,
            profile=author_profile(samples, voice_profile.baseline_stylometrics),
            use_judge=settings.ai_detection,
            usage=ctx.add_usage,
        )
        with Session(engine) as session:
            row = session.get(Project, project_id)
            if row is None:
                raise WriterError("Project not found.")
            push_revision(row, feedback, "tweak")
            if added and row.revisions:
                # Undoing this tweak takes its new images out again (see the restore endpoint).
                row.revisions = [{**row.revisions[0], "added_slots": [s for s, _ in added]}, *row.revisions[1:]]
            if added:
                row.plan = plan
                order = {s: i for i, s in enumerate(PLACEHOLDER_RE.findall(markdown))}
                for slot_id, slot in added:
                    new_row = ProjectImage(project_id=project_id, slot_id=slot_id, kind=slot.kind, purpose=slot.purpose, prompt=slot.brief)
                    session.add(new_row)
                    session.flush()
                    if new_row.id is not None:
                        new_ids.append(new_row.id)
                for existing in session.exec(select(ProjectImage).where(ProjectImage.project_id == project_id)):
                    existing.position = order.get(existing.slot_id, len(order))
                    session.add(existing)
            row.markdown, row.title, row.subtitle = markdown, title, subtitle
            row.fidelity = measure(markdown, voice_profile.baseline_stylometrics)
            row.authenticity = authenticity
            row.updated_at = utcnow()
            session.add(row)
            # The author's feedback is a lesson for every later post, not just this one.
            persona_row = session.get(Persona, project.persona_id)
            if persona_row is not None and learn:
                record_feedback(persona_row, feedback)
                session.add(persona_row)
            session.commit()

    if new_ids:
        await ctx.progress(0.65, f"Drawing {len(new_ids)} new image{'s' if len(new_ids) > 1 else ''}")
        draw_semaphore = asyncio.Semaphore(3)

        async def draw_new(image_id: int) -> None:
            async with draw_semaphore:
                await images.create(
                    image_id,
                    persona=persona,
                    title=title,
                    markdown=markdown,
                    voice_profile=voice_profile.markdown,
                    brand_kit=project.brand_kit,
                    usage=ctx.add_usage,
                )
            await ctx.emit("image_ready", {"image_id": image_id})

        await asyncio.gather(*(draw_new(i) for i in new_ids))

    if changes:
        await ctx.progress(0.7, f"Redrawing {len(changes)} image{'s' if len(changes) > 1 else ''}")
        with Session(engine) as session:
            for change in changes:
                image = session.get(ProjectImage, by_slot[change.slot_id].id)
                if image is not None:
                    image.prompt = change.brief.strip()
                    session.add(image)
            session.commit()
        semaphore = asyncio.Semaphore(3)

        async def redraw(image_id: int) -> None:
            async with semaphore:
                await images.create(
                    image_id,
                    persona=persona,
                    title=title,
                    markdown=markdown,
                    voice_profile=voice_profile.markdown,
                    redraw=True,
                    rethink=True,
                    brand_kit=project.brand_kit,
                    usage=ctx.add_usage,
                )
            await ctx.emit("image_ready", {"image_id": image_id})

        await asyncio.gather(*(redraw(image_id) for c in changes if (image_id := by_slot[c.slot_id].id) is not None))

    await ctx.progress(1.0, "Feedback applied")
    return {
        "project_id": project_id,
        "summary": result.summary,
        "applied": applied,
        "skipped": skipped,
        "images_redrawn": [c.slot_id for c in changes],
        "images_added": [s for s, _ in added],
    }

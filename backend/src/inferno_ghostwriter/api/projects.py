"""Projects (one per post), their images, and exports."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlmodel import Session, col, select

from inferno_ghostwriter.abtest.service import ABTestError, current_test, delete_project_data, start_ab_test
from inferno_ghostwriter.api.deps import ServicesDep, SessionDep, image_or_404, persona_or_404, project_or_404
from inferno_ghostwriter.api.evolution import evolution_out
from inferno_ghostwriter.api.image_room import image_formats, image_out, image_url, room_info
from inferno_ghostwriter.api.schemas import (
    ABTestSummary,
    AddImageIn,
    BuildsOnIn,
    CopyHtmlOut,
    ExperimentIn,
    GenerateIn,
    ImageEditIn,
    ImageFormatOut,
    ImageOut,
    ImageUpdate,
    InterviewAnswer,
    InterviewIn,
    JobOut,
    LinkedInPostOut,
    OpeningCatalogOut,
    OpeningStyleOut,
    PickIn,
    ProjectCreate,
    ProjectCreated,
    ProjectOut,
    ProjectSummary,
    ProjectUpdate,
    RedrawIn,
    ReferenceHistoryOut,
    ReferenceOut,
    RemixDimensionOut,
    RemixOptionOut,
    RevertIn,
    RevisionOut,
    RewriteIn,
    TweakIn,
    WordsIn,
)
from inferno_ghostwriter.authenticity import analyze, author_profile
from inferno_ghostwriter.config import ImageRoute
from inferno_ghostwriter.db import Idea, Persona, PersonaEvolution, Project, ProjectImage, ProjectReference, Sample, utcnow
from inferno_ghostwriter.evolution import change_stage, edit_rate, start_analysis
from inferno_ghostwriter.experiments.models import Experiment, Scenario, default_scenarios
from inferno_ghostwriter.experiments.service import rerun as rerun_experiment
from inferno_ghostwriter.export import PLATFORMS, Platform, build_bundle, copy_html, linkedin_post
from inferno_ghostwriter.images import ImageProviderError, raster
from inferno_ghostwriter.images import remix as remixing
from inferno_ghostwriter.images.opening.styles import STYLES, suggested_by_type
from inferno_ghostwriter.images.render import upload_to_png
from inferno_ghostwriter.jobs import JobContext
from inferno_ghostwriter.llm import LLMError
from inferno_ghostwriter.llm.router import image_model
from inferno_ghostwriter.services import Services
from inferno_ghostwriter.voice import current_voice_profile
from inferno_ghostwriter.voice.lessons import extract_lessons, record_lessons
from inferno_ghostwriter.writer import (
    TEXT_JOBS,
    Dials,
    WriterError,
    finish_text,
    generate_article,
    merge_titles,
    push_revision,
    regenerate_titles,
    resolve,
    rewrite_passage,
    set_title,
    split_title,
    tweak_post,
    word_count,
)
from inferno_ghostwriter.writer.add_image import add_image_at
from inferno_ghostwriter.writer.image_text import describe_image, failed_sync_result, sync_text_to_images
from inferno_ghostwriter.writer.interview import plan_interview
from inferno_ghostwriter.writer.pipeline import measure
from inferno_ghostwriter.writer.references import in_post, project_references
from inferno_ghostwriter.writer.social import write_linkedin_post
from inferno_ghostwriter.writer.tweak import locate

router = APIRouter(prefix="/api")

MAX_IMAGE_BYTES = 15 * 1024 * 1024


# -- helpers ---------------------------------------------------------------------------


def reference_out(row: ProjectReference, markdown: str) -> ReferenceOut:
    assert row.id is not None
    history = [
        ReferenceHistoryOut(
            index=i,
            kind=str(entry.get("kind", "")),
            url=str(entry.get("url", "")),
            title=str(entry.get("title", "")),
            created_at=str(entry.get("created_at", "")),
        )
        for i, entry in enumerate(row.history or [])
    ]
    return ReferenceOut(
        **row.model_dump(exclude={"project_id", "anchor", "query", "original", "inserted", "tried_urls", "history", "created_at"}),
        in_post=in_post(row, markdown),
        history=history,
    )


def project_images(session: Session, project_id: int) -> list[ProjectImage]:
    return list(session.exec(select(ProjectImage).where(ProjectImage.project_id == project_id).order_by(col(ProjectImage.position))))


def project_out(session: Session, project: Project, services: Services) -> ProjectOut:
    assert project.id is not None
    persona = session.get(Persona, project.persona_id)
    profile = current_voice_profile(session, project.persona_id) if persona else None
    resolved = (
        resolve(
            Dials(**(project.dials or {})),
            persona,
            project.prompt,
            default_revisions=services.settings.revision_passes,
            words_per_image=(profile.baseline_stylometrics or {}).get("words_per_image") if profile else None,
            code_runs=services.settings.allow_code_execution,
        ).model_dump()
        if persona
        else {}
    )
    # Only text jobs: an image redraw is followed by its own card, not the whole page.
    active = services.jobs.active_for(project_id=project.id, kinds=TEXT_JOBS)
    revisions = [
        RevisionOut(
            index=i,
            label=str(entry.get("label", "")),
            kind=str(entry.get("kind", "edit")),
            created_at=str(entry.get("created_at", "")),
            word_count=word_count(str(entry.get("markdown", ""))),
        )
        for i, entry in enumerate(project.revisions or [])
    ]
    test = current_test(session, project.id)
    evolutions = session.exec(
        select(PersonaEvolution).where(PersonaEvolution.project_id == project.id).order_by(col(PersonaEvolution.created_at))
    ).all()
    return ProjectOut(
        **project.model_dump(exclude={"revisions", "baseline_markdown", "baseline_title", "ab_test_id", "variant"}),
        ab_test=ABTestSummary(id=test.id, status=test.status, error=test.error) if test is not None and test.id is not None else None,
        has_baseline=bool(project.baseline_markdown),
        edit_rate=edit_rate(project.baseline_markdown, project.markdown) if project.baseline_markdown else None,
        evolutions=[evolution_out(e) for e in evolutions],
        revisions=revisions,
        resolved_dials=resolved,
        images=[image_out(i, project.markdown) for i in project_images(session, project.id)],
        references=[reference_out(r, project.markdown) for r in project_references(session, project.id)],
        active_job_id=active[0].id if active else None,
        active_job_kind=active[0].kind if active else None,
    )


def _check_idle(services: Services, project_id: int) -> None:
    if services.jobs.active_for(project_id=project_id, kinds=TEXT_JOBS):
        raise HTTPException(409, "Claude is still working on this post. Wait for it to finish.")


def _new_experiment(spec: ExperimentIn) -> Experiment:
    """The experiment a new post starts with: the author's prompt and scenarios (the six defaults when none are given)."""
    scenarios = [Scenario(**s.model_dump()) for s in spec.scenarios] if spec.scenarios is not None else default_scenarios()
    ids = [s.id for s in scenarios]
    if not scenarios or len(set(ids)) != len(ids):
        raise HTTPException(422, "An experiment needs at least one scenario, and each needs its own id.")
    return Experiment(prompt=spec.prompt.strip(), model=spec.model, scenarios=scenarios, run_code=spec.run_code)


def _check_no_open_test(session: Session, project_id: int) -> None:
    """While an A/B test is open the post is not refined: the author picks a winner (or discards the test) first."""
    test = current_test(session, project_id)
    if test is not None and test.status != "decided":
        raise HTTPException(409, "This post has an A/B test in progress. Pick a winner or discard the test first.")


def _writable_persona(session: Session, persona_id: int) -> Persona:
    persona = persona_or_404(session, persona_id)
    if current_voice_profile(session, persona_id) is None:
        raise HTTPException(422, f"Persona '{persona.name}' has no voice profile yet. Generate it first.")
    return persona


async def start_generation(services: Services, project_id: int) -> str:
    active = services.jobs.active_for(project_id=project_id, kinds=TEXT_JOBS)
    if active and active[0].kind == "generate_post":
        return active[0].id
    if active:
        raise HTTPException(409, "Claude is still applying your feedback. Wait for it to finish.")
    job = await services.jobs.start(
        "generate_post",
        lambda ctx: generate_article(
            engine=services.engine,
            llm=services.llm,
            settings=services.settings,
            images=services.images,
            project_id=project_id,
            ctx=ctx,
            links=services.links,
            sandbox=services.sandbox,
        ),
        project_id=project_id,
    )
    return job.id


async def start_interview(services: Services, project_id: int) -> str:
    """Ask the interview questions for this post (the optional step before writing)."""
    active = services.jobs.active_for(project_id=project_id, kinds=TEXT_JOBS)
    if active and active[0].kind == "interview":
        return active[0].id
    if active:
        raise HTTPException(409, "Claude is still working on this post. Wait for it to finish.")
    job = await services.jobs.start(
        "interview",
        lambda ctx: _interview_job(services, project_id, ctx),
        project_id=project_id,
    )
    return job.id


async def _interview_job(services: Services, project_id: int, ctx: JobContext) -> dict[str, Any]:
    await ctx.progress(0.1, "Thinking of a few questions for you")
    interview = await plan_interview(llm=services.llm, settings=services.settings, engine=services.engine, project_id=project_id)
    await ctx.progress(1.0, "Your questions are ready")
    return {"project_id": project_id, "questions": len(interview)}


def _save_interview(project: Project, answers: list[InterviewAnswer]) -> None:
    project.interview = [{"question": a.question.strip(), "answer": a.answer.strip()} for a in answers if a.question.strip()]


# -- projects ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(session: SessionDep) -> list[ProjectSummary]:
    # The two hidden posts of an A/B test are not posts of their own.
    projects = session.exec(select(Project).where(col(Project.variant).is_(None)).order_by(col(Project.updated_at).desc())).all()
    names = {p.id: p.name for p in session.exec(select(Persona))}
    out = []
    for project in projects:
        assert project.id is not None
        hero = session.exec(select(ProjectImage).where(ProjectImage.project_id == project.id, ProjectImage.slot_id == "hero")).first()
        out.append(
            ProjectSummary(
                **project.model_dump(
                    include={"id", "persona_id", "title", "prompt", "status", "stage", "outcome", "idea_id", "created_at", "updated_at"}
                ),
                persona_name=names.get(project.persona_id, ""),
                thumbnail_url=image_url(hero) if hero else None,
                ab_status=test.status if (test := current_test(session, project.id)) else None,
            )
        )
    return out


@router.post("/projects", response_model=ProjectCreated, status_code=201)
async def create_project(body: ProjectCreate, session: SessionDep, services: ServicesDep) -> ProjectCreated:
    if body.persona_id is not None:
        persona = persona_or_404(session, body.persona_id)
    else:
        active = session.exec(select(Persona).where(Persona.is_active == True)).first()  # noqa: E712
        if active is None:
            raise HTTPException(422, "Create a persona and turn it on first.")
        persona = active
    assert persona.id is not None
    if body.generate and current_voice_profile(session, persona.id) is None:
        raise HTTPException(422, f"Persona '{persona.name}' has no voice profile yet. Generate it first.")
    idea = session.get(Idea, body.idea_id) if body.idea_id is not None else None
    if body.idea_id is not None and idea is None:
        raise HTTPException(404, "That idea no longer exists.")
    if body.experiment is not None and body.mode == "ab":
        raise HTTPException(422, "A library experiment cannot also be an A/B test.")
    project = Project(
        persona_id=persona.id,
        experiment=_new_experiment(body.experiment).model_dump() if body.experiment is not None else None,
        prompt=body.prompt.strip(),
        dials=body.dials.model_dump(exclude_none=True),
        title=(idea.title if idea else body.prompt.strip().splitlines()[0])[:80],
        brand_kit=body.brand_kit.model_dump() if body.brand_kit else {},
        idea_id=body.idea_id,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    assert project.id is not None
    if idea is not None:
        idea.state = "used"
        idea.project_id = project.id
        session.add(idea)
        session.commit()
    job_id: str | None = None
    if body.generate and body.interview and body.mode != "ab":
        # Interview first: the post is written when the author answers (or skips) the questions.
        job_id = await start_interview(services, project.id)
    elif body.generate and body.mode == "ab":
        try:
            job_id = (await start_ab_test(services, project.id)).id
        except ABTestError as exc:
            raise HTTPException(409, str(exc)) from exc
    elif body.generate:
        job_id = await start_generation(services, project.id)
    session.refresh(project)
    return ProjectCreated(project=project_out(session, project, services), job_id=job_id)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, session: SessionDep, services: ServicesDep) -> ProjectOut:
    return project_out(session, project_or_404(session, project_id), services)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectUpdate, session: SessionDep, services: ServicesDep) -> ProjectOut:
    project = project_or_404(session, project_id)
    if body.markdown is not None and body.markdown != project.markdown:
        push_revision(project, "Before your edit", "edit")
        persona = session.get(Persona, project.persona_id)
        if persona is not None and body.learn:
            record_lessons(persona, extract_lessons(project.markdown, body.markdown))
            session.add(persona)
        project.markdown = body.markdown
    if body.title is not None and body.title.strip():
        project.title = body.title.strip()
        project.markdown = set_title(project.markdown, project.title) if project.markdown else project.markdown
    if body.pinned_titles is not None:
        project.pinned_titles = merge_titles(body.pinned_titles)
    if body.brand_kit is not None:
        project.brand_kit = body.brand_kit.model_dump()
    if body.prompt is not None:
        project.prompt = body.prompt.strip()
    if body.dials is not None:
        project.dials = body.dials.model_dump(exclude_none=True)
    if body.persona_id is not None and body.persona_id != project.persona_id:
        _writable_persona(session, body.persona_id)
        project.persona_id = body.persona_id
    due = change_stage(session, project, stage=body.stage, outcome=body.outcome) if body.stage or body.outcome else []
    project.updated_at = utcnow()
    session.add(project)
    session.commit()
    # Publishing compares the post with what was generated; a hit is read for its secret sauce.
    for kind in due:
        await start_analysis(services, project_id, kind)
    session.refresh(project)
    return project_out(session, project, services)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, session: SessionDep, services: ServicesDep) -> None:
    project_or_404(session, project_id)
    delete_project_data(session, services.storage, project_id)
    # The idea it was written from goes back to the saved list.
    for idea in session.exec(select(Idea).where(Idea.project_id == project_id)):
        idea.state, idea.project_id = "saved", None
        session.add(idea)
    session.commit()


@router.post("/projects/{project_id}/generate", response_model=JobOut, status_code=202)
async def generate(project_id: int, session: SessionDep, services: ServicesDep, body: GenerateIn | None = None) -> JobOut:
    """Write the whole post again; with a body, first apply a new brief, dials or persona."""
    project = project_or_404(session, project_id)
    _check_no_open_test(session, project_id)
    body = body or GenerateIn()
    persona_id = body.persona_id if body.persona_id is not None else project.persona_id
    _writable_persona(session, persona_id)
    if body.persona_id is not None or body.prompt is not None or body.dials is not None or body.interview is not None:
        _check_idle(services, project_id)
        project.persona_id = persona_id
        if body.prompt is not None:
            project.prompt = body.prompt.strip()
        if body.dials is not None:
            project.dials = body.dials.model_dump(exclude_none=True)
        if body.interview is not None:
            _save_interview(project, body.interview)
        project.updated_at = utcnow()
        session.add(project)
        session.commit()
    job_id = await start_generation(services, project_id)
    return JobOut(**services.jobs.get(job_id).model_dump())


@router.post("/projects/{project_id}/interview", response_model=JobOut, status_code=202)
async def interview(project_id: int, session: SessionDep, services: ServicesDep) -> JobOut:
    """Ask 3-5 new interview questions for this post (replacing any earlier ones)."""
    project_or_404(session, project_id)
    _check_no_open_test(session, project_id)
    job_id = await start_interview(services, project_id)
    return JobOut(**services.jobs.get(job_id).model_dump())


@router.put("/projects/{project_id}/interview", response_model=ProjectOut)
def save_interview(project_id: int, body: InterviewIn, session: SessionDep, services: ServicesDep) -> ProjectOut:
    """Save the author's answers without writing the post yet."""
    project = project_or_404(session, project_id)
    _save_interview(project, body.answers)
    project.updated_at = utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_out(session, project, services)


@router.post("/projects/{project_id}/tweak", response_model=JobOut, status_code=202)
async def tweak(project_id: int, body: TweakIn, session: SessionDep, services: ServicesDep) -> JobOut:
    """Apply the author's feedback with surgical edits, keeping the rest of the text and the images."""
    project = project_or_404(session, project_id)
    if not project.markdown:
        raise HTTPException(409, "Generate the post before tweaking it.")
    _check_no_open_test(session, project_id)
    _writable_persona(session, project.persona_id)
    _check_idle(services, project_id)
    job = await services.jobs.start(
        "tweak_post",
        lambda ctx: tweak_post(
            engine=services.engine,
            llm=services.llm,
            settings=services.settings,
            images=services.images,
            project_id=project_id,
            feedback=body.feedback,
            ctx=ctx,
        ),
        project_id=project_id,
    )
    return JobOut(**job.model_dump())


def _drop_added_image(session: Session, services: Services, project: Project, slot_id: str) -> None:
    """Remove an image the author added from a highlight: its row, files and plan slot. The caller commits."""
    folder = services.storage.image_dir(project.id)  # type: ignore[arg-type]
    for image in session.exec(select(ProjectImage).where(ProjectImage.project_id == project.id, ProjectImage.slot_id == slot_id)):
        names = {image.file_name, *(entry.get("file_name") for entry in image.history)} - {None}
        for name in names:
            (folder / str(name)).unlink(missing_ok=True)
        session.delete(image)
    plan = dict(project.plan or {})
    plan["image_slots"] = [slot for slot in plan.get("image_slots", []) if slot.get("slot_id") != slot_id]
    project.plan = plan


@router.post("/projects/{project_id}/revisions/{index}/restore", response_model=ProjectOut)
def restore_revision(project_id: int, index: int, session: SessionDep, services: ServicesDep) -> ProjectOut:
    """Bring back an earlier text version; the current text becomes a version too, so this can be undone."""
    project = project_or_404(session, project_id)
    revisions = list(project.revisions or [])
    if not 0 <= index < len(revisions):
        raise HTTPException(404, "No such version.")
    _check_idle(services, project_id)
    entry = revisions.pop(index)
    project.revisions = revisions
    for added in [entry["added_slot"]] if entry.get("added_slot") else entry.get("added_slots") or []:
        # The text from before an image was added: the image goes too, or its placeholder would come straight back.
        _drop_added_image(session, services, project, str(added))
    push_revision(project, f"Before restoring: {entry.get('label', '')}", "restore")
    project.markdown = finish_text(str(entry.get("markdown", "")), project.plan)
    title, subtitle = split_title(project.markdown)
    project.title = title or str(entry.get("title", "")) or project.title
    project.subtitle = subtitle or str(entry.get("subtitle", "")) or project.subtitle
    voice_profile = current_voice_profile(session, project.persona_id)
    if voice_profile is not None:
        project.fidelity = measure(project.markdown, voice_profile.baseline_stylometrics)
    project.updated_at = utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_out(session, project, services)


@router.post("/projects/{project_id}/rewrite", response_model=ProjectOut)
async def rewrite(project_id: int, body: RewriteIn, session: SessionDep, services: ServicesDep) -> ProjectOut:
    project_or_404(session, project_id)
    _check_no_open_test(session, project_id)
    try:
        await rewrite_passage(
            llm=services.llm,
            settings=services.settings,
            engine=services.engine,
            project_id=project_id,
            selection=body.selection,
            instruction=body.instruction,
            action=body.action,
        )
    except (WriterError, LLMError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return project_out(session, project_or_404(session, project_id), services)


@router.post("/projects/{project_id}/titles", response_model=ProjectOut)
async def new_title_options(project_id: int, session: SessionDep, services: ServicesDep) -> ProjectOut:
    """Have Claude replace the title options; the current and pinned titles are kept."""
    project_or_404(session, project_id)
    try:
        await regenerate_titles(llm=services.llm, settings=services.settings, engine=services.engine, project_id=project_id)
    except (WriterError, LLMError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.expire_all()
    return project_out(session, project_or_404(session, project_id), services)


@router.post("/projects/{project_id}/authenticity", response_model=ProjectOut)
async def check_authenticity(project_id: int, session: SessionDep, services: ServicesDep) -> ProjectOut:
    """Re-run the AI-generation detection report on the current text (e.g. after editing)."""
    project = project_or_404(session, project_id)
    if not project.markdown:
        raise HTTPException(409, "Generate the post first.")
    voice_profile = current_voice_profile(session, project.persona_id)
    samples = list(session.exec(select(Sample).where(Sample.persona_id == project.persona_id)))
    project.authenticity = await analyze(
        llm=services.llm,
        settings=services.settings,
        markdown=project.markdown,
        voice_profile=voice_profile.markdown if voice_profile else "",
        profile=author_profile(samples, voice_profile.baseline_stylometrics if voice_profile else None),
        use_judge=services.settings.ai_detection,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project_out(session, project, services)


# -- images ------------------------------------------------------------------------------


def _image_file(services: Services, image: ProjectImage, file_name: str | None) -> FileResponse:
    if not file_name:
        raise HTTPException(404, "Image has no file yet.")
    path = services.storage.image_dir(image.project_id) / file_name
    if not path.is_file():
        raise HTTPException(404, "Image file is missing.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/images/{image_id}/file")
def image_file(image_id: int, session: SessionDep, services: ServicesDep) -> FileResponse:
    image = image_or_404(session, image_id)
    return _image_file(services, image, image.file_name)


@router.get("/images/{image_id}/history/{index}/file")
def image_history_file(image_id: int, index: int, session: SessionDep, services: ServicesDep) -> FileResponse:
    image = image_or_404(session, image_id)
    if not 0 <= index < len(image.history):
        raise HTTPException(404, "No such version.")
    return _image_file(services, image, image.history[index].get("file_name"))


@router.patch("/images/{image_id}", response_model=ImageOut)
def update_image(image_id: int, body: ImageUpdate, session: SessionDep) -> ImageOut:
    image = image_or_404(session, image_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(image, key, value)
    session.add(image)
    session.commit()
    session.refresh(image)
    return image_out(image)


async def _sync_text(services: Services, project_id: int, changes: list[tuple[str, str, str]], ctx) -> dict:  # type: ignore[no-untyped-def]
    """After images are redrawn, fix the sentences that described the old ones. Never fails the redraw."""
    if services.jobs.active_for(project_id=project_id, kinds=TEXT_JOBS):
        return {"text_edits": 0, "text_summary": ""}
    try:
        await ctx.progress(0.85, "Updating the text around the image")
        return await sync_text_to_images(
            engine=services.engine,
            llm=services.llm,
            settings=services.settings,
            project_id=project_id,
            changes=changes,
            usage=ctx.add_usage,
        )
    except Exception as exc:  # noqa: BLE001 - the redraw already succeeded; a failed text check must not fail it
        return failed_sync_result(exc)


async def _image_job(
    services: Services,
    session: Session,
    image_id: int,
    *,
    rethink: bool = False,
    instruction: str = "",
    concept: int | None = None,
    format: str | None = None,
    note: str = "",
    tweaks: dict[str, str] | None = None,
    improve: bool = True,
    model: ImageRoute = "auto",
) -> JobOut:
    image = image_or_404(session, image_id)
    if model in ("codex", "gemini"):
        cli = services.secondary.get(model)
        if cli is None or not await cli.signed_in():
            raise HTTPException(
                422, f"{'ChatGPT' if model == 'codex' else 'Gemini'} is not signed in. Sign in under Settings -> Optional models."
            )
    project = project_or_404(session, image.project_id)
    # Detached copies: the job outlives this request's database session.
    persona = Persona.model_validate(persona_or_404(session, project.persona_id).model_dump())
    brand_kit = dict(project.brand_kit or {})
    voice_profile = current_voice_profile(session, project.persona_id)
    markdown, title, voice = project.markdown, project.title, voice_profile.markdown if voice_profile else ""
    before = describe_image(image)

    async def run(ctx):  # type: ignore[no-untyped-def]
        await ctx.progress(0.1, "Editing image" if instruction else "Redrawing image")
        with image_model(model):
            result = await services.images.create(
                image_id,
                persona=persona,
                title=title,
                markdown=markdown,
                voice_profile=voice,
                redraw=True,
                rethink=rethink,
                brand_kit=brand_kit,
                instruction=instruction,
                concept=concept,
                format=format,
                note=note,
                tweaks=tweaks,
                improve=improve,
                usage=ctx.add_usage,
            )
        if result.status == "error":
            raise ImageProviderError(result.error or "Image generation failed.")
        return {
            "image_id": image_id,
            # Images that extend this one were drawn from its old version; the card offers to match them.
            "dependents": dependent_slots(services, image.project_id, image.slot_id),
            **await _sync_text(services, image.project_id, [(result.slot_id, before, describe_image(result))], ctx),
        }

    job = await services.jobs.start("edit_image" if instruction else "redraw_image", run, project_id=project.id)
    return JobOut(**job.model_dump())


@router.post("/images/{image_id}/redraw", response_model=JobOut, status_code=202)
async def redraw_image(image_id: int, body: RedrawIn, session: SessionDep, services: ServicesDep) -> JobOut:
    """Make a new version of one image (redesign it with ``rethink``).

    Every image has the same tools: ``concept`` draws one of its stored ideas, ``format`` pitches again in a meme
    format, an opening style or another way to draw it (the whole meme bank is open to the opening image), and
    ``note`` steers the redraw in the author's words."""
    image = image_or_404(session, image_id)
    for dimension, tweak_id in (body.tweaks or {}).items():
        if dimension not in remixing.DIMENSIONS or (tweak_id != "auto" and remixing.get_tweak(dimension, tweak_id) is None):
            raise HTTPException(422, f"Unknown tweak {dimension}={tweak_id!r}.")
    room = room_info(image)
    if body.format is not None:
        allowed = {f.id for f in image_formats(room.room if room else _room_kind(image), image.kind)}
        if body.format not in allowed:
            raise HTTPException(422, f"This image cannot be drawn as {body.format!r}.")
    if body.concept is not None and (room is None or body.concept not in {p.index for p in room.pitches}):
        raise HTTPException(422, "This image has no such idea.")
    return await _image_job(
        services,
        session,
        image_id,
        rethink=body.rethink,
        concept=body.concept,
        format=body.format,
        note=body.note,
        tweaks=body.tweaks,
        improve=body.improve,
        model=body.model,
    )


def _room_kind(image: ProjectImage) -> str:
    return {"hero": "opening", "meme": "meme"}.get(image.kind, "body")


@router.post("/images/{image_id}/pick", response_model=ImageOut)
def pick_finalist(image_id: int, body: PickIn, session: SessionDep, services: ServicesDep) -> ImageOut:
    """Show another finalist of the image's last fresh run (no call to Claude)."""
    image_or_404(session, image_id)
    try:
        return image_out(services.images.pick(image_id, body.index))
    except IndexError as exc:
        raise HTTPException(404, "No such finalist.") from exc


@router.get("/images/{image_id}/finalists/{index}/file")
def finalist_file(image_id: int, index: int, session: SessionDep, services: ServicesDep) -> FileResponse:
    image = image_or_404(session, image_id)
    finalists = image.finalists or []
    if not 0 <= index < len(finalists):
        raise HTTPException(404, "No such finalist.")
    return _image_file(services, image, finalists[index].get("file_name"))


@router.get("/image-formats", response_model=list[ImageFormatOut])
def list_image_formats(room: str = "meme", kind: str = "") -> list[ImageFormatOut]:
    """What an image's room can switch to: ``room`` is opening, meme or body (with the image's ``kind``)."""
    if room not in ("opening", "meme", "body"):
        raise HTTPException(422, "room is one of opening, meme, body.")
    return image_formats(room, kind)


def dependent_slots(services: Services, project_id: int, slot_id: str) -> list[str]:
    """Slot ids of the images that extend ``slot_id`` (directly or through each other), in post order."""
    with Session(services.engine) as session:
        rows = project_images(session, project_id)
    found: list[str] = []
    frontier = {slot_id}
    for row in rows:  # rows are in post order and an image only builds on an earlier one
        if row.builds_on in frontier:
            found.append(row.slot_id)
            frontier.add(row.slot_id)
    return found


@router.post("/images/{image_id}/build-on", response_model=JobOut, status_code=202)
async def build_on(image_id: int, body: BuildsOnIn, session: SessionDep, services: ServicesDep) -> JobOut:
    """Make this image extend an earlier one and draw it again from that image's data and look."""
    image = image_or_404(session, image_id)
    rows = project_images(session, image.project_id)
    base = next((r for r in rows if r.slot_id == body.slot_id), None)
    if base is None or base.position >= image.position:
        raise HTTPException(422, "An image can only build on one that comes earlier in the post.")
    if base.kind in ("meme", "hero") or image.kind in ("meme", "hero"):
        raise HTTPException(422, "The opening image and the closing meme stand on their own.")
    if not base.spec or base.provider in ("upload", "placeholder"):
        raise HTTPException(422, "That image has no source to build on (it is an upload or a placeholder). Redraw it first.")
    image.builds_on = base.slot_id
    session.add(image)
    session.commit()
    return await _image_job(services, session, image_id, improve=False)


@router.delete("/images/{image_id}/build-on", response_model=ImageOut)
def clear_build_on(image_id: int, session: SessionDep) -> ImageOut:
    """Make an image stand on its own again (it keeps its current picture)."""
    image = image_or_404(session, image_id)
    image.builds_on = ""
    session.add(image)
    session.commit()
    session.refresh(image)
    return image_out(image)


@router.post("/images/{image_id}/redraw-dependents", response_model=JobOut, status_code=202)
async def redraw_dependents(image_id: int, session: SessionDep, services: ServicesDep) -> JobOut:
    """Redraw the images that build on this one, in order, so they match its current data and look."""
    image = image_or_404(session, image_id)
    project = project_or_404(session, image.project_id)
    slots = dependent_slots(services, image.project_id, image.slot_id)
    if not slots:
        raise HTTPException(409, "No other image builds on this one.")
    persona = Persona.model_validate(persona_or_404(session, project.persona_id).model_dump())
    brand_kit = dict(project.brand_kit or {})
    voice_profile = current_voice_profile(session, project.persona_id)
    markdown, title, voice = project.markdown, project.title, voice_profile.markdown if voice_profile else ""
    rows = {r.slot_id: r for r in project_images(session, image.project_id)}
    ids = [i for i in (rows[s].id for s in slots) if i is not None]
    before = {rows[s].id: (s, describe_image(rows[s])) for s in slots}

    async def run(ctx):  # type: ignore[no-untyped-def]
        redrawn: dict[int, ProjectImage] = {}
        for n, dependent_id in enumerate(ids):
            await ctx.progress(n / len(ids), f"Matching image {n + 1} of {len(ids)}")
            redrawn[dependent_id] = await services.images.create(
                dependent_id,
                persona=persona,
                title=title,
                markdown=markdown,
                voice_profile=voice,
                redraw=True,
                remix=False,
                brand_kit=brand_kit,
                usage=ctx.add_usage,
            )
            await ctx.emit("image_ready", {"image_id": dependent_id})
        changes = [(before[i][0], before[i][1], describe_image(img)) for i, img in redrawn.items() if i in before]
        return {"image_ids": ids, **await _sync_text(services, image.project_id, changes, ctx)}

    job = await services.jobs.start("redraw_images", run, project_id=image.project_id)
    return JobOut(**job.model_dump())


@router.get("/remix-options", response_model=list[RemixDimensionOut])
def remix_options() -> list[RemixDimensionOut]:
    """What Remix can change in a redraw: colors, who is in it, staging and medium (each also has "auto")."""
    return [
        RemixDimensionOut(
            id=dimension,
            label=remixing.DIMENSION_LABELS[dimension],
            options=[RemixOptionOut(id=t.id, label=t.label, swatch=list(t.colors)) for t in remixing.TWEAKS if t.dimension == dimension],
        )
        for dimension in remixing.DIMENSIONS
    ]


@router.put("/images/{image_id}/words", response_model=ImageOut)
async def set_words(image_id: int, body: WordsIn, session: SessionDep, services: ServicesDep) -> ImageOut:
    """Retype the words of a meme or a code-drawn opening image (see ``ImageOut.room.slots``). It is drawn again at
    once with no call to Claude; numbers and sources cannot be changed this way."""
    image = image_or_404(session, image_id)
    project = project_or_404(session, image.project_id)
    persona = persona_or_404(session, project.persona_id)
    try:
        return image_out(await services.images.set_words(image_id, body.words, persona=persona, brand_kit=dict(project.brand_kit or {})))
    except ImageProviderError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/opening-styles", response_model=OpeningCatalogOut)
def opening_styles() -> OpeningCatalogOut:
    """Every way a post can open, and which styles suit each article type."""
    from inferno_ghostwriter.writer.formulas import ARTICLE_TYPES

    return OpeningCatalogOut(
        styles=[
            OpeningStyleOut(
                id=s.id, label=s.label, summary=s.summary, when_to_use=s.when_to_use, needs_data=s.needs_data, min_humor=s.min_humor
            )
            for s in STYLES
        ],
        suggested_by_type=suggested_by_type([t.id for t in ARTICLE_TYPES]),
    )


@router.post("/projects/{project_id}/images/redraw", response_model=JobOut, status_code=202)
async def redraw_all_images(project_id: int, session: SessionDep, services: ServicesDep) -> JobOut:
    """Redraw every image Claude drew (e.g. after changing the brand kit); uploads and old placeholders stay."""
    project = project_or_404(session, project_id)
    persona = Persona.model_validate(persona_or_404(session, project.persona_id).model_dump())
    brand_kit = dict(project.brand_kit or {})
    voice_profile = current_voice_profile(session, project.persona_id)
    markdown, title, voice = project.markdown, project.title, voice_profile.markdown if voice_profile else ""
    drawn = [
        (i.id, i.kind) for i in project_images(session, project_id) if i.id is not None and i.provider not in ("upload", "placeholder")
    ]
    before = {i.id: (i.slot_id, describe_image(i)) for i in project_images(session, project_id) if i.id is not None}
    image_ids = [image_id for image_id, _ in drawn]
    if not image_ids:
        raise HTTPException(409, "This post has no drawn images to redraw.")

    async def run(ctx):  # type: ignore[no-untyped-def]
        done = 0
        semaphore = asyncio.Semaphore(3)
        redrawn: dict[int, ProjectImage] = {}
        # The closing meme waits for the opening image, so a meme sandwich's closer knows the new opener.
        opened = asyncio.Event()
        if not any(kind == "hero" for _, kind in drawn) or not services.images.opening_may_be_meme(project_id, persona):
            opened.set()

        async def one(image_id: int, kind: str) -> None:
            nonlocal done
            if kind == "meme":
                await opened.wait()
            try:
                async with semaphore:
                    redrawn[image_id] = await services.images.create(
                        image_id,
                        persona=persona,
                        title=title,
                        markdown=markdown,
                        voice_profile=voice,
                        redraw=True,
                        remix=False,
                        brand_kit=brand_kit,
                        usage=ctx.add_usage,
                    )
            finally:
                if kind == "hero":
                    opened.set()
            done += 1
            await ctx.emit("image_ready", {"image_id": image_id})
            await ctx.progress(done / len(image_ids), f"Redrew {done} of {len(image_ids)} images")

        await ctx.progress(0.05, f"Redrawing {len(image_ids)} images")
        await asyncio.gather(*(one(i, kind) for i, kind in drawn))
        failed = [img for img in redrawn.values() if img.status == "error"]
        if failed and len(failed) == len(redrawn):
            raise ImageProviderError(failed[0].error or "Image generation failed.")
        changes = [(before[i][0], before[i][1], describe_image(img)) for i, img in redrawn.items() if i in before]
        return {"image_ids": image_ids, **await _sync_text(services, project_id, changes, ctx)}

    job = await services.jobs.start("redraw_images", run, project_id=project_id)
    return JobOut(**job.model_dump())


@router.post("/projects/{project_id}/images", response_model=JobOut, status_code=202)
async def add_image(project_id: int, body: AddImageIn, session: SessionDep, services: ServicesDep) -> JobOut:
    """Add an image near a highlighted passage: Claude picks the spot and the kind, draws it, and reworks adjacent text."""
    project = project_or_404(session, project_id)
    if not project.markdown:
        raise HTTPException(409, "Generate the post before adding images.")
    _check_no_open_test(session, project_id)
    _writable_persona(session, project.persona_id)
    _check_idle(services, project_id)
    if locate(project.markdown, body.selection) is None:
        raise HTTPException(422, "Could not find the highlighted text in the post. Select it again.")
    job = await services.jobs.start(
        "add_image",
        lambda ctx: add_image_at(
            engine=services.engine,
            llm=services.llm,
            settings=services.settings,
            images=services.images,
            project_id=project_id,
            selection=body.selection,
            instruction=body.instruction,
            ctx=ctx,
        ),
        project_id=project_id,
    )
    return JobOut(**job.model_dump())


async def _start_experiment_run(services: Services, session: Session, project_id: int, only: list[str] | None) -> JobOut:
    project = project_or_404(session, project_id)
    if not project.experiment:
        raise HTTPException(409, "This post is not a library experiment.")
    if not project.markdown:
        raise HTTPException(409, "Generate the post before rerunning its experiment.")
    if only and any(s not in {sc.get("id") for sc in project.experiment.get("scenarios", [])} for s in only):
        raise HTTPException(404, "No such scenario.")
    _check_no_open_test(session, project_id)
    _writable_persona(session, project.persona_id)
    _check_idle(services, project_id)
    job = await services.jobs.start(
        "run_experiment",
        lambda ctx: rerun_experiment(
            engine=services.engine,
            llm=services.llm,
            settings=services.settings,
            images=services.images,
            sandbox=services.sandbox,
            project_id=project_id,
            only=only,
            reporter=ctx,
        ),
        project_id=project_id,
    )
    return JobOut(**job.model_dump())


@router.post("/projects/{project_id}/experiment/rerun", response_model=JobOut, status_code=202)
async def rerun_experiment_all(project_id: int, session: SessionDep, services: ServicesDep) -> JobOut:
    """Ask the model again for every scenario of a library experiment, run the answers and swap them into the post."""
    return await _start_experiment_run(services, session, project_id, None)


@router.post("/projects/{project_id}/experiment/{scenario_id}/rerun", response_model=JobOut, status_code=202)
async def rerun_experiment_scenario(project_id: int, scenario_id: str, session: SessionDep, services: ServicesDep) -> JobOut:
    """The same for one scenario."""
    return await _start_experiment_run(services, session, project_id, [scenario_id])


@router.post("/images/{image_id}/edit", response_model=JobOut, status_code=202)
async def edit_image(image_id: int, body: ImageEditIn, session: SessionDep, services: ServicesDep) -> JobOut:
    """Change one image as the author describes ("make the arrows orange"), keeping the rest of it."""
    image = image_or_404(session, image_id)
    if image.kind != "hands_on_viz" and (image.provider in ("upload", "placeholder") or not image.spec):
        raise HTTPException(422, "Only images Claude drew can be edited by instruction. Redraw or upload this one instead.")
    # Only GPT can change a painting, so a painting's edit ignores the model choice.
    model = "auto" if image.provider == raster.PROVIDER else body.model
    return await _image_job(services, session, image_id, instruction=body.instruction, model=model)


@router.post("/images/{image_id}/reference", response_model=ImageOut)
async def set_reference(image_id: int, session: SessionDep, services: ServicesDep, file: Annotated[UploadFile, File()]) -> ImageOut:
    """Attach a style reference ("make it like this"): the designer and the judge see it on every draw of this image."""
    image_or_404(session, image_id)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Images must be 15 MB or smaller.")
    try:
        png, _, _ = upload_to_png(data)
    except Exception as exc:
        raise HTTPException(
            422, f"That file is not an image Inferno Ghostwriter can read ({type(exc).__name__}: {str(exc)[:120]})."
        ) from exc
    return image_out(services.images.set_reference(image_id, png))


@router.delete("/images/{image_id}/reference", response_model=ImageOut)
def clear_reference(image_id: int, session: SessionDep, services: ServicesDep) -> ImageOut:
    image_or_404(session, image_id)
    return image_out(services.images.set_reference(image_id, None))


@router.get("/images/{image_id}/reference/file")
def reference_file(image_id: int, session: SessionDep, services: ServicesDep) -> FileResponse:
    image = image_or_404(session, image_id)
    if not image.reference:
        raise HTTPException(404, "This image has no style reference.")
    return _image_file(services, image, image.reference)


@router.post("/images/{image_id}/upload", response_model=ImageOut)
async def upload_image(
    image_id: int,
    session: SessionDep,
    services: ServicesDep,
    file: Annotated[UploadFile, File()],
) -> ImageOut:
    """Replace an image with the user's own (e.g. a real platform screenshot)."""
    image = image_or_404(session, image_id)
    project = project_or_404(session, image.project_id)
    persona = persona_or_404(session, project.persona_id)
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Images must be 15 MB or smaller.")
    try:
        png, width, height = upload_to_png(data)
    except Exception as exc:
        raise HTTPException(
            422, f"That file is not an image Inferno Ghostwriter can read ({type(exc).__name__}: {str(exc)[:120]})."
        ) from exc
    return image_out(services.images.save_upload(image_id, png, width, height, persona))


@router.post("/images/{image_id}/revert", response_model=ImageOut)
def revert_image(image_id: int, body: RevertIn, session: SessionDep, services: ServicesDep) -> ImageOut:
    image_or_404(session, image_id)
    try:
        return image_out(services.images.revert(image_id, body.index))
    except IndexError as exc:
        raise HTTPException(404, "No such version.") from exc


# -- export -------------------------------------------------------------------------------


def _check_platform(platform: str) -> Platform:
    if platform not in PLATFORMS:
        raise HTTPException(404, f"Unknown platform. Use one of: {', '.join(PLATFORMS)}.")
    return platform  # type: ignore[return-value]


@router.get("/projects/{project_id}/export/{platform}")
def export_bundle(project_id: int, platform: str, session: SessionDep, services: ServicesDep) -> Response:
    project = project_or_404(session, project_id)
    if not project.markdown:
        raise HTTPException(409, "Generate the post before exporting it.")
    persona = session.get(Persona, project.persona_id)
    name, data = build_bundle(
        project,
        project_images(session, project_id),
        services.storage.image_dir(project_id),
        _check_platform(platform),
        author=(persona.display_name or persona.name) if persona else "",
    )
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/projects/{project_id}/copy/{platform}", response_model=CopyHtmlOut)
def export_copy_html(project_id: int, platform: str, session: SessionDep, services: ServicesDep) -> CopyHtmlOut:
    project = project_or_404(session, project_id)
    html = copy_html(project, project_images(session, project_id), services.storage.image_dir(project_id), _check_platform(platform))
    return CopyHtmlOut(html=html)


@router.get("/projects/{project_id}/linkedin-post", response_model=LinkedInPostOut)
def get_linkedin_post(project_id: int, session: SessionDep) -> LinkedInPostOut:
    """The saved Claude-written feed post, or a template built from the article."""
    project = project_or_404(session, project_id)
    if not project.markdown:
        raise HTTPException(409, "Generate the post first.")
    text, by_claude = linkedin_post(project)
    return LinkedInPostOut(text=text, characters=len(text), written_by="claude" if by_claude else "template")


@router.post("/projects/{project_id}/linkedin-post", response_model=LinkedInPostOut)
async def create_linkedin_post(project_id: int, session: SessionDep, services: ServicesDep) -> LinkedInPostOut:
    """Have Claude write the LinkedIn feed post in the persona's voice (replaces any saved one)."""
    project_or_404(session, project_id)
    try:
        text = await write_linkedin_post(llm=services.llm, settings=services.settings, engine=services.engine, project_id=project_id)
    except (WriterError, LLMError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return LinkedInPostOut(text=text, characters=len(text), written_by="claude")

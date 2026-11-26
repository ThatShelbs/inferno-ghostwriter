"""The hands-on kit: build it, download it, push it to GitHub, and link it from the post."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from inferno_ghostwriter.api.deps import ServicesDep, SessionDep, project_or_404
from inferno_ghostwriter.api.projects import project_images
from inferno_ghostwriter.api.schemas import (
    GitHubStatusOut,
    JobOut,
    KitBuildIn,
    KitFitOut,
    KitLibraryOut,
    KitLinkOut,
    KitOut,
    KitPromptOut,
    KitPushIn,
    KitRepoOut,
)
from inferno_ghostwriter.db import Project
from inferno_ghostwriter.kit import KIT_JOBS, LIBRARIES, LIBRARY_LABELS, add_link, build_kit, kit_fit, kit_folder, push_kit, render_kit
from inferno_ghostwriter.kit.build import Repo, kit_prompts, zip_kit
from inferno_ghostwriter.kit.design import KitDesign
from inferno_ghostwriter.kit.github import SIGN_IN, repo_name
from inferno_ghostwriter.services import Services
from inferno_ghostwriter.storage import slugify
from inferno_ghostwriter.writer import WriterError, split_title

router = APIRouter(prefix="/api")


def _job_out(job: Any) -> JobOut:
    return JobOut(**job.model_dump())


def _ready(project: Project) -> None:
    if not project.markdown:
        raise HTTPException(409, "Generate the post before building its kit.")


def _idle(services: Services, project_id: int) -> None:
    if services.jobs.active_for(project_id=project_id, kinds=KIT_JOBS):
        raise HTTPException(409, "The kit is still being built or pushed. Wait for it to finish.")


def _files(services: Services, project: Project) -> list[str]:
    kit = project.kit or {}
    if not kit.get("slug") or project.id is None:
        return []
    folder = kit_folder(services.storage, project.id, kit["slug"])
    if not folder.exists():
        return []
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and ".git" not in p.relative_to(folder).parts)


def _repo_out(kit: dict[str, Any]) -> KitRepoOut | None:
    repo = kit.get("repo")
    if not repo:
        return None
    public = repo["visibility"] == "public"
    colab = Repo(repo["owner"], repo["name"], public).colab_url if public else None
    return KitRepoOut(
        owner=repo["owner"], name=repo["name"], visibility=repo["visibility"], url=repo["url"], colab_url=colab, pushed_at=repo["pushed_at"]
    )


@router.get("/projects/{project_id}/kit", response_model=KitOut)
def get_kit(project_id: int, session: SessionDep, services: ServicesDep) -> KitOut:
    project = project_or_404(session, project_id)
    fit = kit_fit(project, project_images(session, project_id))
    kit = project.kit or {}
    title, _ = split_title(project.markdown or "")
    repo = _repo_out(kit)
    return KitOut(
        fit=KitFitOut(recommended=fit.recommended, article_type=fit.article_type, reasons=fit.reasons),
        built=bool(kit.get("design")),
        built_at=kit.get("built_at"),
        library=str(kit.get("library") or "auto"),
        note=str(kit.get("note") or ""),
        article_url=str(kit.get("article_url") or ""),
        files=_files(services, project),
        notes=list(kit.get("notes") or []),
        repo=repo,
        default_name=repo_name(kit.get("slug") or slugify(title or project.title or "post")),
        linked=bool(repo and repo.url in (project.markdown or "")),
        libraries=[KitLibraryOut(id=lib, label=LIBRARY_LABELS[lib]) for lib in LIBRARIES],
        prompts=[
            KitPromptOut(file=p.file, title=p.title, text=p.text)
            for p in kit_prompts(project, KitDesign.model_validate(kit["design"]) if kit.get("design") else None)
        ],
    )


@router.post("/projects/{project_id}/kit", response_model=JobOut, status_code=202)
async def start_kit(project_id: int, session: SessionDep, services: ServicesDep, body: KitBuildIn | None = None) -> JobOut:
    """Design and build the kit (one model call, plus one retry if its code fails the checks)."""
    _ready(project_or_404(session, project_id))
    _idle(services, project_id)
    body = body or KitBuildIn()
    url = body.article_url.strip()
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(422, "The article link must start with https://.")
    job = await services.jobs.start(
        "build_kit",
        lambda ctx: build_kit(services.kit, project_id, library=body.library, note=body.note, article_url=url, job=ctx),
        project_id=project_id,
    )
    return _job_out(job)


@router.get("/projects/{project_id}/kit/download")
def download_kit(project_id: int, session: SessionDep, services: ServicesDep) -> Response:
    project_or_404(session, project_id)
    try:
        slug, files = render_kit(services.kit, project_id)
    except WriterError as exc:
        raise HTTPException(409, str(exc)) from exc
    return Response(
        zip_kit(slug, files), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{slug}-kit.zip"'}
    )


@router.post("/projects/{project_id}/kit/push", response_model=JobOut, status_code=202)
async def start_push(project_id: int, session: SessionDep, services: ServicesDep, body: KitPushIn | None = None) -> JobOut:
    """Create the GitHub repository and push the kit, or push an update to the kit's repository."""
    project = project_or_404(session, project_id)
    if not (project.kit or {}).get("design"):
        raise HTTPException(409, "Build the kit first.")
    _idle(services, project_id)
    status = await services.github.astatus(fresh=True)
    if not status.signed_in:
        raise HTTPException(422, status.message)
    body = body or KitPushIn()
    job = await services.jobs.start(
        "push_kit",
        lambda ctx: push_kit(services.kit, project_id, name=body.name, public=body.visibility == "public", job=ctx),
        project_id=project_id,
    )
    return _job_out(job)


@router.post("/projects/{project_id}/kit/link", response_model=KitLinkOut)
def link_kit(project_id: int, session: SessionDep, services: ServicesDep) -> KitLinkOut:
    """Add a follow-along line pointing to the kit near the top of the post (undoable)."""
    project_or_404(session, project_id)
    try:
        return KitLinkOut(added=add_link(services.engine, project_id))
    except WriterError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/github/status", response_model=GitHubStatusOut)
async def github_status(services: ServicesDep, fresh: bool = False) -> GitHubStatusOut:
    status = await services.github.astatus(fresh=fresh)
    return GitHubStatusOut(
        installed=status.installed, signed_in=status.signed_in, login=status.login, message=status.message, sign_in_command=SIGN_IN
    )

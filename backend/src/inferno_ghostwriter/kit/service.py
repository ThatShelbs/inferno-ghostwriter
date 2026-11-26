"""Build the kit, push it to GitHub, and link it from the post."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Persona, Project, ProjectImage, Sample, utcnow
from inferno_ghostwriter.jobs import JobContext
from inferno_ghostwriter.kit.build import Repo, chart_data, kit_files, other_images, own_code, write_kit
from inferno_ghostwriter.kit.design import KitDesign, design_kit
from inferno_ghostwriter.kit.fit import article_type_of
from inferno_ghostwriter.kit.github import GitHubCLI, GitHubError, repo_name
from inferno_ghostwriter.llm import LLM, SystemBlock
from inferno_ghostwriter.storage import Storage, slugify
from inferno_ghostwriter.voice import current_voice_profile, format_exemplars, select_exemplars
from inferno_ghostwriter.voice.lessons import format_lessons
from inferno_ghostwriter.voice.playbook import format_playbook
from inferno_ghostwriter.writer import WriterError, split_title
from inferno_ghostwriter.writer.pipeline import writer_system
from inferno_ghostwriter.writer.revisions import push_revision

KIT_JOBS = ("build_kit", "push_kit")
LINK_MARK = "**Follow along:**"


@dataclass
class KitContext:
    engine: Engine
    llm: LLM
    settings: Settings
    storage: Storage
    github: GitHubCLI


def kit_folder(storage: Storage, project_id: int, slug: str) -> Path:
    return storage.project_dir(project_id) / "kit" / slug


def _load(engine: Engine, project_id: int) -> tuple[Project, list[ProjectImage], Persona | None]:
    with Session(engine, expire_on_commit=False) as session:
        project = session.get(Project, project_id)
        if project is None:
            raise WriterError("Project not found.")
        images = list(session.exec(select(ProjectImage).where(ProjectImage.project_id == project_id).order_by(col(ProjectImage.position))))
        persona = session.get(Persona, project.persona_id)
        return project, images, persona


def _author(persona: Persona | None) -> str:
    return (persona.display_name or persona.name) if persona else ""


def _save_kit(engine: Engine, project_id: int, kit: dict[str, Any]) -> None:
    with Session(engine) as session:
        row = session.get(Project, project_id)
        if row is not None:
            row.kit = kit
            session.add(row)
            session.commit()


def _repo(kit: dict[str, Any]) -> Repo | None:
    repo = kit.get("repo")
    if not repo:
        return None
    return Repo(owner=repo["owner"], name=repo["name"], public=repo["visibility"] == "public")


def render_kit(ctx: KitContext, project_id: int, repo: Repo | None = None) -> tuple[str, dict[str, bytes]]:
    """The kit's files from the saved design (no model call), and its folder slug."""
    project, images, persona = _load(ctx.engine, project_id)
    kit = project.kit or {}
    if not kit.get("design") or not project.markdown:
        raise WriterError("Build the kit first.")
    files = kit_files(
        project,
        images,
        ctx.storage.image_dir(project_id),
        KitDesign.model_validate(kit["design"]),
        author=_author(persona),
        repo=repo or _repo(kit),
        article_url=str(kit.get("article_url") or ""),
    )
    return str(kit["slug"]), files


def _system(engine: Engine, project: Project, persona: Persona | None) -> list[SystemBlock]:
    with Session(engine) as session:
        profile = current_voice_profile(session, project.persona_id)
        samples = list(session.exec(select(Sample).where(Sample.persona_id == project.persona_id)))
    if profile is None:
        return [SystemBlock("You write clear, friendly, beginner-level Python and explain it in plain words.")]
    return writer_system(
        profile.markdown,
        format_exemplars(select_exemplars(project.prompt, samples)),
        format_lessons(persona.edit_lessons if persona else None),
        format_playbook(persona.playbook if persona else None),
    )


async def build_kit(
    ctx: KitContext, project_id: int, *, library: str, note: str, article_url: str, job: JobContext | None = None
) -> dict[str, Any]:
    project, images, persona = _load(ctx.engine, project_id)
    if not project.markdown:
        raise WriterError("Generate the post before building its kit.")
    if job:
        await job.progress(0.1, "Designing the notebook, data and prompts")
    ready = [i for i in images if i.status == "ready"]
    charts = chart_data(ready)
    # Charts the post's own code draws ship as that code, so the model is not asked to recreate them.
    covered = [(c.slot_id, c.title) for c in own_code(project, ready) if c.slot_id]
    design, notes = await design_kit(
        llm=ctx.llm,
        settings=ctx.settings,
        system=_system(ctx.engine, project, persona),
        markdown=project.markdown,
        article_type=article_type_of(project),
        library=library,
        note=note,
        charts=charts,
        others=other_images(ready, charts, {slot for slot, _ in covered}),
        covered=covered,
    )
    title, _ = split_title(project.markdown)
    old = project.kit or {}
    kit = {
        **old,
        "slug": old.get("slug") or slugify(title or project.title or "post"),
        "design": design.model_dump(),
        "library": library,
        "note": note,
        "article_url": article_url,
        "notes": notes,
        "built_at": utcnow().isoformat(),
    }
    _save_kit(ctx.engine, project_id, kit)
    if job:
        await job.progress(0.85, "Building the files")
    slug, files = render_kit(ctx, project_id)
    write_kit(kit_folder(ctx.storage, project_id, slug), files)
    return {"project_id": project_id, "files": len(files), "notes": notes}


async def push_kit(ctx: KitContext, project_id: int, *, name: str | None, public: bool, job: JobContext | None = None) -> dict[str, Any]:
    project, _, _ = _load(ctx.engine, project_id)
    kit = dict(project.kit or {})
    if not kit.get("design"):
        raise WriterError("Build the kit first.")
    status = await ctx.github.astatus(fresh=True)
    if not status.signed_in:
        raise GitHubError(status.message)
    existing = kit.get("repo")
    title, _ = split_title(project.markdown)
    message = f"Hands-on kit for {title or project.title or 'the post'}"
    if existing:
        repo = Repo(owner=existing["owner"], name=existing["name"], public=existing["visibility"] == "public")
    else:
        repo = Repo(owner=status.login, name=repo_name(name or kit["slug"]), public=public)
    if job:
        await job.progress(0.2, "Writing the files")
    slug, files = render_kit(ctx, project_id, repo)
    folder = kit_folder(ctx.storage, project_id, slug)
    write_kit(folder, files)
    if job:
        await job.progress(0.5, "Pushing to GitHub" if existing else "Creating the repository on GitHub")
    if existing:
        await ctx.github.aupdate(folder, message=f"Update: {message}")
        url = existing["url"]
    else:
        description = str(kit["design"].get("description") or message)
        url = await ctx.github.acreate(folder, name=repo.name, public=repo.public, description=description, message=message)
        # gh may report the repository under another owner (an organization default); trust what it says.
        parts = url.rstrip("/").split("/")
        repo = Repo(owner=parts[-2], name=parts[-1], public=repo.public)
    kit["repo"] = {
        "owner": repo.owner,
        "name": repo.name,
        "visibility": "public" if repo.public else "private",
        "url": url,
        "pushed_at": utcnow().isoformat(),
    }
    _save_kit(ctx.engine, project_id, kit)
    return {"project_id": project_id, "url": url}


def link_markdown(repo: Repo, url: str) -> str:
    line = f"> {LINK_MARK} the notebook, data and code for this post are in [the companion repo]({url})."
    if repo.public:
        line += f" [Open it in Colab]({repo.colab_url}) to run every example yourself."
    return line


def insert_link(markdown: str, link: str) -> str:
    """The post with the follow-along line before its first section heading (else before the closing meme, else at the end)."""
    lines = markdown.split("\n")
    for marker in ("## ", "{{image:meme}}"):
        for i, line in enumerate(lines):
            if i > 0 and line.strip().startswith(marker):
                return "\n".join([*lines[:i], link, "", *lines[i:]])
    return markdown.rstrip() + "\n\n" + link + "\n"


def add_link(engine: Engine, project_id: int) -> bool:
    """Add the follow-along line to the post (an undoable revision); False when it is already there."""
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if project is None:
            raise WriterError("Project not found.")
        kit = project.kit or {}
        repo = _repo(kit)
        if repo is None:
            raise WriterError("Push the kit to GitHub first.")
        url = kit["repo"]["url"]
        if url in project.markdown:
            return False
        push_revision(project, "Linked the hands-on kit", "edit")
        project.markdown = insert_link(project.markdown, link_markdown(repo, url))
        project.updated_at = utcnow()
        session.add(project)
        session.commit()
        return True

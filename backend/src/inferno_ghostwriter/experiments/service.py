"""Running an experiment inside a post: ask and run every scenario, keep the results on the project, and keep the post's
slots, image rows and text in step with them.

The pipeline calls ``execute`` before the writer and ``expand_into`` after it; the *Rerun* routes call ``rerun``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Persona, Project, ProjectImage, utcnow
from inferno_ghostwriter.experiments import compose
from inferno_ghostwriter.experiments.models import MONTAGE_SLOT, Experiment, Scenario, load, slot_id
from inferno_ghostwriter.experiments.run import ExperimentError, ScenarioOutcome, run_experiment
from inferno_ghostwriter.images.base import PLACEHOLDER_RE
from inferno_ghostwriter.llm import LLM
from inferno_ghostwriter.sandbox import NoSandbox, Sandbox
from inferno_ghostwriter.writer.schemas import ImageSlot

if TYPE_CHECKING:
    from inferno_ghostwriter.images import ImageService
    from inferno_ghostwriter.writer.pipeline import Reporter

log = logging.getLogger(__name__)
KIND = "hands_on_viz"


def effective(experiment: Experiment, settings: Settings, sandbox: Sandbox | None) -> Experiment:
    """The experiment as it will run: code runs only with the author's consent, the setting and something to run it with."""
    runs = experiment.run_code and settings.allow_code_execution and sandbox is not None
    return experiment.model_copy(update={"run_code": runs})


def merge(experiment: Experiment, outcomes: list[ScenarioOutcome]) -> Experiment:
    """The experiment with each outcome folded in: slot ids for the charts that exist, the montage slot, library versions."""
    by_id = {o.scenario.id: o for o in outcomes}
    environment = dict(experiment.environment)
    scenarios: list[Scenario] = []
    for index, scenario in enumerate(experiment.scenarios):
        outcome = by_id.get(scenario.id)
        updated = outcome.scenario if outcome is not None else scenario
        if outcome is not None:
            environment.update(outcome.versions)
        scenarios.append(updated.model_copy(update={"slot_id": slot_id(index) if updated.status == "ready" else ""}))
    ready = sum(1 for s in scenarios if s.slot_id)
    return experiment.model_copy(
        update={"scenarios": scenarios, "environment": environment, "montage_slot": MONTAGE_SLOT if ready >= 2 else ""}
    )


def slots_for(experiment: Experiment) -> list[ImageSlot]:
    """One hands-on slot per chart that exists, then the montage slot."""
    slots = [
        ImageSlot(
            slot_id=s.slot_id,
            kind=KIND,
            section_index=0,
            purpose=f"The chart the {s.label} code draws",
            brief=f"The chart the {s.label} code above draws.",
        )
        for s in experiment.scenarios
        if s.slot_id
    ]
    if experiment.montage_slot:
        slots.append(
            ImageSlot(
                slot_id=experiment.montage_slot,
                kind=KIND,
                section_index=0,
                purpose="Every chart side by side",
                brief="All the charts from this experiment on one sheet.",
            )
        )
    return slots


def order_slots(slots: list[dict[str, Any]], markdown: str) -> list[dict[str, Any]]:
    """Hero first, meme last, the rest in the order their placeholders appear in the text."""
    order = {sid: i for i, sid in enumerate(PLACEHOLDER_RE.findall(markdown))}
    hero = [s for s in slots if s.get("kind") == "hero"]
    meme = [s for s in slots if s.get("kind") == "meme"]
    middle = [s for s in slots if s.get("kind") not in ("hero", "meme")]
    middle.sort(key=lambda s: order.get(s["slot_id"], len(order)))
    return [*hero, *middle, *meme]


async def execute(
    *,
    llm: LLM,
    settings: Settings,
    sandbox: Sandbox | None,
    experiment: Experiment,
    reporter: Reporter,
    only: list[str] | None = None,
    reuse: bool = False,
) -> tuple[Experiment, dict[str, bytes]]:
    """Run the scenarios (all, or ``only``); returns the merged experiment and the chart PNG of each that drew one."""
    running = effective(experiment, settings, sandbox)
    total = len([s for s in experiment.scenarios if not only or s.id in only])
    done = 0
    pngs: dict[str, bytes] = {}

    async def finished(outcome: ScenarioOutcome) -> None:
        nonlocal done
        done += 1
        if outcome.png is not None:
            pngs[outcome.scenario.id] = outcome.png
        await reporter.emit("experiment_scenario", {"id": outcome.scenario.id, "status": outcome.scenario.status})
        await reporter.progress(0.02 + 0.08 * done / total, f"Ran {outcome.scenario.label} ({done} of {total})")

    outcomes = await run_experiment(
        llm=llm,
        settings=settings,
        sandbox=sandbox or NoSandbox(unavailable="Nothing is available to run code."),
        experiment=running,
        only=only,
        usage=reporter.add_usage,
        reuse=reuse,
        on_outcome=finished,
    )
    return merge(experiment, outcomes), pngs


def save(engine: Engine, project_id: int, experiment: Experiment) -> None:
    with Session(engine) as session:
        project = session.get(Project, project_id)
        if project is not None:
            project.experiment = experiment.model_dump()
            project.updated_at = utcnow()
            session.add(project)
            session.commit()


def expand_into(plan: dict[str, Any], markdown: str, experiment: Experiment) -> tuple[str, dict[str, Any]]:
    """The writer's draft with every marker expanded, and the plan with the experiment's slots added (in reading order)."""
    text = compose.expand(markdown, experiment)
    own = {s.slot_id for s in slots_for(experiment)}
    existing = [s for s in plan.get("image_slots", []) if s.get("slot_id") not in own]
    slots = [*existing, *(s.model_dump() for s in slots_for(experiment))]
    return text, {**plan, "image_slots": order_slots(slots, text)}


async def rerun(
    *,
    engine: Engine,
    llm: LLM,
    settings: Settings,
    images: ImageService,
    sandbox: Sandbox | None,
    project_id: int,
    only: list[str] | None,
    reporter: Reporter,
) -> dict[str, Any]:
    """Ask the model again for ``only`` (every scenario when None), run the new answers and swap them into the post."""
    from inferno_ghostwriter.writer.revisions import push_revision  # the writer package imports this one

    with Session(engine, expire_on_commit=False) as session:
        project = session.get(Project, project_id)
        if project is None:
            raise ExperimentError("Project not found.")
        persona = session.get(Persona, project.persona_id)
    experiment = load(project.experiment)
    if experiment is None:
        raise ExperimentError("This post has no experiment.")
    if persona is None:
        raise ExperimentError("The post's persona no longer exists.")
    if only and any(experiment.scenario(i) is None for i in only):
        raise ExperimentError("Unknown scenario.")

    await reporter.progress(0.02, "Running the experiment again")
    after, pngs = await execute(llm=llm, settings=settings, sandbox=sandbox, experiment=experiment, reporter=reporter, only=only)
    markdown = project.markdown
    touched = only or [s.id for s in experiment.scenarios]
    try:
        for scenario_id in touched:
            markdown = compose.replace_block(markdown, experiment, after, scenario_id)
    except ValueError as exc:
        raise ExperimentError(str(exc)) from exc

    # The post's slots and image rows follow the charts that exist now.
    wanted = slots_for(after)
    keep = {s.slot_id for s in wanted}
    own = {slot_id(i) for i in range(len(after.scenarios))} | {MONTAGE_SLOT}
    with Session(engine) as session:
        row = session.get(Project, project_id)
        assert row is not None
        push_revision(row, "Experiment rerun", "image")
        row.markdown = markdown
        row.experiment = after.model_dump()
        plan = dict(row.plan or {})
        others = [s for s in plan.get("image_slots", []) if s.get("slot_id") not in own]
        final = order_slots([*others, *(s.model_dump() for s in wanted)], markdown)
        plan["image_slots"] = final
        row.plan = plan
        row.updated_at = utcnow()
        session.add(row)
        position = {s["slot_id"]: i for i, s in enumerate(final)}
        existing = {i.slot_id: i for i in session.exec(select(ProjectImage).where(col(ProjectImage.project_id) == project_id))}
        for sid, image in existing.items():
            if sid in own and sid not in keep:
                session.delete(image)
            else:
                image.position = position.get(sid, image.position)
                session.add(image)
        for slot in wanted:
            if slot.slot_id not in existing:
                session.add(
                    ProjectImage(
                        project_id=project_id,
                        slot_id=slot.slot_id,
                        position=position[slot.slot_id],
                        kind=KIND,
                        purpose=slot.purpose,
                        prompt=slot.brief,
                    )
                )
        session.commit()
        rows = {i.slot_id: i.id for i in session.exec(select(ProjectImage).where(col(ProjectImage.project_id) == project_id))}

    for scenario in after.scenarios:
        image_id = rows.get(scenario.slot_id)
        png = pngs.get(scenario.id)
        if scenario.slot_id and image_id is not None and png is not None:
            images.save_experiment_image(image_id, png, scenario, persona, after.model)
    montage_id = rows.get(after.montage_slot)
    if montage_id is not None:
        await images.create(
            montage_id,
            persona=persona,
            title=project.title,
            markdown=markdown,
            voice_profile="",
            brand_kit=project.brand_kit,
            usage=reporter.add_usage,
        )
    await reporter.progress(1.0, "Experiment updated")
    return {"project_id": project_id, "scenarios": touched, "ready": [s.id for s in after.scenarios if s.status == "ready"]}

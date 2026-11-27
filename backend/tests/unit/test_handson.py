"""Hands-on data viz: the picture is what the code block above it draws; a failing example is repaired in the post itself."""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlmodel import Session

from inferno_ghostwriter.codecheck import problems
from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.db import Persona, Project, ProjectImage
from inferno_ghostwriter.demo import FakeLLM, experiment_code
from inferno_ghostwriter.images import ImageProviderError
from inferno_ghostwriter.images.codeblocks import code_before
from inferno_ghostwriter.images.handson import PROVIDER, HandsOn, HandsOnResult, code_hash, is_stale, library_of, load_spec
from inferno_ghostwriter.sandbox import NoSandbox, Sandbox
from inferno_ghostwriter.services import Services

CODE = "import matplotlib.pyplot as plt\n\nplt.bar(['a', 'b'], [1, 2])\nplt.show()"
POST = f"# T\n\n## Plot\n\nHere is the script:\n\n```python\n{CODE}\n```\n\n{{{{image:img2}}}}\n\nThat is the chart.\n"


def make(sandbox: Sandbox | None, llm: FakeLLM | None = None) -> HandsOn:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    return HandsOn(llm or FakeLLM(), settings, lambda: sandbox)


def run(handson: HandsOn, markdown: str = POST, **kwargs: str) -> HandsOnResult:
    return asyncio.run(handson.make(slot_id="img2", markdown=markdown, purpose="Two bars", **kwargs))


def test_the_chart_is_made_from_the_exact_code_above_the_image() -> None:
    sandbox = NoSandbox()
    result = run(make(sandbox))
    assert sandbox.calls == [CODE]
    assert result.changed is False and result.markdown == POST
    drawn = result.drawn
    assert drawn.provider == PROVIDER and drawn.png.startswith(b"\x89PNG") and drawn.width > 0
    assert drawn.alt == "Two bars" and f"4 lines of Matplotlib, {len(CODE)} characters" in drawn.caption
    spec = load_spec(drawn.spec)
    assert spec["code_hash"] == code_hash(CODE) and spec["library"] == "matplotlib" and (spec["lines"], spec["chars"]) == (4, len(CODE))


def test_a_failing_example_gets_one_repair_round_and_the_post_block_is_rewritten() -> None:
    llm, sandbox = FakeLLM(), NoSandbox(fail_first=1)
    result = run(make(sandbox, llm))
    assert result.changed and result.code == experiment_code("matplotlib")
    assert [c["task"] for c in llm.calls] == ["hands-on code fix"]
    assert "NameError" in llm.calls[0]["prompt"]  # the error is quoted back to the model
    block = code_before(result.markdown, "img2")
    assert block is not None and block.code == result.code
    assert "That is the chart." in result.markdown and CODE not in result.markdown
    assert len(sandbox.calls) == 2


def test_an_example_that_still_fails_after_the_repair_raises_with_the_last_line_of_the_error() -> None:
    sandbox = NoSandbox(fail_first=2)
    with pytest.raises(ImageProviderError, match="did not draw a chart: NameError"):
        run(make(sandbox))
    assert len(sandbox.calls) == 2  # exactly one repair, never a loop


def test_an_instruction_changes_the_code_first_and_then_runs_it() -> None:
    llm = FakeLLM()
    result = run(make(NoSandbox(), llm), instruction="make the bars orange")
    assert result.changed and "make the bars orange" in llm.calls[0]["prompt"]
    assert code_before(result.markdown, "img2").code == result.code  # type: ignore[union-attr]


def test_no_code_directly_above_the_image_is_an_error_that_says_what_to_do() -> None:
    post = "## A\n\nNo code here.\n\n{{image:img2}}\n"
    with pytest.raises(ImageProviderError, match="directly after the code"):
        run(make(NoSandbox()), post)


def test_without_a_sandbox_the_image_says_how_to_turn_it_on() -> None:
    with pytest.raises(ImageProviderError, match="Run example code"):
        run(make(None))


def test_a_block_the_code_check_rejects_is_repaired_not_run() -> None:
    bad = POST.replace(CODE, "import subprocess\nsubprocess.run(['ls'])")
    llm, sandbox = FakeLLM(), NoSandbox()
    result = run(make(sandbox, llm), bad)
    assert result.changed and problems(result.code) == []
    assert sandbox.calls[-1] == result.code  # what ran is the repaired block, never the unsafe one


def test_staleness_follows_the_code_above_the_image() -> None:
    spec = json.dumps({"code_hash": code_hash(CODE)})
    assert not is_stale(spec, POST, "img2")
    assert is_stale(spec, POST.replace("plt.bar", "plt.barh"), "img2")
    assert not is_stale("", POST, "img2")  # an image with no recorded code is never stale
    assert not is_stale(spec, "no code now\n\n{{image:img2}}", "img2")  # nothing above it to compare with
    assert not is_stale(spec, POST.replace(CODE, CODE + "\n\n"), "img2")  # whitespace around the block does not count


def test_the_library_named_is_the_first_plotting_import() -> None:
    assert library_of("import seaborn as sns\nimport matplotlib.pyplot as plt") == "matplotlib"
    assert library_of("import bokeh.plotting") == "bokeh"
    assert library_of("import json") == ""


# -- through the image service ---------------------------------------------------------


def seed_post(services: Services, markdown: str = POST) -> tuple[Persona, int]:
    with Session(services.engine) as session:
        persona = Persona(name="Me", display_name="Shelby Temple")
        session.add(persona)
        session.commit()
        session.refresh(persona)
        assert persona.id is not None
        detached = Persona.model_validate(persona.model_dump())
        project = Project(persona_id=persona.id, prompt="x", markdown=markdown, title="T")
        session.add(project)
        session.commit()
        session.refresh(project)
        assert project.id is not None
        image = ProjectImage(project_id=project.id, slot_id="img2", kind="hands_on_viz", purpose="Two bars", prompt="The bars")
        session.add(image)
        session.commit()
        session.refresh(image)
        assert image.id is not None
        return detached, image.id


def create(services: Services, persona: Persona, image_id: int, markdown: str = POST, instruction: str = "") -> ProjectImage:
    return asyncio.run(
        services.images.create(image_id, persona=persona, title="T", markdown=markdown, voice_profile="", instruction=instruction)
    )


def test_the_image_service_makes_the_picture_from_the_code_when_running_code_is_on(services: Services) -> None:
    services.settings.allow_code_execution = True
    persona, image_id = seed_post(services)
    image = create(services, persona, image_id)
    assert image.status == "ready", image.error
    assert image.provider == PROVIDER and image.file_name and (services.storage.image_dir(image.project_id) / image.file_name).exists()
    assert image.credit.startswith("Author: Shelby Temple; Made with Claude Opus 5.5")
    assert load_spec(image.spec)["code_hash"] == code_hash(CODE)


def test_the_image_service_explains_that_running_code_is_off_by_default(services: Services) -> None:
    assert services.settings.allow_code_execution is False
    persona, image_id = seed_post(services)
    image = create(services, persona, image_id)
    assert image.status == "error" and image.error is not None and "Run example code" in image.error


def test_a_repair_through_the_service_rewrites_the_posts_block_with_an_undo_point(services: Services) -> None:
    services.settings.allow_code_execution = True
    services.sandbox.fail_first = 1  # type: ignore[attr-defined]
    persona, image_id = seed_post(services)
    image = create(services, persona, image_id)
    assert image.status == "ready", image.error
    with Session(services.engine) as session:
        project = session.get(Project, image.project_id)
        assert project is not None
        block = code_before(project.markdown, "img2")
        assert block is not None and block.code == experiment_code("matplotlib")
        assert project.revisions and project.revisions[0]["kind"] == "image" and CODE in project.revisions[0]["markdown"]

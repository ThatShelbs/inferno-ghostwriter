from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from inferno_ghostwriter.config import Settings
from inferno_ghostwriter.demo import FakeLLM
from inferno_ghostwriter.images.judge import PitchRanking, PitchScore, SheetScore, SheetVerdict, judge_sheet, rank_pitches
from inferno_ghostwriter.llm.base import LLMError, LLMImagesUnsupportedError, LLMLimitError, LLMNotConfiguredError, LLMRefusalError
from inferno_ghostwriter.llm.router import RoutingLLM
from inferno_ghostwriter.llm.secondary import MODEL_IDS, SecondaryCLI
from inferno_ghostwriter.main import create_app
from inferno_ghostwriter.services import Services, load_runtime_settings


class Answer(BaseModel):
    word: str


async def test_uses_next_provider_after_limit_and_replaces_partial_preview(settings: Settings) -> None:
    settings.secondary.fallback = ["gemini", "codex"]
    claude = FakeLLM()
    gemini = SecondaryCLI("gemini", discover=False)
    codex = SecondaryCLI("codex", discover=False)
    gemini.complete = AsyncMock(side_effect=LLMError("Unavailable"))
    codex.complete = AsyncMock(return_value="Recovered draft")
    events = []

    async def delta(text: str) -> None:
        events.append(text)

    async def reset() -> None:
        events.append("reset")

    async def limit(**kwargs) -> str:
        await kwargs["on_delta"]("Partial")
        raise LLMLimitError("Quota")

    claude.text = AsyncMock(side_effect=limit)
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex, "gemini": gemini})
    assert await router.text(task="draft", system=[], prompt="Brief", effort="high", on_delta=delta, on_reset=reset) == "Recovered draft"
    assert events == ["Partial", "reset", "Recovered draft"]
    gemini.complete.assert_awaited_once()
    codex.complete.assert_awaited_once()


async def test_quota_fallback_excludes_claude_rendering_and_refusals(settings: Settings) -> None:
    settings.secondary.fallback = ["codex"]
    claude = FakeLLM()
    claude.structured = AsyncMock(side_effect=LLMLimitError("Quota"))
    codex = SecondaryCLI("codex", discover=False)
    codex.complete = AsyncMock(return_value=Answer(word="example"))
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex})
    request = dict(system=[], prompt="Example", schema=Answer, effort="medium")
    with pytest.raises(LLMLimitError):
        await router.structured(task="diagram image design", **request)
    claude.structured.side_effect = LLMRefusalError(None)
    with pytest.raises(LLMRefusalError):
        await router.structured(task="post plan", **request)
    codex.complete.assert_not_awaited()
    claude.structured.side_effect = LLMLimitError("Quota")
    assert await router.structured(task="post plan", **request) == Answer(word="example")


async def test_writing_stages_can_mix_claude_and_both_secondary_models(settings: Settings) -> None:
    settings.secondary.critique = "gemini"
    settings.secondary.revision = "codex"
    claude = FakeLLM()
    claude.text = AsyncMock(return_value="Claude draft")
    gemini = SecondaryCLI("gemini", discover=False)
    gemini.complete = AsyncMock(return_value=Answer(word="Gemini critique"))
    codex = SecondaryCLI("codex", discover=False)
    codex.complete = AsyncMock(return_value="Codex revision")
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"gemini": gemini, "codex": codex})

    draft = await router.text(task="draft", system=[], prompt="Brief", effort="high")
    critique = await router.structured(task="critique", system=[], prompt=draft, schema=Answer, effort="medium")
    revised = await router.text(task="revision", system=[], prompt=f"{draft}\n{critique.word}", effort="high")

    assert draft == "Claude draft" and revised == "Codex revision"
    assert gemini.complete.call_args.kwargs["prompt"] == draft
    assert codex.complete.call_args.kwargs["prompt"] == "Claude draft\nGemini critique"
    claude.text.assert_awaited_once()


async def test_optional_judges_keep_claude_in_charge_and_ignore_failed_guests(settings: Settings) -> None:
    settings.secondary.judges = ["codex", "gemini"]

    def verdict(score: int, *, veto: bool = False) -> PitchRanking:
        return PitchRanking(scores=[PitchScore(candidate=0, story_fit=score, clarity=score, surprise=score, veto=veto, note="Read")])

    claude = FakeLLM()
    claude.structured = AsyncMock(return_value=verdict(9, veto=True))
    codex = SecondaryCLI("codex", discover=False)
    codex.complete = AsyncMock(return_value=verdict(3))
    gemini = SecondaryCLI("gemini", discover=False)
    gemini.complete = AsyncMock(side_effect=LLMError("Unavailable"))
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex, "gemini": gemini})
    ranking = await rank_pitches(router, settings, context="A post", candidates=["A pitch"])
    assert ranking is not None and ranking.totals == pytest.approx([7.0]) and ranking.vetoed == {0}
    codex.complete.assert_awaited_once()
    gemini.complete.assert_awaited_once()


async def test_codex_can_review_when_claude_cannot_see_images(settings: Settings) -> None:
    settings.secondary.judges = ["codex", "gemini"]
    claude = FakeLLM()
    claude.structured = AsyncMock(side_effect=LLMImagesUnsupportedError())
    codex = SecondaryCLI("codex", discover=False)
    codex.complete = AsyncMock(
        return_value=SheetVerdict(
            scores=[
                SheetScore(candidate=0, score=4, reads_as="One"),
                SheetScore(candidate=1, score=8, reads_as="Two", fix="Guest suggestion"),
            ],
            why="Two is clearer.",
        )
    )
    gemini = SecondaryCLI("gemini", discover=False)
    gemini.complete = AsyncMock()
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex, "gemini": gemini})

    sheet = await judge_sheet(router, settings, context="A post", candidates=["One", "Two"], pngs=[b"one", b"two"])
    assert sheet is not None and sheet.order() == [1, 0] and sheet.fixes == ["", ""]
    assert codex.complete.call_args.kwargs["images"] == [b"one", b"two"]
    gemini.complete.assert_not_awaited()


async def test_guest_calls_require_a_primary_claude_connection(settings: Settings) -> None:
    claude = FakeLLM()
    codex = SecondaryCLI("codex", discover=False)
    codex.complete = AsyncMock()
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex}, claude_ready=lambda: False)
    with pytest.raises(LLMNotConfiguredError):
        await router.structured(task="opening ideas", system=[], prompt="Example", schema=Answer, effort="medium", model=MODEL_IDS["codex"])
    codex.complete.assert_not_awaited()


async def test_gemini_parses_validated_output_and_enforces_tool_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    gemini = SecondaryCLI("gemini", command=["fake-agy"], discover=False)

    async def run(args, *, cwd, timeout, body):
        assert args[args.index("--model") + 1] == "gemini-4-argon-medium"
        agent = next(cwd.glob(".agents/agents/*/agent.md"))
        assert "tools: []" in agent.read_text()
        assert "sample" in json.loads(body)["message"]["content"]
        result = {"status": "SUCCESS", "structured_output": {"word": "example"}}
        return (
            0,
            b"\n".join(
                json.dumps(event).encode()
                for event in [
                    {"event": "init", "init": {"tools": tools}},
                    {"event": "result", "result": result},
                ]
            ),
            b"",
        )

    tools = ["send_message"]
    monkeypatch.setattr(gemini, "_run", run)
    assert await gemini.complete(system=[], prompt="sample", schema=Answer) == Answer(word="example")
    tools.append("run_command")
    with pytest.raises(LLMError, match="restricted writing agent"):
        await gemini.complete(system=[], prompt="sample", schema=Answer)


def test_optional_settings_persist_and_auth_stays_local(client: TestClient, settings: Settings, services: Services) -> None:
    out = client.get("/api/settings").json()["secondary"]
    assert out["draft"] == "claude" and out["fallback"] == []
    assert client.put("/api/settings", json={"secondary": {"critique": "gemini", "fallback": ["codex"]}}).is_success
    assert client.put("/api/settings", json={"secondary": {"tweak": "codex"}}).json()["secondary"]["critique"] == "gemini"
    disk = Settings(data_dir=settings.data_dir, _env_file=None)
    load_runtime_settings(services.engine, disk)
    assert disk.secondary.critique == "gemini" and disk.secondary.fallback == ["codex"]
    assert client.put("/api/settings", json={"secondary": {"critique": "unknown"}}).status_code == 422
    assert client.post("/api/auth/secondary/codex/login", json={}).status_code == 409
    with TestClient(create_app(settings, services), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as local:
        assert local.post("/api/auth/secondary/codex/login").status_code == 415
        assert local.post("/api/auth/secondary/codex/login", json={}).status_code == 409
        assert local.post("/api/auth/secondary/codex/login", json={}, headers={"host": "example.com"}).status_code == 409
    assert client.get("/api/auth/secondary").json()[0]["installed"] is False


async def test_image_work_goes_to_the_best_fit_signed_in_model_and_falls_back_to_claude(settings: Settings) -> None:
    from inferno_ghostwriter.llm.router import image_category

    assert image_category("meme ideas") == "pitch" and image_category("chart image ideas") == "pitch"
    assert image_category("opening cheat_grid build") == "design" and image_category("meme edit (drake)") == "design"
    assert image_category("illustration image design") == "svg" and image_category("opening editorial drawing") == "svg"
    assert image_category("image sheet judge") == "judge" and image_category("draft") is None

    claude = FakeLLM()
    claude.structured = AsyncMock(return_value=Answer(word="claude"))
    codex = SecondaryCLI("codex", discover=False)
    codex.signed_in = AsyncMock(return_value=True)  # type: ignore[method-assign]
    codex.complete = AsyncMock(return_value=Answer(word="codex"))
    gemini = SecondaryCLI("gemini", discover=False)  # not verified: auto skips it
    gemini.complete = AsyncMock(return_value=Answer(word="gemini"))
    router = RoutingLLM(settings, api=claude, subscription=claude, secondary={"codex": codex, "gemini": gemini})
    request = dict(system=[], prompt="Example", schema=Answer, effort="medium")

    assert (await router.structured(task="meme ideas", **request)).word == "codex"
    assert (await router.structured(task="image sheet judge", images=[b"png"], **request)).word == "codex"
    assert (await router.structured(task="illustration image design", **request)).word == "claude"  # hand-drawn SVG stays
    gemini.complete.assert_not_awaited()

    codex.complete.side_effect = LLMError("Codex is busy")
    assert (await router.structured(task="chart image design", **request)).word == "claude"

    codex.signed_in.return_value = False
    codex.complete.reset_mock()
    assert (await router.structured(task="opening ideas", **request)).word == "claude"
    codex.complete.assert_not_awaited()

    settings.secondary.images.pitch = "claude"
    codex.signed_in.return_value = True
    assert (await router.structured(task="opening ideas", **request)).word == "claude"


def test_image_routing_and_quality_are_saved_field_by_field(client: TestClient, settings: Settings, services: Services) -> None:
    out = client.get("/api/settings").json()
    assert out["secondary"]["images"] == {"pitch": "auto", "design": "auto", "svg": "auto", "judge": "auto", "raster": True}
    assert out["image_quality"] == "lean"
    client.put("/api/settings", json={"secondary": {"images": {"svg": "codex"}}})
    saved = client.put("/api/settings", json={"secondary": {"images": {"raster": False}, "draft": "codex"}}).json()["secondary"]
    assert saved["images"]["svg"] == "codex" and saved["images"]["raster"] is False and saved["draft"] == "codex"
    assert settings.secondary.images.svg == "codex"  # a model, not a plain dict, so the router can read it
    assert client.put("/api/settings", json={"image_quality": "max"}).json()["image_quality"] == "max"
    assert settings.image_builds == 6 and settings.image_body_candidates == 3 and settings.image_refine == 3
    disk = Settings(data_dir=settings.data_dir, _env_file=None)
    load_runtime_settings(services.engine, disk)
    assert disk.image_quality == "max" and disk.image_builds == 6 and disk.secondary.images.svg == "codex"
    client.put("/api/settings", json={"image_quality": "lean"})
    assert settings.image_builds == 3 and settings.image_refine_below == 8.0

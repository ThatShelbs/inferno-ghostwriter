"""Optional subscription connections through the vendors' own local CLIs."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from inferno_ghostwriter.config import SecondaryProvider
from inferno_ghostwriter.llm.base import LLMError, LLMImagesUnsupportedError, LLMRefusalError, SystemBlock, T, UsageSink

MODEL_IDS: dict[SecondaryProvider, str] = {"codex": "gpt-6.2-sol", "gemini": "gemini-4-argon-medium"}
LABELS: dict[SecondaryProvider, str] = {"codex": "GPT-6.2 Sol (Medium)", "gemini": "Gemini 4 Argon (Medium)"}
# How long a "signed in" answer from `codex login status` is trusted before asking again.
SIGNED_IN_TTL = 600.0
INSTALL_URLS: dict[SecondaryProvider, str] = {
    "codex": "https://developers.openai.com/codex/cli",
    "gemini": "https://antigravity.google/docs/cli-getting-started",
}
_ENV = {
    "PATH",
    "PATHEXT",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "CODEX_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
}
_AGENT = "inferno-ghostwriter-text"
_CODEX_CHATGPT = 'forced_login_method="chatgpt"'


class _Probe(BaseModel):
    word: str


def _cli(provider: SecondaryProvider) -> list[str] | None:
    name = "codex" if provider == "codex" else "agy"
    found = shutil.which(name)
    if os.name != "nt":
        return [found] if found else None
    if found and Path(found).suffix.lower() == ".exe":
        return [found]
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    candidates = [local / "agy" / "bin" / "agy.exe"] if provider == "gemini" else []
    if provider == "codex":
        npm_dir = Path(found).parent if found else Path(os.environ.get("APPDATA", str(local))) / "npm"
        packages = npm_dir / "node_modules" / "@openai"
        package = packages / "codex"
        arm = platform.machine().lower() in {"arm64", "aarch64"}
        suffix, arch = ("arm64", "aarch64") if arm else ("x64", "x86_64")
        platform_package = f"codex-win32-{suffix}"
        vendor_path = Path("vendor") / f"{arch}-pc-windows-msvc" / "bin" / "codex.exe"
        candidates = [
            package / "node_modules" / "@openai" / platform_package / vendor_path,
            packages / platform_package / vendor_path,
            package / vendor_path,
        ]
    return next(([str(path)] for path in candidates if path.is_file()), None)


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def _codex_auth_store() -> str:
    # Carry forward this one setting when inference ignores the user configuration.
    config = _codex_home() / "config.toml"
    try:
        value = tomllib.loads(config.read_text(encoding="utf-8")).get("cli_auth_credentials_store")
    except (OSError, ValueError):
        return "file"
    return value if value in ("file", "keyring", "auto", "ephemeral") else "file"


class SecondaryCLI:
    def __init__(self, provider: SecondaryProvider, *, command: list[str] | None = None, discover: bool = True) -> None:
        self.provider = provider
        self.label = LABELS[provider]
        self._command = command
        self._discover = discover
        self._login: subprocess.Popen[bytes] | None = None
        self.verified = False
        self._slots = asyncio.Semaphore(3)
        # When `codex login status` last said yes (a check spawns a process; one per call added up).
        self._signed_in_at = 0.0

    @property
    def command(self) -> list[str] | None:
        return self._command or (_cli(self.provider) if self._discover else None)

    @property
    def signing_in(self) -> bool:
        return self._login is not None and self._login.poll() is None

    def start_login(self) -> None:
        command = self.command
        if command is None:
            raise LLMError(f"Install {'Codex CLI' if self.provider == 'codex' else 'Antigravity CLI'} first.")
        if self.signing_in:
            return
        self.verified = False
        self._signed_in_at = 0.0
        args = ["login", "-c", _CODEX_CHATGPT] if self.provider == "codex" else ["acp", "--login"]
        terminal = self.provider == "gemini"
        if terminal and os.name != "nt":
            raise LLMError("Run agy acp --login in a terminal, then return here and choose Test connection.")
        try:
            self._login = subprocess.Popen(
                [*command, *args],
                env=self._env(),
                cwd=Path.home(),
                stdin=None if terminal else subprocess.DEVNULL,
                stdout=None if terminal else subprocess.DEVNULL,
                stderr=None if terminal else subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE" if terminal else "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise LLMError(f"Could not start {self.label} sign-in.") from exc

    async def signed_in(self, *, fresh: bool = False) -> bool:
        """Whether this model can be used now. A yes from Codex is trusted for ``SIGNED_IN_TTL`` seconds."""
        if self.provider == "gemini":
            return self.verified
        command = self.command
        if command is None:
            return False
        if not fresh and time.monotonic() - self._signed_in_at < SIGNED_IN_TTL:
            return True
        try:
            status, out, err = await self._run([*command, "login", "status"], cwd=Path.home(), timeout=8)
        except LLMError:
            return False
        ok = status == 0 and "logged in using chatgpt" in (out + err).decode(errors="replace").lower()
        self._signed_in_at = time.monotonic() if ok else 0.0
        return ok

    async def test(self) -> None:
        self.verified = False
        result = await self.complete(
            system=[SystemBlock("This is a connection test.")], prompt='Set word to "inferno".', schema=_Probe, timeout=75
        )
        if not isinstance(result, _Probe) or result.word.strip().lower() != "inferno":
            raise LLMError(f"{self.label} returned an unexpected test response.")
        self.verified = True

    async def complete(
        self,
        *,
        system: list[SystemBlock],
        prompt: str,
        schema: type[T] | None = None,
        images: list[bytes] | None = None,
        usage: UsageSink | None = None,
        timeout: float = 240,
    ) -> T | str:
        command = self.command
        if command is None:
            raise LLMError(f"The CLI for {self.label} is unavailable.")
        if images and self.provider != "codex":
            raise LLMImagesUnsupportedError()
        instructions = "\n\n".join(block.text for block in system)
        request = (
            f"Complete the writing task below. Return only the requested result and use no tools.\n\n"
            f"<instructions>\n{instructions}\n</instructions>\n\n<task>\n{prompt}\n</task>"
        )
        async with self._slots:
            if self.provider == "codex" and not await self.signed_in():
                raise LLMError("Sign in to Codex with ChatGPT in Settings before using GPT-6.2 Sol.")
            with tempfile.TemporaryDirectory(prefix="inferno-secondary-") as tmp:
                cwd = Path(tmp)
                if self.provider == "codex":
                    payload, counters, _ = await self._codex(command, cwd, request, schema, images, timeout)
                else:
                    payload, counters = await self._gemini(command, cwd, request, schema, timeout)
        if usage and counters:
            usage({key: counters[key] for key in ("input_tokens", "output_tokens", "cache_read_input_tokens") if key in counters})
        if schema:
            try:
                return schema.model_validate_json(payload) if isinstance(payload, str) else schema.model_validate(payload)
            except ValidationError as exc:
                raise LLMError(f"{self.label} returned an invalid structured response.") from exc
        if not isinstance(payload, str) or not payload.strip():
            raise LLMError(f"{self.label} returned an empty response.")
        return payload

    async def paint(self, prompt: str, *, images: list[bytes] | None = None, usage: UsageSink | None = None, timeout: float = 360) -> bytes:
        """One picture from GPT's own image generation (Codex only), as PNG bytes. ``images`` are shown to it
        first (a style reference, or the picture to change)."""
        command = self.command
        if self.provider != "codex" or command is None:
            raise LLMError(f"{self.label} cannot paint pictures.")
        request = (
            "Use your image generation tool to create exactly one image as described below. Do not write code or files "
            "yourself. When the image is made, reply only with the word done.\n\n<picture>\n" + prompt + "\n</picture>"
        )
        async with self._slots:
            if not await self.signed_in():
                raise LLMError("Sign in to Codex with ChatGPT in Settings before using GPT image generation.")
            with tempfile.TemporaryDirectory(prefix="inferno-secondary-") as tmp:
                _, counters, thread = await self._codex(command, Path(tmp), request, None, images, timeout, paint=True)
        if usage and counters:
            usage({key: counters[key] for key in ("input_tokens", "output_tokens", "cache_read_input_tokens") if key in counters})
        folder = _codex_home() / "generated_images" / thread if thread else None
        found = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime) if folder and folder.is_dir() else []
        if not found or folder is None:
            raise LLMError(f"{self.label} did not return a picture.")
        png = found[-1].read_bytes()
        shutil.rmtree(folder, ignore_errors=True)  # the app keeps its own copy; leave nothing behind in ~/.codex
        return png

    async def _codex(
        self,
        command: list[str],
        cwd: Path,
        request: str,
        schema: type[T] | None,
        images: list[bytes] | None,
        timeout: float,
        *,
        paint: bool = False,
    ) -> tuple[str, dict[str, int], str]:

        args = [
            *command,
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "--color",
            "never",
            "--model",
            MODEL_IDS["codex"],
            "-c",
            'model_provider="openai"',
            "-c",
            _CODEX_CHATGPT,
            "-c",
            f'cli_auth_credentials_store="{_codex_auth_store()}"',
            "-c",
            'model_reasoning_effort="medium"',
            "-c",
            'approval_policy="never"',
            "-c",
            'web_search="disabled"',
            "-c",
            "project_doc_max_bytes=0",
            "--disable",
            "shell_tool",
            "--disable",
            "plugins",
            "--disable",
            "multi_agent",
            "--enable" if paint else "--disable",
            "image_generation",
        ]
        for index, image in enumerate(images or []):
            path = cwd / f"picture-{index}.png"
            path.write_bytes(image)
            args += ["--image", str(path)]
        if schema:
            # Some app schemas include maps and defaulted fields outside Codex's strict schema subset.
            request += "\n\nReturn a single JSON object without fences, matching this schema:\n" + json.dumps(schema.model_json_schema())
        status, stdout, stderr = await self._run([*args, "-"], cwd=cwd, timeout=timeout, body=request.encode())
        messages = []
        counters: dict[str, int] = {}
        failed = False
        thread = ""
        for line in stdout.splitlines():
            event = _object(line)
            if event.get("type") == "thread.started":
                thread = str(event.get("thread_id") or "")
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))
            if event.get("type") == "turn.completed":
                counters = event.get("usage") or {}
                if "cached_input_tokens" in counters:
                    counters["cache_read_input_tokens"] = counters["cached_input_tokens"]
            if event.get("type") == "turn.failed":
                failed = True
        if status or failed or not messages:
            self._failed(stdout, stderr)
        payload = messages[-1].strip()
        if schema and payload.startswith("```") and payload.endswith("```"):
            payload = payload.partition("\n")[2][:-3].strip()
        return payload, counters, thread

    async def _gemini(
        self, command: list[str], cwd: Path, request: str, schema: type[T] | None, timeout: float
    ) -> tuple[Any, dict[str, int]]:
        agent = cwd / ".agents" / "agents" / _AGENT / "agent.md"
        agent.parent.mkdir(parents=True)
        agent.write_text(
            f"---\nname: {_AGENT}\ndescription: Text writing and review\ntools: []\n"
            "inheritMcp: false\nsubagent: false\ncommandExecutionPolicy: 'off'\n---\n"
            "Complete writing tasks using only the supplied material.\n",
            encoding="utf-8",
        )
        settings = cwd / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "modelProvider": "",
                    "agentMode": "",
                    "toolPermission": "strict",
                    "permissions": {
                        "deny": [
                            f"{action}(*)"
                            for action in ("command", "read_file", "write_file", "read_url", "execute_url", "download_url", "mcp")
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        args = [
            *command,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--settings",
            str(settings),
            "--disable-slash-commands",
            "--log-file",
            str(cwd / "agy.log"),
            "--agent",
            _AGENT,
            "--model",
            MODEL_IDS["gemini"],
        ]
        if schema:
            path = cwd / "schema.json"
            path.write_text(json.dumps(schema.model_json_schema()), encoding="utf-8")
            args += ["--json-schema", str(path)]
        body = (json.dumps({"event": "user", "message": {"content": request}}) + "\n").encode()
        status, stdout, stderr = await self._run(args, cwd=cwd, timeout=timeout, body=body)
        events = [_object(line) for line in stdout.splitlines()]
        result: dict[str, Any] = next((event.get("result", {}) for event in reversed(events) if event.get("event") == "result"), {})
        if status or result.get("status") != "SUCCESS":
            self._failed(stdout, stderr)
        tools = next((event.get("init", {}).get("tools") for event in events if event.get("event") == "init"), None)
        if not isinstance(tools, list) or set(tools) - {"ask_permission", "send_message"}:
            raise LLMError("Antigravity did not start the restricted writing agent. Update Antigravity CLI and test again.")
        counters = result.get("usage") or {}
        if "cache_read_tokens" in counters:
            counters["cache_read_input_tokens"] = counters["cache_read_tokens"]
        payload = result.get("structured_output") if schema else result.get("response")
        return payload, counters

    def _failed(self, stdout: bytes, stderr: bytes) -> None:
        # CLI errors can contain private prompts or account data. Return actionable categories only.
        detail = (stdout + stderr).decode(errors="replace").lower()
        if "authentication required" in detail or "not logged in" in detail or "unauthorized" in detail:
            self.verified = False
            raise LLMError(f"Sign in to {self.label} again in Settings.")
        if "refusal" in detail:
            raise LLMRefusalError(None, provider=self.label)
        if "rate limit" in detail or "quota" in detail or "usage limit" in detail:
            raise LLMError(f"{self.label} reached its usage limit.")
        raise LLMError(f"{self.label} could not complete the request. Check sign-in and model access in Settings.")

    @staticmethod
    def _env() -> dict[str, str]:
        # The sign-in and model commands use the CLI's own credential store. Inherited API tokens are excluded.
        return {key: value for key, value in os.environ.items() if key.upper() in _ENV}

    async def _run(self, args: list[str], *, cwd: Path, timeout: float, body: bytes | None = None) -> tuple[int, bytes, bytes]:
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=self._env(),
                stdin=subprocess.PIPE if body else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise LLMError(f"Could not start the CLI for {self.label}.") from exc
        # Uvicorn's Windows reload loop cannot run asyncio subprocess transports.
        worker = asyncio.create_task(asyncio.to_thread(process.communicate, body))
        try:
            out, err = await asyncio.wait_for(asyncio.shield(worker), timeout)
        except (TimeoutError, asyncio.CancelledError) as exc:
            if process.poll() is None:
                process.kill()
            await worker
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise LLMError(f"{self.label} timed out.") from exc
        return process.returncode or 0, out, err


def _object(line: bytes) -> dict[str, Any]:
    try:
        value = json.loads(line)
    except (ValueError, UnicodeError):
        return {}
    return value if isinstance(value, dict) else {}

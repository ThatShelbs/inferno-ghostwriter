"""Create and push the kit's repository with the author's own GitHub CLI (``gh``) and git.

The app never sees a GitHub token: ``gh`` keeps the author's sign-in, as Claude Code and Codex keep theirs. Every
command runs with argument lists (no shell), prompts disabled, and without the app's own secrets in its environment.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

STATUS_TTL = 60.0
_SECRETS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "GEMINI_API_KEY")
_REPO_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SIGN_IN = "gh auth login --web --git-protocol https"


class GitHubError(Exception):
    """Something the author can fix (sign in, pick another name); the message says what."""


@dataclass
class GitHubStatus:
    installed: bool
    signed_in: bool
    login: str = ""
    message: str = ""


def repo_name(text: str) -> str:
    """A valid GitHub repository name from a title or the author's input."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-.")[:100]
    return name or "hands-on-kit"


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _SECRETS}
    env.update({"GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0", "GH_NO_UPDATE_NOTIFIER": "1"})
    return env


class GitHubCLI:
    """``command`` runs gh (``["gh"]``; tests use a fake script); None = gh is not available (tests, demo mode)."""

    def __init__(self, command: list[str] | None, *, git: str | None = None) -> None:
        self.command = command
        self.git = git or shutil.which("git")
        self._status: tuple[float, GitHubStatus] | None = None

    @classmethod
    def discover(cls) -> GitHubCLI:
        found = shutil.which("gh")
        if found is None and os.name == "nt":
            default = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "GitHub CLI" / "gh.exe"
            found = str(default) if default.exists() else None
        return cls([found] if found else None)

    def _run(self, args: list[str], *, cwd: Path | None = None, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args, cwd=cwd, env=_env(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False
        )

    def _gh(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        assert self.command is not None
        return self._run([*self.command, *args], cwd=cwd)

    def _git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        if self.git is None:
            raise GitHubError("Git is not installed. Install it from git-scm.com, then try again.")
        result = self._run([self.git, *args], cwd=cwd)
        if result.returncode != 0:
            raise GitHubError(f"git {args[0]} failed: {(result.stderr or result.stdout).strip()[:300]}")
        return result

    def status(self, *, fresh: bool = False) -> GitHubStatus:
        if self._status is not None and not fresh and time.monotonic() - self._status[0] < STATUS_TTL:
            return self._status[1]
        status = self._check()
        self._status = (time.monotonic(), status)
        return status

    def _check(self) -> GitHubStatus:
        if self.command is None:
            return GitHubStatus(False, False, message="Install the GitHub CLI (cli.github.com) to push kits to GitHub.")
        try:
            if self._gh("--version").returncode != 0:
                return GitHubStatus(False, False, message="The GitHub CLI did not start.")
            if self._gh("auth", "status", "--hostname", "github.com").returncode != 0:
                return GitHubStatus(True, False, message=f"Sign in to GitHub: run `{SIGN_IN}` in a terminal.")
            user = self._gh("api", "user", "--jq", ".login")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return GitHubStatus(False, False, message=f"The GitHub CLI did not respond: {exc}")
        login = user.stdout.strip()
        if user.returncode != 0 or not login:
            return GitHubStatus(True, False, message=f"Sign in to GitHub: run `{SIGN_IN}` in a terminal.")
        return GitHubStatus(True, True, login=login)

    def _commit(self, folder: Path, message: str, login: str) -> bool:
        """Commit everything; False when nothing changed."""
        if not (folder / ".git").exists():
            self._git("init", "-b", "main", cwd=folder)
        self._git("add", "-A", cwd=folder)
        if not self._run([self.git or "git", "status", "--porcelain"], cwd=folder).stdout.strip():
            return False
        identity: list[str] = []
        if not self._run([self.git or "git", "config", "user.email"], cwd=folder).stdout.strip():
            identity = ["-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com"]
        self._git(*identity, "commit", "-q", "-m", message, cwd=folder)
        return True

    def create(self, folder: Path, *, name: str, public: bool, description: str, message: str) -> str:
        """Create the GitHub repository from the folder and push it; returns its URL."""
        status = self.status(fresh=True)
        if not status.signed_in:
            raise GitHubError(status.message)
        if not _REPO_NAME.match(name):
            raise GitHubError("Repository names use letters, numbers, dots, dashes and underscores only.")
        self._commit(folder, message, status.login)
        result = self._gh(
            "repo",
            "create",
            name,
            "--public" if public else "--private",
            "--description",
            description[:300],
            "--source",
            str(folder),
            "--remote",
            "origin",
            "--push",
            cwd=folder,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip()
            if "already exists" in error.lower():
                raise GitHubError(f"You already have a repository named {name}. Pick another name.")
            raise GitHubError(f"GitHub did not create the repository: {error[:300]}")
        found = re.search(r"https://github\.com/[\w.-]+/[\w.-]+", result.stdout + result.stderr)
        return found.group(0) if found else f"https://github.com/{status.login}/{name}"

    def update(self, folder: Path, *, message: str) -> bool:
        """Commit and push changes to the kit's existing repository; False when there was nothing new."""
        status = self.status()
        if not status.signed_in:
            raise GitHubError(status.message)
        changed = self._commit(folder, message, status.login)
        self._git("push", "-q", "origin", "main", cwd=folder)
        return changed

    async def acreate(self, folder: Path, *, name: str, public: bool, description: str, message: str) -> str:
        return await asyncio.to_thread(self.create, folder, name=name, public=public, description=description, message=message)

    async def aupdate(self, folder: Path, *, message: str) -> bool:
        return await asyncio.to_thread(self.update, folder, message=message)

    async def astatus(self, *, fresh: bool = False) -> GitHubStatus:
        return await asyncio.to_thread(self.status, fresh=fresh)

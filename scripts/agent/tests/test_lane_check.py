"""Exercise the lane checker against real disposable Git repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CHECKER = Path(".claude/skills/dev-team/lane_check.py")
GUARD = Path("scripts/agent/path_guard.py")
REGISTRY = """\
version: 2
shared_paths:
  - AGENTS.md
packages:
  - id: TEST
    branch: agent/lane
    status: active
    allowed_paths:
      - allowed/**
"""
GIT_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
)


def _env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in GIT_OVERRIDES}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=_env(),
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Lane Test")
    _git(path, "config", "user.email", "lane-test@example.invalid")
    for name in (CHECKER, GUARD):
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path / name)
    registry = path / "docs/handoff/workstreams.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(REGISTRY)
    (path / "AGENTS.md").write_text("Operating contract\n")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "base")
    _git(path, "checkout", "-qb", "agent/lane")
    return path


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    return _repo(tmp_path / "repo")


def _commit(repo: Path, name: str, content: str = "change\n") -> None:
    target = repo / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    _git(repo, "add", "--all")
    _git(repo, "commit", "-qm", "change")


def _check(
    repo: Path, base: str = "main", branch: str = "agent/lane", **env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(repo / CHECKER), base, branch],
        cwd=repo.parent,
        env={**_env(), **env},
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "name",
    ["allowed/plain.txt", "allowed/café.txt", "allowed/tab\t.txt", "allowed/line\rbreak.txt"],
)
def test_allowed_git_paths_are_decoded_without_quoting(repo: Path, name: str) -> None:
    _commit(repo, name)
    result = _check(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 changed path(s), 0 finding(s)" in result.stdout


def test_newline_paths_are_one_path_and_keep_their_shared_classification(repo: Path) -> None:
    _commit(repo, "docs/decisions/ADR\nexample.md")
    result = _check(repo)
    assert result.returncode == 1
    assert "is a shared path" in result.stdout
    assert "1 changed path(s)" in result.stdout


def test_both_rename_endpoints_are_checked(repo: Path) -> None:
    (repo / "allowed").mkdir()
    _git(repo, "mv", "AGENTS.md", "allowed/moved-contract.md")
    _git(repo, "commit", "-qm", "move contract")
    result = _check(repo)
    assert result.returncode == 1
    assert "AGENTS.md is a shared path" in result.stdout


def test_guard_changes_cannot_neutralize_the_checker(repo: Path) -> None:
    _commit(repo, str(GUARD), (repo / GUARD).read_text() + "\ndef reasons_for(*args): return []\n")
    result = _check(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "part of the path guard" in result.stdout


def test_candidate_guard_code_is_not_executed(repo: Path) -> None:
    marker = repo / "executed.txt"
    _commit(repo, str(GUARD), f"raise RuntimeError({str(marker)!r})\n")
    result = _check(repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "RuntimeError" not in result.stderr


def test_git_environment_cannot_redirect_the_check(repo: Path, tmp_path: Path) -> None:
    other = _repo(tmp_path / "other")
    _commit(repo, "AGENTS.md", "changed contract\n")
    result = _check(repo, GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "AGENTS.md is a shared path" in result.stdout


def test_the_candidate_cannot_widen_its_registry(repo: Path) -> None:
    widened = REGISTRY.replace("allowed/**", "**")
    _commit(repo, "docs/handoff/workstreams.yaml", widened)
    _commit(repo, "outside.txt")
    result = _check(repo)
    assert result.returncode == 1
    assert "outside.txt is outside the allowed_paths" in result.stdout


@pytest.mark.parametrize(("base", "branch"), [("bad-base", "agent/lane"), ("main", "main")])
def test_invalid_inputs_fail_closed(repo: Path, base: str, branch: str) -> None:
    result = _check(repo, base, branch)
    assert result.returncode == 2
    assert result.stderr

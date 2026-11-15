#!/usr/bin/env python3
"""Check a branch diff against the lane of its work package.

Usage: lane_check.py <base> <branch>   (run with python3 -I, from any directory)

Lists each path that `<base>...<branch>` changes and applies the rules of
scripts/agent/path_guard.py to it: shared paths, guard files, and the
`allowed_paths` of the package registered for the branch. The registry and guard
are read from `<base>`, so a branch cannot widen its lane or replace its checker.

Exit 0: every changed path is in the lane. Exit 1: at least one is not.
Exit 2: the check could not run (usage, git error, or no package for the branch).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    env = os.environ.copy()
    # These override -C and can silently check an unrelated checkout instead.
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
    ):
        env.pop(key, None)
    # Replacement refs can swap base blobs while leaving the printed SHA unchanged.
    done = subprocess.run(  # nosec B603 B607
        ["git", "--no-replace-objects", "-C", str(ROOT), *args],
        capture_output=True,
        check=False,
        env=env,
    )
    if done.returncode != 0:
        print(
            f"lane_check: git {' '.join(args)} failed: {os.fsdecode(done.stderr).strip()}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return os.fsdecode(done.stdout)


def _guard(base: str) -> ModuleType:
    # Never import code from the candidate worktree, including adjacent helpers.
    # The scheduler supplies an approved base; -I keeps its stdlib imports isolated.
    source = _git("show", f"{base}:scripts/agent/path_guard.py")
    with tempfile.TemporaryDirectory(prefix="lane-guard-") as directory:
        path = Path(directory, "path_guard.py")
        path.write_text(source)
        spec = importlib.util.spec_from_file_location("path_guard", path)
        if spec is None or spec.loader is None:
            print("lane_check: cannot load the approved-base path guard", file=sys.stderr)
            raise SystemExit(2)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
    return guard


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: lane_check.py <base> <branch>", file=sys.stderr)
        return 2
    base, branch = sys.argv[1], sys.argv[2]
    base = _git("rev-parse", "--verify", f"{base}^{{commit}}").strip()
    head = _git("rev-parse", "--verify", f"{branch}^{{commit}}").strip()
    path_guard = _guard(base)
    registry = _git("show", f"{base}:docs/handoff/workstreams.yaml")
    packages = path_guard.parse_packages(registry)
    if not path_guard.owners_of(branch, packages):
        print(f"lane_check: no package in workstreams.yaml uses branch {branch}", file=sys.stderr)
        return 2
    shared = path_guard.parse_shared_paths(registry)
    # --no-renames: a rename lists its source too, so moving a shared file into the lane is caught.
    names = _git("diff", "--name-only", "--no-renames", "-z", f"{base}...{head}")
    changed = [p for p in names.split("\0") if p]
    reasons = [r for p in changed for r in path_guard.reasons_for(p, branch, packages, shared)]
    for reason in reasons:
        print(reason)
    print(f"lane_check: checked head {head} against base {base}")
    print(f"lane_check: {len(changed)} changed path(s), {len(reasons)} finding(s)")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())

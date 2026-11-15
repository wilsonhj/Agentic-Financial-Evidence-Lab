#!/usr/bin/env python3
"""Check a branch diff against the lane of its work package.

Usage: lane_check.py <base> <branch>   (run with python3 -I, from any directory)

Lists each path that `<base>...<branch>` changes and applies the rules of
scripts/agent/path_guard.py to it: shared paths, guard files, and the
`allowed_paths` of the package registered for the branch. The registry is read
from `<base>`, so a branch cannot widen its own lane.

Exit 0: every changed path is in the lane. Exit 1: at least one is not.
Exit 2: the check could not run (usage, git error, or no package for the branch).
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "agent"))

import path_guard  # noqa: E402


def _git(*args: str) -> str:
    done = subprocess.run(  # nosec B603 B607
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        print(f"lane_check: git {' '.join(args)} failed: {done.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return done.stdout


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: lane_check.py <base> <branch>", file=sys.stderr)
        return 2
    base, branch = sys.argv[1], sys.argv[2]
    registry = _git("show", f"{base}:docs/handoff/workstreams.yaml")
    packages = path_guard.parse_packages(registry)
    if not path_guard.owners_of(branch, packages):
        print(f"lane_check: no package in workstreams.yaml uses branch {branch}", file=sys.stderr)
        return 2
    shared = path_guard.parse_shared_paths(registry)
    # --no-renames: a rename lists its source too, so moving a shared file into the lane is caught.
    names = _git("diff", "--name-only", "--no-renames", f"{base}...{branch}")
    changed = [p for p in names.splitlines() if p]
    reasons = [r for p in changed for r in path_guard.reasons_for(p, branch, packages, shared)]
    for reason in reasons:
        print(reason)
    print(f"lane_check: {len(changed)} changed path(s), {len(reasons)} finding(s)")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())

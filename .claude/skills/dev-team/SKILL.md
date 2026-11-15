---
name: dev-team
description: Schedule one work package through the agent team. Runs the dispatch check, the implementer, the lane check, and the read-only specialist reviewers, then reports to the integration lead.
argument-hint: <package-id or issue-number>
disable-model-invocation: true
---

# Dev team

Schedule the work package `$ARGUMENTS`.

You are the scheduler. Follow `docs/handoff/FABLE_ORCHESTRATION.md`. You do
not write code. You do not decide architecture. You do not merge. The
integration lead is the only authority.

Run one package for each invocation.

## 1. Reconcile

1. Do step 1 of the resume sequence in `docs/handoff/README.md`.
2. Find the package in `docs/handoff/workstreams.yaml` by its ID or its issue.
3. If no package matches, stop. Report that to the integration lead.

## 2. Check the dispatch rules

Apply the dispatch checklist in `docs/handoff/README.md` to the package. Apply
the limit on concurrent packages from the same file.

If one item fails, stop. Report the item and the evidence. A `blocked` status
is not permission to work, also when the old blocker is gone.

## 3. Dispatch the implementer

Start one `implementer` subagent. Give it the worker prompt from
`docs/handoff/FABLE_ORCHESTRATION.md` with every field filled. Use the values
in `workstreams.yaml` and the issue. Do not start two implementers on one
branch.

If the implementer reports a blocker, go to step 7.

## 4. Run the lane check

```bash
python3 -I .claude/skills/dev-team/lane_check.py <base-sha> <working-branch>
```

- Exit 0: continue.
- Exit 1: stop. Do not start the reviewers. Report each path that the check
  printed. A shared path needs the `contract-change` process in `AGENTS.md`.
- Exit 2: the check did not run. Report the error text.

## 5. Write the diff file

Write `git diff <base-sha>...<working-branch>` to a file in a temporary
directory outside the repository. Record the absolute path.

The reviewers read files in the worktree of the implementer. If the result of
the implementer gives no worktree path, add a detached worktree of the working
branch in the same temporary directory.

## 6. Start the reviewers

Start `security-reviewer` and `domain-integrity-reviewer` in one message, so
that they run at the same time. Give each one:

- The path of the diff file and the path of the worktree.
- The package ID and the allowed paths.

Give `domain-integrity-reviewer` the acceptance checks also, with the command
and the result that the implementer reported for each one.

Do not give a reviewer the reasoning or the summary of the implementer. A
reviewer must judge the diff, not the explanation.

If a reviewer reports `BLOCK`, start a new `implementer` run on the same
branch one time. Give it the findings. Then do steps 4 to 6 again. If a
reviewer reports `BLOCK` a second time, stop and go to step 7. Recommend the
`needs-decision` label.

## 7. Report to the integration lead

Give these items:

- The package ID, the working branch, the head commit SHA, and the draft PR.
- The result of the lane check.
- Each acceptance check with its result.
- The verdict of each reviewer and every finding, complete. Do not shorten a
  finding or remove one.
- Each decision that the integration lead must make.

Record a blocker on the GitHub issue only when the integration lead tells you
to.

## Limits

- Do not merge, approve, or close a PR.
- Do not mark a Spec Kit task complete.
- Do not change a package status or a dependency in `workstreams.yaml`.
- Do not edit a shared path.
- Do not settle a disagreement between a reviewer and the implementer. Report
  the two positions.

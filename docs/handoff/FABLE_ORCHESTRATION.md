# Fable orchestration protocol

Fable is the scheduler and recovery coordinator; Claude Code agents are isolated workers. Fable does not make product architecture decisions or merge code.

## Scheduling loop

Resume and recovery follow the single [resume sequence](README.md#resume-sequence)
in the handoff README; this loop adds only Fable's scheduling duties.

1. Load `workstreams.yaml`, `STATUS.md`, and GitHub issue/PR state (resume sequence step 1).
2. Mark a package ready only when all dependencies are merged and paths do not overlap active work.
3. Create one worktree and the declared branch for one Claude Code agent.
4. Give the agent its issue, task IDs, allowed paths, frozen inputs, acceptance checks, and credential policy.
5. Require a draft PR and first pushed checkpoint before scheduling another risky package.
6. Poll PR checks and issue heartbeats. Record blockers in GitHub, not private orchestration memory.
7. Send passing PRs to an independent reviewer and then the integration lead.
8. After merge, ask the integration lead to update task checkboxes, package status, and `STATUS.md`.

## Agent team

Claude Code sessions run this protocol with the definitions below. The team
has one human authority, one scheduler, one builder, and read-only reviewers.

| Role | Definition | Writes code |
|---|---|---|
| Integration lead | The repository owner (`.github/CODEOWNERS`) | Yes. Merges and decides. |
| Scheduler | [`/dev-team` skill](../../.claude/skills/dev-team/SKILL.md) | No |
| Builder | [`implementer`](../../.claude/agents/implementer.md) | Only in the `allowed_paths` of its package |
| Reviewer | [`security-reviewer`](../../.claude/agents/security-reviewer.md) | No. It has only the Read, Grep, and Glob tools. |
| Reviewer | [`domain-integrity-reviewer`](../../.claude/agents/domain-integrity-reviewer.md) | No. It has only the Read, Grep, and Glob tools. |

The scheduler runs `.claude/skills/dev-team/lane_check.py` before review. The
script applies the rules of `scripts/agent/path_guard.py` to the diff of the
branch. A reviewer gets the diff and the brief, not the reasoning of the
builder. Add a reviewer only after a failure that it can prevent occurs more
than one time.

The specialist reviews are internal advice and do not replace required
different-vendor review or integration-lead approval. Preserve the applicable
merge gates, including
[ADR-0034](../decisions/ADR-0034-public-read-only-evidence-surface.md)
for MCP work; a team using one vendor cannot satisfy that gate for its own author.

## Worker prompt

```text
Repository: wilsonhj/financial-evidence-lab
Package: <id>
Issue: <url>
Base branch/SHA: <branch>@<sha>
Working branch: <branch>
Task IDs: <ids>
Dependencies: <merged packages>
Allowed paths: <paths>
Forbidden/shared paths: <paths>
Acceptance checks: <commands and criteria>
Credentials: mock-only | approved env-var names

Read AGENTS.md and CLAUDE.md, then follow the resume sequence in
docs/handoff/README.md. Implement only this package. Open a draft PR early,
push bounded checkpoints, and leave a complete handoff if blocked. Never include secrets.
```

## Failure and reassignment

- A stalled agent must push its latest safe checkpoint and describe the blocker.
- Do not assign two agents to the same branch.
- Reassignment uses a new branch from the last reviewed checkpoint unless the prior PR is cleanly resumable.
- After two failed attempts, mark the issue `needs-decision` and stop automatic retries.
- Contract disagreements always escalate to an ADR; Fable never resolves them by majority vote.

## Credential policy

Fable may transmit environment-variable names and setup instructions, never secret values. Live provider tests are separate, explicitly labeled work. GitHub, Railway, and Supabase secret stores are the only intended delivery mechanisms.

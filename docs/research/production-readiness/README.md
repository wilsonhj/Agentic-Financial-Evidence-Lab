# Production readiness research and implementation proposal

**Status: proposed for external review.** Research date: 2026-11-14.
Repository baseline: `33c6a635c05460624c894d00363d8710a780adc3`.
Tracking issue: [#419](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/419).

The owner requested research, independent verification and a reviewable
implementation specification for production readiness, SOC 2 Type II,
vulnerability scanning, retained security evidence, horizontal scaling,
structured logging and containerization.

This package is authorized documentation work. Its implementation requirements
and package IDs are proposals, not a second canonical task ledger or dispatch
registration. The [parent specification](../../../specs/001-financial-evidence-lab/spec.md),
[constitution](../../../.specify/memory/constitution.md), accepted
[architecture decisions](../../decisions/README.md), and current
[handoff process](../../handoff/README.md) govern conflicts.
No architecture decision, hosted deployment, credential use, paid call, immutable
retention configuration or implementation-package dispatch is authorized by
merging these research documents.

The proposed specification is kept here until external review and the applicable
ADR/lead gates are satisfied. Moving it into `specs/**`, modifying shared
contracts or adopting a new stack component requires the repository's separate
approval process. This research branch was directly requested by the owner;
it does not modify the dispatch registry.

**Reading order**

1. [Research report](research-report.md): conclusions, verified baseline and priorities.
2. [Implementation specification](implementation-spec.md): testable proposed requirements.
3. [Parallel work packages](parallel-work-packages.md): dependencies, exclusive ownership and handoffs.
4. [Verification plan](verification-plan.md): independent acceptance and fault injection.
5. [Review record](review-record.md): research method, reviewer findings and limitations.

**Detailed research**

- [SOC 2 and retained security evidence](soc2-and-evidence.md).
- [Security scanning and release evidence](security-ci.md).
- [Structured logging](structured-logging.md).
- [Containers and horizontal scaling](containers-and-scaling.md).

All claims about existing code refer to the pinned baseline, not to an
unverified hosted deployment. External sources are dated in the topic documents.
Open PRs can supersede a baseline finding; agents must reconcile them before
implementing. Research agents and internal reviewers are OpenAI models and do
not constitute the repository's required different-vendor approval.

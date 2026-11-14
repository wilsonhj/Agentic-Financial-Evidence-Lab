# Application load testing and load balancing

**Status: implementation proposal; no capacity certification.** Research date:
2026-11-14. Repository baseline: `33c6a635c05460624c894d00363d8710a780adc3`.
Tracking issue: [#421](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/421).

The owner requested researched implementation requirements, independent subagent
verification and a repository commit. This documentation-only branch is directly
authorized by that request; it does not register or dispatch implementation work.
The [canonical specification](../../../specs/001-financial-evidence-lab/spec.md),
[constitution](../../../.specify/memory/constitution.md), accepted
[ADRs](../../decisions/README.md) and [handoff process](../../handoff/README.md)
govern conflicts. New requirements here are proposals, not amendments to existing
release gates. No application, infrastructure, migration or contract changes are
included. Implementation of shared-path or architecture changes still requires
the applicable accepted ADR, contract-change and integration-lead review.

Read in order:

1. [Implementation specification](implementation-spec.md): workloads, architecture,
   acceptance, rollout and proposed delivery slices.
2. [Source register](sources.md): claim-level evidence, official documentation,
   derivations and reproducible checks.
3. [Independent review record](review-record.md): review findings and dispositions.
4. [Evidence manifest](evidence.json): hashes of the repository sources and dated
   external-document excerpts used in this research.

Related [PR #420](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/420)
is an **unmerged proposal**, observed at
`1ab36715cb6f229e58bcf4716b630fe9fa74a32b`. Its
[scaling design](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/1ab36715cb6f229e58bcf4716b630fe9fa74a32b/docs/research/production-readiness/containers-and-scaling.md)
and [ownership map](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/1ab36715cb6f229e58bcf4716b630fe9fa74a32b/docs/research/production-readiness/parallel-work-packages.md)
cover storage, admission, lifecycle and telemetry. This package specializes their
capacity-testing protocol. Reconcile both proposals before assigning one owner
per implementation path; do not dispatch two implementations of the same change.

At this baseline, the evidence supports neither a 1,000-, 5,000- nor 10,000-user
capacity claim. The current extraction benchmark is a local synthetic 25-client
test with a failed review-latency gate. Public web identity and hosted extraction
also have functional prerequisites. These are source observations, not a claim
that higher capacity is impossible or that a particular hosted account was tested.

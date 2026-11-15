# Research verification record

Research date: 2026-11-14. Baseline: `33c6a63`.
Tracking issue: [#419](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/419).

The owner requested parallel research, independent verification and publication
for external review. Four topic researchers used GPT 6.1 Sol/Terra; GPT 6 Astra
provided orchestration advice. Independent Terra and Sol reviewers cross-checked
the integrated design, source paths and selected primary references. Astra reviewed
the dependency graph and governance. These are all OpenAI models: this work does
not satisfy a different-vendor approval or an independent CPA examination.

**Research verification**

The topic notes cite dated primary documentation and pinned repository sources.
Researchers inspected actual CI, logging, runtime-installation, queue, storage,
rate-limit and deployment paths. Independent review sampled GitHub workflow-run
semantics, AWS OIDC subjects, Object Lock, Railway health behavior, Next tracing,
the parent retention requirements and the API's local storage reader.
No cloud configuration, vulnerability scanner execution, container build,
penetration test, deployment or production access was performed.

**Findings and resolutions**

| Finding | Resolution in this proposal |
| --- | --- |
| Upstream gate waited for a collector triggered only after upstream completion | Selected completion-triggered collector with a separate commit-bound required evidence check; upstream local gate completes first; missing/overdue evidence blocks release |
| Real archive provisioning and identity acceptance had no integrated owner | Added PRO-20 with explicit cloud/retention authorization, provider adapter, OIDC claim design, permission negatives and reconciliation tests |
| OIDC requirements assumed clouds enforce every GitHub claim | Added provider-specific subject/claim design and same-repo wrong-workflow/ref/environment/audience denial tests; environment subject differences are explicit |
| Readiness review preceded release/hosted evidence | PRO-19 now reviews release/archive evidence for pilot entry; PRO-21 independently reviews actual PRO-17 hosted results before production recommendation |
| Scanner status enums disagreed | Standardized clean/findings/failed/incomplete, lossless reason/native-state fields and shared adapter fixtures |
| SAST/DAST work lacked an integrated package | Added PRO-22, with PRO-13 retaining exclusive workflow ownership |
| Shared storage omitted the API's local-file reader | PRO-10 owns reader and extraction-evidence binding plus worker-to-other-API-replica citation acceptance |
| Durable request-to-job correlation lacked queue/enqueue ownership | Added PRO-23 and a PRO-00 metadata contract; PRO-10/11 consume it after merge |
| Final image might omit migration scripts/SQL despite claiming one-shot migration support | IMG-01/PRO-05 require explicit assets and real apply/check from the final digest against a fixture database |
| Web correlation omitted transports that rebuild outbound headers | PRO-12 now owns data/Observatory/extraction transports, named server bindings and per-transport header-capture tests |
| Old same-run collector preference contradicted selected topology | Removed stale preference; same-run design is explicitly a separate reviewed alternative |
| Round-two #420: same-SHA rerun could reuse old archive success; stale collectors could publish last | Added exact-attempt invalidation/admission acknowledgement, one serialized App publisher, durable generations/execution slots, stale/late-write fencing and cancellation/reconciliation semantics; SEC-08 blocks activation pending actual same-SHA native-check/App-bound branch-rule acceptance before ACK and while archival is paused |
| Round-two #420: real API initialization and extraction/calculation telemetry were absent from the integrated ownership map | PRO-10 explicitly owns `observability.py`/Sentry tests; PRO-11 owns both telemetry adapters and existing/new tests, with actual-entrypoint canaries, recording-sink compatibility and full emitter inventory under LOG-08; existing dependencies carry those checkpoints into release/scale/recovery |

Terra and Astra re-review confirmed their original material findings were addressed
in the proposed design; the remaining stale preference was then removed. Sol
cross-review confirmed its first three corrections and identified the additional
web-transport ownership gap, which was assigned explicitly. These reviews assess
the specification, not an implemented or hosted system.

The 2026-11-15 round-two revision addresses the two remaining proposed-design
findings from exact prior head `1ab3671`. It rechecked GitHub's workflow-event
and protected-branch primary documentation through the Tavily search skill;
extraction returned no failed URLs. GitHub explicitly excludes reruns from
`workflow_run: requested`; expected publisher App binding does not select a receipt
attempt. The documented handshake starts its guarantee at invalidation ACK.
Before-ACK native required-check behavior remains an explicit hosted activation
criterion, including individual/failed-job reruns; no automatic invalidation or
zero-window same-SHA guarantee is claimed. An unsuccessful experiment requires a
separately reviewed authority design before enabling this topology.

**Local documentation checks**

- Markdownlint CLI2 0.18.1, using the repository configuration: passed for all
  ten research documents on the 2026-11-15 revision; the initial publication
  previously checked all 11 changed Markdown files including the parent index.
- JSON parse checks: both fenced JSON examples parsed.
- Relative file-link/anchor check: all 109 relative links across the ten research
  documents resolved on the 2026-11-15 revision.
- Dependency validation: all 24 PRO package IDs resolve; graph is acyclic.
- Repository documentation index: 178 tracked Markdown files reachable, 18
  documented exclusions; index-check regression suite passed.
- `git diff --check`: passed on the 2026-11-15 revision; repeat on the final staged diff.
- Scope check: documentation only under `docs/research/production-readiness/**`
  and its parent research index. No application, workflow, canonical ledger,
  shared schema, ADR or live configuration was modified.

The PR records the current pushed SHA and remote CI results. A fresh full
application/load/hosted run is not claimed for a documentation-only change.
Repository CI can run its existing suites independently of these local checks.

**Remaining external decisions**

External review must settle control scope/owners, archive and retention policy,
provider-specific identity proof, exact-image platform feasibility, RPO/RTO,
new dependency/stack ADRs and package registration. Real tests must establish
check-SHA/attempt binding, collector cancellation recovery, platform permissions,
retention/key recovery, image lifecycle and measured scale. No pending decision
is silently treated as accepted.

Return to the [research index](README.md), [implementation specification](implementation-spec.md)
and [verification plan](verification-plan.md).

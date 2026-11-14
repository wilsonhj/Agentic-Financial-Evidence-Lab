# Parallel implementation packages

**Proposal only:** these `PRO-*` IDs are planning handles, not canonical task IDs,
registered issues or ready-to-dispatch packages. Baseline `33c6a63`; issue
[#419](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/419).
The [parent specification](../../../specs/001-financial-evidence-lab/spec.md),
[AGENTS.md](../../../AGENTS.md) and [handoff process](../../handoff/README.md) govern.

Use at most **three implementation agents plus a coordinator** for this program
unless the lead explicitly revises the limit. Additional research/review agents
can work without owning implementation files. This conservative limit respects
the MCP amendment and the broader four-package handoff ceiling. It avoids
interpreting the latter as automatic permission for four simultaneous writers.

Topic documents contain candidate slices; the integrated package table here is
the proposed scheduling map. Merge or rename topic-local labels during registration,
never dispatch both sets as duplicate work.

**Operating protocol**

Before each dispatch the lead creates the scoped issue, registers branch and exact
paths, checks current open-PR ownership, approves relevant contracts/ADRs and
confirms dependencies are merged into the branch base. Use an isolated worktree.
No agent edits another package's files. Shared files have one assigned writer at
a time, even when hunks appear independent.

All packages use recorded fixtures and local disposable environments unless
explicitly marked hosted. A contract consumer may develop against accepted mocks
before a producer merges, but its final integration test must run against the
merged producer. Package dependency edges below are merge gates; mock development
does not erase them. Prefer bounded PRs around 600 changed lines; split a package
into sequential checkpoints when needed without inventing parallel shared owners.

Each handoff includes issue, branch, commit, dependency SHAs, schema/fixture versions,
owned paths, tests and commands, artifacts, known limitations, next step and reviewer.
Do not put secret values in the handoff. Only the lead updates canonical state.

**Contract freeze and decision gates**

PRO-00 must freeze five small, independently versioned interfaces before consumers
start: logging envelope/privacy fixtures; scanner result and evidence receipt;
runtime/release manifest; storage/admission behavior; and durable queue correlation
metadata (enqueue, claim and retry propagation without changing evidence hashes).
Existing interfaces
should be retained where sufficient. Shared schemas belong to their registered
contract owner, not to every consumer.

Cloud provider, immutable-retention duration and hosted budget decisions may remain
open while offline adapters and fixture tests proceed. Changes to the frozen
application/storage contracts, database migrations, architecture or `specs/**`
need the applicable accepted ADR and lead review. Root dependency/configuration
changes follow their specific authorization rule. Never claim this research PR
itself accepted those decisions.

**Dependency and ownership table**

Paths are candidate exact ownership for the future issue, relative to repo root.
New directories are explicitly proposals. The lead may narrow them, but must not
broaden them silently. “None” means no engineering predecessor, not automatic
authorization.

| ID | Deliverable | Merge dependencies | Candidate exclusive ownership |
| --- | --- | --- | --- |
| PRO-00 | Minimal interfaces, fixtures and decision records | None | Named new logging/evidence/release schemas and fixtures under `packages/contracts/`; applicable named ADR/spec files; integration lead owns registry/root registration |
| PRO-01 | Locked-dependency and image scanner adapters | PRO-00 | New `scripts/security/scans/**`, matching `scripts/security/tests/scans/**`; narrow JSON-output extension to `scripts/audit-bulk.mjs` and its existing tests |
| PRO-02 | Evidence validation, local archive adapter and receipt verification | PRO-00 | New `scripts/security/evidence/**`, `scripts/security/tests/evidence/**` |
| PRO-03 | Python logging core and pretty renderer | PRO-00 | New `packages/observability/**`; package registration only by lead in a serialized shared-file change |
| PRO-04 | TypeScript logging core | PRO-00 | New `apps/web/src/lib/observability/**` and tests within that subtree |
| PRO-05 | Python API/worker image and fixture smoke | PRO-00 | New `infra/containers/python/**`, `infra/containers/tests/python/**`; existing installer changes only in a separately assigned follow-up |
| PRO-06 | Web image and standalone tracing | PRO-00 | New `infra/containers/web/**`, `infra/containers/tests/web/**`; `apps/web/next.config.ts` |
| PRO-07 | Shared immutable object-store adapter | PRO-00 | New `workers/src/fel_workers/object_storage.py`, `workers/tests/test_object_storage.py`; existing storage protocol remains frozen |
| PRO-08 | Shared admission/cost reservation prototype | PRO-00 | New `packages/admission/**`; any schema migration is separately registered and merged before implementation requiring it |
| PRO-09 | Independent acceptance harness and adversarial fixtures | PRO-00 | New `evals/production/**`; collection/configuration wired only by lead |
| PRO-10 | API logging, storage-reader, pool/role, health and admission integration | PRO-03, PRO-07, PRO-08, PRO-23 | Named API `logging.py`, `middleware.py`, `main.py`, `db.py`, `ratelimit.py`, `retrieval.py`, `reader.py`, `extraction/evidence.py`, `config.py` files and named tests; narrow sub-PRs |
| PRO-11 | Worker logging, storage/admission binding and drain | PRO-03, PRO-07, PRO-08, PRO-23 | Named worker `__main__.py`, `consumer.py`, `health.py`, `http.py`, `ingestion/sec_client.py` and named tests; narrow sub-PRs |
| PRO-12 | Web request correlation and safe telemetry integration | PRO-04 | `apps/web/src/proxy.ts`, named telemetry route/validation/tests; `lib/data/http-source.ts`, `lib/observatory/http-source.ts`, `lib/extraction/transport.ts` and their tests under `apps/web/src/`; named server route bindings; do not edit `next.config.ts` |
| PRO-13 | CI scan/evidence wiring and required gate | PRO-01, PRO-02, PRO-05, PRO-06, PRO-22 | Named `.github/workflows/ci.yml`, `advisories.yml`, new security workflow/collector, required-check documentation; sole CI writer; local acceptance does not establish real archival |
| PRO-14 | Release orchestration and migration separation | PRO-05, PRO-06, PRO-10, PRO-11, PRO-12, PRO-13 | New named release workflow/scripts and `infra/railway/{api,web,worker}.json`; serialize all `.github/**` and root edits after PRO-13 |
| PRO-15 | Multi-replica acceptance results | PRO-05, PRO-06, PRO-09, PRO-10, PRO-11, PRO-12 | New result reports under `docs/research/production-readiness/acceptance/scale/`; fixture defects returned to PRO-09 owner |
| PRO-16 | Restore and failure-recovery acceptance results | PRO-05, PRO-06, PRO-07, PRO-09, PRO-10, PRO-11 | New result reports under `docs/research/production-readiness/acceptance/recovery/`; fixture defects returned to PRO-09 owner |
| PRO-17 | Authorized hosted pilot acceptance | PRO-14, PRO-15, PRO-16, PRO-19, PRO-20 | Named `docs/runbooks/production/**` and sanitized hosted evidence receipts; actual cloud changes only with scoped authorization |
| PRO-18 | Organizational controls, ownership and evidence operations | PRO-00 | New `docs/security/controls/**` for public-safe policy metadata; restricted personnel/auditor evidence stays outside the public repo |
| PRO-19 | Independent pre-pilot readiness and evidence-population review | PRO-13, PRO-14, PRO-15, PRO-16, PRO-18, PRO-20 | New review records under `docs/research/production-readiness/acceptance/review/pre-pilot/`; read-only producer access; authorizes no production release |
| PRO-20 | Real evidence archive, identity and reconciliation acceptance | PRO-02, PRO-18 | New `infra/security-evidence/**`, cloud archive adapter under `scripts/security/archive-cloud/**`, matching isolated tests and named archive runbook; scoped cloud/budget/retention authorization required |
| PRO-21 | Independent post-pilot release review | PRO-17 | New `docs/research/production-readiness/acceptance/review/post-pilot/**`; read-only verification of actual hosted evidence before a separate production promotion decision |
| PRO-22 | SAST language coverage and controlled DAST adapters/fixtures | PRO-00 | New `scripts/security/analysis/**` and its tests; reusable CodeQL configuration and local synthetic DAST target here; PRO-13 exclusively owns workflow wiring |
| PRO-23 | Durable request-to-job correlation propagation | PRO-00, PRO-03 | `workers/src/fel_workers/queue.py`, `apps/api/app/extraction/runs.py` and specifically named queue/enqueue tests; approved schema migration is a separate PRO-00-owned prerequisite if needed |

The exact existing filenames in PRO-10/11/12 must be resolved from current main
during issue registration. Their scopes are intentionally integration-owned;
authors of PRO-03/04/07/08 must not preemptively wire themselves into those files.
PRO-10/11 each require separate reviewable PR checkpoints if the owned integration
cannot fit a small change. The coordinator owns root build contexts/ignore files,
workspace/package lists, dependency locks and shared test collection. Those
mechanical changes must land before consumers need them, without parallel writers.

PRO-12's issue must enumerate every outbound HTTP transport and server binding
that propagates correlation, including extraction catch-all and event routes and
the corresponding data/Observatory server callers. The named transports currently
construct fresh request headers; a formatter or proxy-only change cannot provide
web-to-API correlation. Resolve this exact list before dispatch, and test every
transport with a downstream header-capture fixture. Keep identity credentials
separate from validated correlation metadata and never forward it to arbitrary origins.

**Existing-work collision register**

| Existing owner or gate | Affected proposal | Rule |
| --- | --- | --- |
| #393 publication ingestion and its `workers/tests/**` claim; #410/#411/#412 repairs | PRO-07, PRO-11, PRO-23 | Wait for ownership release or explicitly narrow/reassign tests; never overlap the broad claim |
| #395 evidence-read, #396 verifier, #397 MCP mount | PRO-03, PRO-10, PRO-14 | Preserve their frozen contracts and mount semantics; serialize any common API/root edits |
| #394 API cutoff predicates and #409/#412 API repairs | PRO-10, PRO-23 | Reconcile merged fixes and broad extraction ownership before runtime integration; do not overwrite security fixes |
| #324 public sessions/BYOK and #292 production identity | PRO-10, PRO-12, PRO-17 | Reuse those owners; this proposal does not independently rebuild authentication |
| #191 usage accounting and #195 provider runtime | PRO-08, PRO-10, PRO-11 | Agree atomic reservation/accounting interface with current owners |
| #108 hosted reader/storage; #177 live corpus; #62 calibration; #362 hosted extraction | PRO-07, PRO-17 | Preserve credentials, product and hosted acceptance dependencies |
| #203 second CODEOWNER/hosted observability | PRO-13, PRO-18 | Reuse the tracking issue and acceptance evidence rather than duplicate it |
| #413 dispatch reconciliation | PRO-00 | Read its current merged state before registering work; do not treat its historical prose as a new authorization |

**Independent acceptance per package**

| ID | Producer output and smallest meaningful acceptance |
| --- | --- |
| PRO-00 | Versioned schemas/examples, error/status enums, compatibility rules and an approved decision register; valid, malformed, malicious and missing-field fixtures |
| PRO-01 | Identical adapter envelope for JS/Python/image scans; simulated vulnerable/clean/unreachable/malformed/timeout/no-packages fixtures; all adapters attempted after one failure |
| PRO-02 | Validated reports and detached trusted receipts; reject forged run/commit/destination, traversal, zip bomb, bad hashes and missing reports; recover idempotently from duplicate delivery |
| PRO-03 | Python event formatter/context API; concurrent tenant tasks, cancellation, newline injection, redaction failure and queue saturation tests; pretty output must preserve identifiers |
| PRO-04 | TypeScript parity for the same fixtures; no browser secrets, no raw body/URL/error leakage; asynchronous context reset |
| PRO-05 | Final-image isolated imports/resources, migration runner and SQL assets with apply/check fixture, non-root user, no build tools/secrets, declared writable paths, configured port and signal smoke; record digest |
| PRO-06 | Final-image standalone server, static assets and shared-contract route; build without hosted credentials; non-root/read-only smoke with explicit cache paths |
| PRO-07 | Two-client identical/conflicting-write races, cross-client reads, checksum corruption, permission denial, migration checksum and restore fixtures |
| PRO-08 | Two-process global quota and cost reservation invariants, retries, clock/backend faults and recovery; measured contention; no unapproved paid call |
| PRO-09 | Harness interface, deterministic fixtures/seeds, expected-failure demonstrations and isolated cleanup; imported producer implementations are forbidden |
| PRO-10 | API request→job correlation, role/claim reset after errors, bounded pools, safe health, shared quota enforcement, shared-object reader/extraction reads and preserved REST/MCP separation |
| PRO-11 | Worker crash/reclaim, stale-lease denied writes, signal drain, idempotent side effects, shared SEC allowance and no mock mode on a production-target fixture |
| PRO-12 | Browser→web→API correlation, bounded telemetry and safe Sentry forwarding; hostile header/body/log injection cases |
| PRO-13 | Inject a vulnerable dependency, scanner crash, omitted artifact and archive outage; each must produce evidence and the correct failing required gate |
| PRO-14 | Build-once deployment manifest, signature/provenance verification, one-shot migration identity, rollback compatibility and rejected digest mismatch using staging fixtures |
| PRO-15 | Reproducible one/two/overlap-replica results with latency, correctness, connection ceilings, quotas, cursor-key rotation and stream resume |
| PRO-16 | Timed isolated DB+object restoration, key/config/role reconstruction, verified citations and retained-pin replay; partial/missing-object recovery fails acceptance |
| PRO-17 | Platform-observed digest/roles/health/grace, production identity/provider/storage proof and selected product's live gates; no code-only substitute |
| PRO-18 | Owner/frequency/evidence matrix, access/offboarding and incident exercises, vendor/risk/retention decisions, overdue-control reporting |
| PRO-19 | Independent sampling of local/release/archive results and missing-run population; pilot-entry recommendation, not hosted-readiness or SOC attestation |
| PRO-20 | Approved archive and provider-specific OIDC design; prove same-repo wrong-workflow/ref/environment/audience denial, scoped writes, forbidden deletion/overwrite, key recovery, retention/readback, catch-up and missing-run alerts in an authorized disposable target |
| PRO-21 | Independently sample actual hosted digest, migration, identity, storage, quota, lifecycle and recovery evidence; unresolved failures block production recommendation; no SOC attestation claim |
| PRO-22 | Python/JS analysis coverage and seeded SAST findings; bounded local DAST/auth fixture, wrong-host/unavailable-target rejection; licensing/scope decided before making a new gate required |
| PRO-23 | Enqueue→claim→retry correlation survives process restart; old envelopes remain compatible, hostile metadata is bounded and no tenant/context leaks or changed financial hashes |

**Efficient scheduling**

After PRO-00, start PRO-01, PRO-03 and PRO-05 in parallel. Refill those lanes with
PRO-02, PRO-04 and PRO-06 as writers finish. PRO-07/08/09 then run independently
subject to existing ownership release. PRO-18 can proceed as organizational
research/control work without claiming implementation files.

PRO-22 and PRO-23 refill available offline slots after their prerequisites.
PRO-10/11/12 integrate disjoint service boundaries after PRO-23. PRO-13 owns CI edits;
PRO-14 follows its shared-file release. PRO-15 and PRO-16 can verify the same
immutable local artifacts independently, without waiting for hosted provisioning.
PRO-20 separately provisions/verifies the evidence archive under explicit authority;
offline CI can use local fixtures but production gate activation waits for it.
PRO-19 reviews local/release/archive evidence before PRO-17's separately authorized
hosted pilot; PRO-21 reviews the pilot results before production promotion.
A shorter critical path is acceptable when dependencies and file ownership
permit it; do not wait for an entire wave if one package is ready.

**Asynchronous review and stop conditions**

Reviewers receive immutable commit/artifact IDs and fixtures, not a chat-only
claim that tests passed. Reproduce at least one negative acceptance case and
verify the producer cannot forge its own trusted receipt. Report findings with
exact paths, severity and reproducible conditions. Authors fix within their own
package; reviewers do not patch another live worktree.

Pause only the affected package for unresolved interface semantics, missing
credentials, unapproved paid/hosted changes, inaccessible dependency commits,
expired exceptions or ownership conflicts. Continue independent approved work.
Cross-vendor and integration-lead gates remain as the repository requires.
Record a dated limitation when platform evidence cannot be obtained; never
substitute a documentation link for a successful hosted test.

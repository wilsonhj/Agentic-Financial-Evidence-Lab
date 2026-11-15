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
start: logging envelope/privacy fixtures; scanner result, evidence receipt and
exact-attempt admission/publisher generation protocol;
runtime/release manifest; storage/admission behavior; and durable queue correlation
metadata (enqueue, claim and retry propagation without changing evidence hashes).
Existing interfaces
should be retained where sufficient. Shared schemas belong to their registered
contract owner, not to every consumer.

Cloud provider, immutable-retention duration and hosted budget decisions may remain
open while offline adapters and fixture tests proceed. Apply the
[AGENTS.md shared-path rules](../../../AGENTS.md#shared-paths) at registration:
contracts, migrations, `specs/**` and `docs/decisions/**` require `contract-change`,
an accepted ADR and integration-lead review. Changes to `.github/**` require
`contract-change` and lead review, with an accepted ADR when the change also
adopts architecture or changes a shared contract; workflow ownership alone does
not imply an ADR requirement. Advisory/lockfile/workspace pins require the label
and the lead's PR authorization record. Other root/configuration changes follow
their applicable shared-path rule. Never claim this research PR accepted those
decisions.

If PRO-08 or PRO-23 needs a schema migration, the integration lead owns one
separately registered migration package with exact `db/migrations/` files in its
`allowed_paths`, the required `contract-change` label, accepted ADR and lead
review. Merge it before the consuming implementation. PRO-00 freezes the metadata
contract; neither PRO-00 nor a consumer gains migration ownership from this table.

**Dependency and ownership table**

Paths are candidate exact ownership for the future issue, relative to repo root.
New directories are explicitly proposals. The lead may narrow them, but must not
broaden them silently. “None” means no engineering predecessor, not automatic
authorization.

| ID | Deliverable | Merge dependencies | Candidate exclusive ownership |
| --- | --- | --- | --- |
| PRO-00 | Minimal interfaces, fixtures and decision records | None | Named new logging/evidence/release schemas and fixtures under `packages/contracts/`; applicable named ADR/spec files; integration lead owns registry/root registration |
| PRO-01 | Locked-dependency and image scanner adapters | PRO-00 | New `scripts/security/scans/**`, matching `scripts/security/tests/scans/**`; narrow JSON-output extension to `scripts/audit-bulk.mjs` and its existing tests |
| PRO-02 | Evidence validation, local archive adapter, receipt verification and serialized check publisher/admission core | PRO-00 | New `scripts/security/evidence/**`, `scripts/security/tests/evidence/**` |
| PRO-03 | Python logging core and pretty renderer | PRO-00 | New `packages/observability/**`; package registration only by lead in a serialized shared-file change |
| PRO-04 | TypeScript logging core | PRO-00 | New `apps/web/src/lib/observability/**` and tests within that subtree |
| PRO-05 | Python API/worker image and fixture smoke | PRO-00 | New `infra/containers/python/**`, `infra/containers/tests/python/**`; existing installer changes only in a separately assigned follow-up |
| PRO-06 | Web image and standalone tracing | PRO-00 | New `infra/containers/web/**`, `infra/containers/tests/web/**`; `apps/web/next.config.ts` |
| PRO-07 | Shared immutable object-store adapter | PRO-00 | New `workers/src/fel_workers/object_storage.py`, `workers/tests/test_object_storage.py`; existing storage protocol remains frozen |
| PRO-08 | Shared admission/cost reservation prototype | PRO-00 | New `packages/admission/**`; any schema migration is a separately registered integration-lead package under the gate above, merged before its consumer |
| PRO-09 | Independent acceptance harness and adversarial fixtures | PRO-00 | New `evals/production/**`; collection/configuration wired only by lead |
| PRO-10 | API logging/Sentry, storage-reader, pool/role, health and admission integration | PRO-03, PRO-07, PRO-08, PRO-23 | `apps/api/app/observability.py`, `apps/api/tests/test_observability.py`, new `apps/api/tests/test_structured_logging.py` and `apps/api/tests/fixtures/logging/**`; named API `main.py`, `db.py`, `ratelimit.py`, `retrieval.py`, `reader.py`, `extraction/evidence.py`, `config.py` files and named tests; narrow sub-PRs |
| PRO-11 | Worker and calculation telemetry adapters, storage/admission binding and drain | PRO-03, PRO-07, PRO-08, PRO-23 | `workers/src/fel_workers/{__main__,consumer,health,storage,http}.py`, `ingestion/sec_client.py`, `extraction/telemetry.py` under that package; `packages/calculation-engine/fel_calculation_engine/telemetry.py`, `packages/calculation-engine/tests/test_telemetry.py`; exact additional worker tests and fixtures listed below; narrow sequential sub-PRs |
| PRO-12 | Web request correlation and safe telemetry integration | PRO-04 | `apps/web/src/proxy.ts`, named telemetry route/validation/tests; `lib/data/http-source.ts`, `lib/observatory/http-source.ts`, `lib/extraction/transport.ts` and their tests under `apps/web/src/`; named server route bindings; do not edit `next.config.ts` |
| PRO-13 | CI scan/evidence wiring, admission handshake and required-gate activation proof | PRO-01, PRO-02, PRO-05, PRO-06, PRO-22 | Named `.github/workflows/ci.yml`, `advisories.yml`, new security workflow/collector/reconciliation wiring, required-check documentation; sole CI writer; local acceptance does not establish real archival or hosted merge enforcement |
| PRO-14 | Release orchestration and migration separation | PRO-05, PRO-06, PRO-10, PRO-11, PRO-12, PRO-13 | New named release workflow/scripts; later authorized modifications to existing `infra/railway/{api,web,worker}.json`; serialize all `.github/**` and root edits after PRO-13; rollout prerequisites below |
| PRO-15 | Multi-replica acceptance results | PRO-05, PRO-06, PRO-09, PRO-10, PRO-11, PRO-12 | New result reports under `docs/research/production-readiness/acceptance/scale/`; fixture defects returned to PRO-09 owner |
| PRO-16 | Restore and failure-recovery acceptance results | PRO-05, PRO-06, PRO-07, PRO-09, PRO-10, PRO-11 | New result reports under `docs/research/production-readiness/acceptance/recovery/`; fixture defects returned to PRO-09 owner |
| PRO-17 | Authorized hosted pilot acceptance | PRO-14, PRO-15, PRO-16, PRO-19, PRO-20 | Named `docs/runbooks/production/**` and sanitized hosted evidence receipts; actual cloud changes only with scoped authorization |
| PRO-18 | Organizational controls, ownership and evidence operations | PRO-00 | New `docs/security/controls/**` for public-safe policy metadata; restricted personnel/auditor evidence stays outside the public repo |
| PRO-19 | Independent pre-pilot readiness and evidence-population review | PRO-13, PRO-14, PRO-15, PRO-16, PRO-18, PRO-20 | New review records under `docs/research/production-readiness/acceptance/review/pre-pilot/`; read-only producer access; authorizes no production release |
| PRO-20 | Real evidence archive, publisher deployment, identity and reconciliation acceptance | PRO-02, PRO-18 | New `infra/security-evidence/**`, cloud archive adapter under `scripts/security/archive-cloud/**`, matching isolated tests and named archive/publisher runbook; scoped cloud/budget/retention authorization required |
| PRO-21 | Independent post-pilot release review | PRO-17 | New `docs/research/production-readiness/acceptance/review/post-pilot/**`; read-only verification of actual hosted evidence before a separate production promotion decision |
| PRO-22 | SAST language coverage and controlled DAST adapters/fixtures | PRO-00 | New `scripts/security/analysis/**` and its tests; reusable CodeQL configuration and local synthetic DAST target here; PRO-13 exclusively owns workflow wiring |
| PRO-23 | Durable request-to-job correlation propagation | PRO-00, PRO-03 | `workers/src/fel_workers/queue.py`, `apps/api/app/extraction/runs.py` and specifically named queue/enqueue tests; any schema migration is a separately registered integration-lead package under the gate above, merged before its consumer |

The real API configuration, middleware and Sentry initialization live together in
`apps/api/app/observability.py` at the baseline; PRO-10 owns that file explicitly.
Candidate API `logging.py`/`middleware.py` files do not exist and are not substitutes.
Reconcile the enumerated paths against current main during issue registration and
resolve the remaining named tests before dispatch. Their scopes are integration-owned;
authors of PRO-03/04/07/08 must not preemptively wire themselves into those files.
PRO-10/11 each require separate reviewable PR checkpoints if the owned integration
cannot fit a small change. The coordinator owns root build contexts/ignore files,
workspace/package lists, dependency locks and shared test collection. Those
mechanical changes must land before consumers need them, without parallel writers.

PRO-11 owns **both** existing dictionary-to-message telemetry sinks, including the
calculation package, after PRO-03. Its logging checkpoint owns new
`workers/tests/extraction/test_telemetry.py`, existing
`workers/tests/extraction/test_consumer_terminal_run.py` and
`workers/tests/extraction/test_terminal_run_not_requeued.py`, existing
`workers/tests/extraction/test_mock_e2e_workflow.py`, and the calculation
telemetry test above. It also owns new `workers/src/fel_workers/log_context.py`,
`workers/tests/test_log_context.py`, `workers/tests/fixtures/logging/**` and existing
`workers/tests/test_entrypoint.py`/`workers/tests/test_health.py` for logging/Sentry
regressions. Other lifecycle/storage test files must be named at registration.
`workers/src/fel_workers/storage.py` is also an authentication boundary: preserve
`apply_worker_db_role`, strict role validation and the role binding on job and
heartbeat connections. PRO-11 owns the existing
`workers/tests/test_worker_db_role.py` and entrypoint role-binding tests for this
checkpoint; require auth-boundary review and retain the DB-backed least-privilege
assertion.
The emitter inventory and actual-entrypoint acceptance in
[structured logging](structured-logging.md#emitter-migration-inventory-and-integrated-owners)
are mandatory registration inputs. Calculation `TelemetrySink`/`RecordingSink`
injection stays compatible; the default `LoggingSink` maps typed catalogue fields
before encoding. There is no separately dispatched topic-local telemetry package.
PRO-14/15/16 already depend on PRO-11, so release/scale/recovery cannot omit either
adapter checkpoint; the integrated dependency graph remains 24 nodes.

PRO-12's issue must enumerate every outbound HTTP transport and server binding
that propagates correlation, including extraction catch-all and event routes and
the corresponding data/Observatory server callers. The named transports currently
construct fresh request headers; a formatter or proxy-only change cannot provide
web-to-API correlation. Resolve this exact list before dispatch, and test every
transport with a downstream header-capture fixture. Keep identity credentials
separate from validated correlation metadata and never forward it to arbitrary origins.
PRO-12 must preserve [ADR-0027](../../decisions/ADR-0027-deployment-modes.md):
missing deployment mode means public, and public web business routes return
HTTP 503 (`PUBLIC_AUTH_NOT_READY` on guarded API routes) until #324's accepted
request-scoped session implementation and acceptance proof permit public access.
Do not bypass `assertDeploymentMode`, change the Proxy matcher as part of this
correlation package, or substitute a deployment-wide bearer. Correlation changes must
retain literal HTTP-status and direct source-factory refusal tests; health/static
access and independently verified public API identities follow the existing ADR.

PRO-14's later issue must name the existing Railway configurations as modifications,
record their prior builder/commands and effective target settings, and provide a
rollback/restore plan plus a pre-deploy migration/identity and compatibility plan.
Test builder or pre-deploy changes in an explicitly authorized non-production
deployment before rollout. This documentation merge authorizes no configuration
change or rollout; actual hosted changes still need their scoped authorization.

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

The following production findings were fetched from GitHub on 2026-11-15:
all seven were open with no comments and explicitly unregistered/non-dispatchable.
Their proposed fixes are issue context, not accepted architecture or automatic
ownership. The lead must reconcile each affected path and register one owner
before the overlapping implementation starts; add any required merge dependencies
at registration. Offline adapters and fixtures on disjoint paths may proceed.
Re-fetch issues, comments and current PRs before dispatch. These references add
no packages to the 24-node proposed graph and amend no canonical ledger.

| Finding / owning issue pending registration | Affected PRO scope | Do not start / acceptance gate |
| --- | --- | --- |
| [#423: API login, lane roles and RLS](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/423) | PRO-10 API pools/roles and PRO-14 migration identity/configuration | Agree one runtime-login/lane-role owner and the separate migration package before overlapping API/infra edits; accepted role/schema decisions and migration must merge before consumers; hosted acceptance proves runtime credentials cannot regain owner rights |
| [#424: retrieval executes inside the request](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/424) | PRO-10 retrieval integration, PRO-11 queue lifecycle, PRO-23 correlation | Register one retrieval/job-lifecycle owner before editing shared retrieval/worker paths; merge the agreed execution/reservation recovery and correlation contracts before consumers; PRO-15/17 cannot treat fast enqueue or mock-only execution as live retrieval completion |
| [#425: deployed ingestion/index publication path](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/425) | PRO-11 worker jobs, PRO-13 CI integration, PRO-15/17 acceptance | Reconcile queue/index/CI ownership with #177/#201 before integration edits; acceptance needs a deployed authorized ingestion-to-published-index path and searchable corpus proof, not only a library/eval call |
| [#426: mock provider seams and verifier/cost gaps](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/426) | PRO-08 admission/cost, PRO-10/11 provider integration, PRO-17 hosted proof | Resolve provider/verifier/metering ownership with #195/#177/#191 before seam changes; preserve the accepted provider baseline while ADR-0012 remains Proposed; no live acceptance until approved non-echo provider/verifier and complete spend accounting are demonstrated |
| [#427: shared canonical-object storage](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/427) | PRO-07 adapter, PRO-10 reader, PRO-11 binding, PRO-16/17 recovery/hosted proof | Agree one storage binding/reader owner with #108 before overlapping changes; merge the approved adapter/interface decisions before consumers; require worker-to-separate-API readback and DB-plus-object restore proof |
| [#428: hosted build/deployability evidence](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/428) | PRO-05/06 images, PRO-13 build CI, PRO-14 host configuration, PRO-17 hosted proof | Lead resolves host-of-record and build/configuration ownership against accepted ADR-0002 before host-specific integration; build/smoke the selected deployables and verify actual hosted digest/configuration before rollout; research cannot certify a never-observed deployment |
| [#429: environments, release identity and delivery](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/429) | PRO-10 readiness, PRO-11/12 telemetry, PRO-13/14 delivery, PRO-17 hosted proof | Register one release/environment/migration-order owner before workflow/config edits; require isolated target authorization, release/environment identity, ordered migration, readiness, rollback/restore and non-production proof before promotion |

**Independent acceptance per package**

| ID | Producer output and smallest meaningful acceptance |
| --- | --- |
| PRO-00 | Versioned schemas/examples, error/status enums, compatibility rules and an approved decision register; valid, malformed, malicious and missing-field fixtures |
| PRO-01 | Identical adapter envelope for JS/Python/image scans; simulated vulnerable/clean/unreachable/malformed/timeout/no-packages fixtures; all adapters attempted after one failure |
| PRO-02 | Validated reports, receipts and durable generation-bound admission/publisher core; reject forged run/commit/destination, traversal, zip bomb, bad hashes and missing reports; suppress stale collectors and late writes across restart; idempotent duplicates |
| PRO-03 | Python event formatter/context API; concurrent tenant tasks, cancellation, newline injection, redaction failure and queue saturation tests; pretty output must preserve identifiers |
| PRO-04 | TypeScript parity for the same fixtures; no browser secrets, no raw body/URL/error leakage; asynchronous context reset |
| PRO-05 | Final-image isolated imports/resources, migration runner and SQL assets with apply/check fixture, non-root user, no build tools/secrets, declared writable paths, configured port and signal smoke; record digest |
| PRO-06 | Final-image standalone server, static assets and shared-contract route; build without hosted credentials; non-root/read-only smoke with explicit cache paths |
| PRO-07 | Two-client identical/conflicting-write races, cross-client reads, checksum corruption, permission denial, migration checksum and restore fixtures |
| PRO-08 | Two-process global quota and cost reservation invariants, retries, clock/backend faults and recovery; measured contention; no unapproved paid call |
| PRO-09 | Harness interface, deterministic fixtures/seeds, expected-failure demonstrations and isolated cleanup; imported producer implementations are forbidden |
| PRO-10 | Real `configure_logging()`/middleware and `configure_error_reporting()` with Sentry transport canaries; API request→job correlation, role/claim reset, bounded pools, safe health, shared quotas/object reads and preserved REST/MCP separation |
| PRO-11 | Actual extraction `emit()` and calculation `emit(None, ...)`/`LoggingSink` produce bounded, queryable catalogue JSON/context without renamed-key secret leakage; injected recording sink remains compatible; auth-boundary review and role-binding/least-privilege tests; worker crash/reclaim, lease fencing, drain, shared SEC allowance and no production mock mode |
| PRO-12 | Browser→web→API correlation, bounded telemetry and safe Sentry forwarding; hostile header/body/log injection cases; preserve ADR-0027 public HTTP503, matcher/source-factory refusal and no shared bearer until #324 acceptance |
| PRO-13 | Vulnerable dependency, scanner crash, omitted artifact and archive outage fail correctly; same-SHA hosted rerun test blocks before admission ACK and while archive is paused, with actual App/source-check branch binding; activation blocked until proven |
| PRO-14 | Build-once deployment manifest, signature/provenance verification, one-shot migration identity, rollback compatibility and rejected digest mismatch using staging fixtures; existing builder/pre-deploy changes require the authorized non-production deploy test and rollback/restore plan above |
| PRO-15 | Reproducible one/two/overlap-replica results with latency, correctness, connection ceilings, quotas, cursor-key rotation and stream resume |
| PRO-16 | Timed isolated DB+object restoration, key/config/role reconstruction, verified citations and retained-pin replay; partial/missing-object recovery fails acceptance |
| PRO-17 | Platform-observed digest/roles/health/grace, production identity/provider/storage proof and selected product's live gates; no code-only substitute |
| PRO-18 | Owner/frequency/evidence matrix, access/offboarding and incident exercises, vendor/risk/retention decisions, overdue-control reporting |
| PRO-19 | Independent sampling of local/release/archive results and missing-run population; pilot-entry recommendation, not hosted-readiness or SOC attestation |
| PRO-20 | Approved archive and provider-specific OIDC design; prove same-repo wrong-workflow/ref/environment/audience denial, scoped writes, forbidden deletion/overwrite, key recovery, retention/readback, catch-up and missing-run alerts; publisher recovery fences old in-flight check writes in an authorized disposable target; coordinate actual App/branch-rule proof with PRO-13 |
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

# Local acceptance and production completion

<details>
<summary>Relevant source files</summary>

- [Canonical specification](../../specs/001-financial-evidence-lab/spec.md) governs product requirements and release thresholds.
- [Canonical plan](../../specs/001-financial-evidence-lab/plan.md) governs milestone order and model/forecast storage boundaries.
- [Workstream registry](../handoff/workstreams.yaml) governs registered ownership and dispatch.
- [Local development](../development/local.md) documents the implemented environment and acceptance entry points.
- [Production proposal](production-readiness/implementation-spec.md) and [load-testing proposal](application-load-testing/implementation-spec.md) define existing proposed infrastructure work.

</details>

Source baseline `5a7b833c385131fa83388a93d6c3363211209832`, inspected
2026-11-15 America/Los_Angeles. Tracking issue
[#433](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/433).

**Status — proposed implementation specification for lead review.** The owner
requested research and a specification for the six next steps following local
setup. This document defines deliverables, interfaces to existing work, and
observable acceptance criteria. The canonical specification and accepted ADRs
govern conflicts. Proposed work below becomes executable through its owning
issue and registered branch after the applicable contract and review steps.

## Contents

- [Outcome and delivery boundaries](#outcome-and-delivery-boundaries)
- [Verified starting point](#verified-starting-point)
- [Local environment requirements](#local-environment-requirements)
- [Correctness and evidence delivery](#correctness-and-evidence-delivery)
- [Production architecture requirements](#production-architecture-requirements)
- [Public sessions, providers and extraction quality](#public-sessions-providers-and-extraction-quality)
- [Modeling, forecasting and export integration](#modeling-forecasting-and-export-integration)
- [Implementation slices and sequencing](#implementation-slices-and-sequencing)
- [Verification and release evidence](#verification-and-release-evidence)
- [Decisions and rollout checkpoints](#decisions-and-rollout-checkpoints)
- [Research sources and review](#research-sources-and-review)
- [Related pages](#related-pages)

## Outcome and delivery boundaries

Deliver a reproducible development environment, then evidence-backed releases
of the read-only evidence surface and the authenticated financial-research
product. Each release carries immutable source, test, deployment and evaluation
provenance sufficient for another operator to reproduce its acceptance.

Three boundaries organize acceptance.

| Boundary | User outcome | Evidence required |
| --- | --- | --- |
| Local development | A contributor can start, stop, inspect and test the repository on macOS and CI Linux | Locked dependency install, owned process lifecycle, real PostgreSQL tests and worker-to-browser acceptance |
| Read-only evidence pilot | A caller can retrieve public filings and replay verified citations under an explicit cutoff | Existing MCP contracts, publication-time correctness, guarded reads, bounded transport, acceptance suite and authorized hosted pilot |
| Authenticated product and MVP | A user owns a private workspace and inference credentials, reviews extractions, builds models and exports traceable forecasts | User-bound identity and spend, durable ingestion/index/retrieval, hosted operations, model integration and the canonical release gates |

[ADR-0034 Amendment 2](../decisions/ADR-0034-public-read-only-evidence-surface.md#amendment-2-2026-11-13-replay-backfill-privileges-and-bounded-dispatch)
selects MCP-first delivery. Its public read-only surface performs no model or
embedding calls. Its pilot depends on strict publication metadata, infrastructure
and its operating budget. User-funded inference belongs to the authenticated
product path under [ADR-0026](../decisions/ADR-0026-public-workspaces-and-user-funded-inference.md).

## Verified starting point

The setup session installed Node 24.20.0, pnpm 10.33.0 and Python 3.11
according to committed pins, and configured PostgreSQL 17 with pgvector 0.8.5.
The local container uses loopback port 55432 and a persistent Docker volume.
Both development and test databases received 13 migrations. Private local
configuration and launchers live in ignored `.local/` files.

The session recorded 874 JavaScript unit tests, 27 fixture Chromium tests and
175 targeted Python tests passing. Four fixture routes and authenticated
workspace reads returned HTTP 200. Those observations describe this workstation
at the inspected revision. A future implementation must emit its own structured
acceptance records. The full Python run exposed a filesystem-dependent guard
test, and the complete local reader/extraction HTTP harnesses remain the next
verification increment.

Live GitHub research also found pending work that changes planning.

| Existing work | Observed state on 2026-11-15 | Consequence |
| --- | --- | --- |
| [#416](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/416), [#418](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/418) | Open evidence-read slices, with #418 stacked after #416 | Reuse their shared evidence service after reviewed integration |
| [#394](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/394), [#417](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/417) | Cutoff and publication-ingestion work remains open | Respect recorded #394-before-#417 order and resolve overlapping paths |
| [#431](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/431) | Draft hosting proposal at `bb62559cf62ea89c22664c34030d51e4e79f855e`; ADR-0035 Proposed | Treat Vercel Services, Neon/PostgreSQL 18 and related runtime integration as a reviewed candidate |
| [#432](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/432) | Open handoff correction | Reconcile current ownership before creating implementation branches |
| [#423–#429](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues?q=is%3Aissue+is%3Aopen+PROD-BLOCKER) | Production findings awaiting implementation registration | Map each finding onto existing production proposal owners |

The accepted baseline remains [ADR-0002](../decisions/ADR-0002-mvp-stack.md)
until a superseding decision is accepted. Check effective deployment settings
and the merged runtime pins again at implementation time.

## Local environment requirements

### Reproducible lifecycle

The proposed local tooling shall expose `start`, `stop`, `status` and `verify`
operations from a fresh checkout. Resolve the repository root from the tool's
location and select versions from `.nvmrc`, `.node-version`, `.python-version`
and `package.json`. Install JavaScript with the frozen pnpm lock and Python
from `requirements-dev.lock` with hashes. Validate the interpreter and installed
dependencies before launching services. Fixture-only startup needs just the
JavaScript toolchain. Database modes support either the dedicated container or
an explicitly supplied compatible PostgreSQL instance.

Use ignored configuration with owner-only permissions for credentials. Generate
a local database password once and retain it across restarts. Store the database
in an explicitly named volume. Validate an existing container's image, mount,
port and ownership before reuse. Expose application and database ports on
loopback. Make an existing foreign listener an actionable configuration failure.

`start` shall record the repository, command, process identity and owned process
group for each service. On partial failure, stop only services created by that
invocation. Repeated start must be idempotent. `stop` shall validate identity
before signalling, handle stale PID records, terminate children gracefully and
preserve database and evidence volumes. `status` shall check HTTP responses,
PostgreSQL connectivity and migration compatibility separately. Its output shall
exclude credentials, bearer tokens and connection strings.

Keep fixture web mode and synthetic HTTP acceptance mode explicit. API and
worker processes must use the same canonical object directory within an
acceptance target. Production web sessions retain the existing deployment guard.
Provide documented foreground launchers and an optional background wrapper.

Acceptance includes a fresh checkout, a second start, an occupied port, a stale
PID, a failed API startup, a worker child process, reboot/container restart,
missing dependencies, a checkout path containing spaces, and inspection of
persisted configuration/logs for secret leakage. After an intentional stop and
restart, previously ingested evidence must retain its hashes and references.

### Portable guard test

Change the filesystem-dependent test at
[scripts/agent/tests/test_path_guard.py](../../scripts/agent/tests/test_path_guard.py)
to model a case-sensitive lookup deterministically for the exact differently
cased path. Delegate all other lookups to the real implementation. Preserve the
existing insensitive-filesystem emulation and folded protected-path assertions.
The runtime guard's canonicalization and enforcement behavior remains the
acceptance baseline.

Run the focused guard tests on default macOS APFS and Linux, then the complete
Python suite with `TEST_DATABASE_URL` and `FEL_REQUIRE_DB=1`. Record explicit
opt-in benchmark skips separately from missing-database skips. The required
result has zero missing-database skips. Run the committed formatting, lint,
type, contract-drift, security and coverage gates against the selected revision.
Use the current Makefile and CI workflow as executable truth. In particular,
`make typecheck` already includes `scripts/db`; the older testing guide's
statement to the contrary needs correction in the tooling documentation slice.

### Worker-to-browser acceptance

Allocate dedicated databases, storage directories, manifests, output directories
and ports for reader and extraction acceptance. Keep the ordinary development
database outside harness reset/cleanup. Before migration, setup or cleanup, local
acceptance must reject non-loopback/foreign database endpoints and unexpected
libpq service/`hostaddr` overrides. Require an allocated database distinct from
`fel_dev` and `fel_test`; extraction names retain the `fel_extraction_acceptance`
prefix. Validate owned target markers before adopting existing storage. Reject
`READER_SMOKE_HOSTED`, `FEL_READER_SMOKE_SERVICE_HOSTED`, remote-execution settings
and API/web/auth-variant URL overrides inconsistent with the allocated local
target. Hosted acceptance uses its separately authorized entry point.

Absolute manifest paths, an absolute `PYTHONPATH` and the selected Python
executable must reach every subprocess with safe argument quoting. Populate the
Python path with the repo root, API, worker, providers, ontology, retrieval and
retrieval-evals paths used by the existing workflows. Each retry gets a fresh
reader or extraction database and storage directory. Give each suite a separate
artifact and reporter-output directory so later runs preserve earlier evidence. Add explicit loopback
hostnames to every test server. Include the reader auth variants in bounded
interrupt cleanup, since their detached processes sit outside the main webServer
configuration. Browser acceptance must refuse foreign servers instead of reusing them.

| Suite | Existing entry points | Local port allocation |
| --- | --- | --- |
| Fixture browser | `apps/web/playwright.config.ts` | Web 3210 |
| Reader HTTP | `evals.harness.reader_prod_smoke setup`; `apps/web/playwright.reader-prod-smoke.config.ts` | API 8218, web 3218; auth variants 3219 and 3220 |
| Extraction HTTP | `evals.harness.extraction_cross_stack seed`; `apps/web/playwright.cross-stack.config.ts` | API 8211, web 3211 |
| Deployment guard | `apps/web/playwright.deployment-guard.config.ts` | Web 3234, counting upstream 8234 |

The reader setup receives `--manifest "$READER_SMOKE_MANIFEST"` and
`--dedicated-target "$FEL_READER_SMOKE_TARGET"`, with deployment mode
`reader-smoke`. Extraction seed receives `--manifest "$CROSS_STACK_MANIFEST"`,
with mode `synthetic-http`, a named `FEL_SYNTHETIC_HTTP_TARGET`,
`FEL_ALLOW_MOCK_LLM=1` and `FEL_WORKER_DB_ROLE=fel_worker`. Both use
`FEL_AUTH_MODE=mock`, their allocated `FEL_DATABASE_URL` and `FEL_STORAGE_DIR`,
and the selected `FEL_ACCEPTANCE_PYTHON`. Preserve the invocation recipes in the
[local guide](../development/local.md) and
[extraction workflow](../../.github/workflows/extraction-acceptance.yml).

Serialize builds within a checkout, because these suites write `.next` and
`next-env.d.ts`. Isolated checkouts still share host TCP ports; serialize suites
on one host unless alternate ports propagate to every bind, readiness, auth
variant and fault-control path. Capture initial
working-tree state, and account for generated-file changes without overwriting
pre-existing user edits. A successful verification command must shut down its
owned test services and preserve the intended development services.

The reader suite shall ingest committed filing bytes through the real worker,
read canonical content through FastAPI and `HttpEvidenceSource`, and assert
exact highlighted text and hashes. Exercise corrupt content, future/direct-URL
reads, amendment resolution, repeat replay and typed authorization/upstream
failures. The extraction suite shall create a run through HTTP, execute its
durable mock worker, observe live SSE, review source-bound proposals in Chromium and
verify immutable approval and correction history in PostgreSQL. Repeat both
runs to expose contamination and teardown failures. Existing API/SSE and load
tests retain reconnect/cursor proof; the baseline browser suite alone does not
prove forced disconnect recovery.

Each run shall emit commit SHA, working-tree cleanliness, tool and image
versions, suite/fixture versions, mode, target identifier, test counts, skips,
exit status and sanitized artifact paths. Reader/extraction manifests containing
private identity metadata stay in ignored or access-controlled storage. Record
fixture-provider mode in every report so its quality claims remain bounded.

## Correctness and evidence delivery

Finish the existing repair lanes before exposing affected evidence. Reuse the
source-bound acceptance fixture changes already merged through #415. For each
pending PR, record the reviewed commit, current CI evidence, resolved findings
and applicable independent review. The registry and [#432](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/432)
must reconcile actual changed paths before integration.

| Owner | Required behavior | Acceptance cases |
| --- | --- | --- |
| [#410](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/410) | Preserve financial sign using Decimal and reject ambiguous leftover text | Parenthesized euro/pound/US-dollar amounts, sign before currency, Unicode minus, existing USD/percent/grouping/scale controls |
| [#411](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/411) | Preserve numerator and denominator of filing-native XBRL units | USD per share, simple measures, multi-measure or malformed divide, downstream normalization compatibility |
| [#412](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/412) | Redact secrets before persisting run errors or publishing events | Synthetic URI userinfo and authorization schemes across retrieval failure, extraction cancel/typed/internal failure, event history and trace reads |
| [#393](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/393), [#394](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/394) | Preserve the distinct accepted legacy/MCP publication predicates and retained evidence pins | Same-day and after-hours cutoffs, DST boundaries, unknown times, concurrent publication/backfill, immutable replay and amendment links |
| [#395](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/395) | Integrate the shared bounded evidence service after its contract decisions resolve | Strict context/pins, visible issuer resolution, signed pagination, exact span/hash verification, malformed inputs, stable replay |

The three repair defects were reproduced by the Sol research agent with local
synthetic inputs at the source baseline. Their issue acceptance criteria govern
implementation detail. Avoid changing applied migration checksums or mutating
already-published evidence to repair data. An irreparable retained pin needs the
separately accepted retirement or versioned replacement design; no such repair
capability is implied by the current pending ingestion slice.

Legacy reads use `GREATEST(COALESCE(public_at, published_at), published_at)`
against the cutoff. MCP reads require a verified non-null `public_at`
no later than the cutoff; unknown publication instants remain hidden. Keep
company-facts snapshot documents and facts citing them excluded from MCP v1.
The #395 completion scope after #416/#418 still includes section reads, facts
with visible restatement/duplicate links, keyword-only index/search across
lexical/fact/table lanes, pinned coverage, live synchronization status and the
service binding. Test those integration surfaces explicitly.

Complete [#397](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/397)
transport, [#398](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/398)
plugin and [#399](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/399)
evaluations against the frozen eight-tool contract. Build transport against its
interface mock while dependency integration proceeds. Test the normal API mount,
stdio and Streamable HTTP entry points, disabled-by-default mounting, dedicated
public-read role, request/output limits, cursor expiry and cancellation.
Provider construction and network egress at tool time must remain absent.
Apply the frozen 8,000-token output target and 20,000-token cap, 4 MiB canonical
read bound, 10-second request deadline, 2-second transaction statement timeout,
16 in-flight requests per replica, four per IP and cursor lifetime at most
15 minutes. Test all boundaries through the public transport.

The hosted pilot stays under [#400](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/400).
Its current registered dependency on #177 remains binding. A narrower
provider-free corpus/publication prerequisite would require an explicit lead
change to that dependency. Include part-two evidence reads in the final
integration audit. Confirm the SEC timestamp timezone and dissemination
assumptions with the approved contact identity before hosted temporal claims.
Use the canonical 20-issuer strict-publication corpus, published coverage/gaps
and #108's reviewed shared-storage design. Set the monthly operating budget and
global abuse limit, publish the privacy policy and avoid query-text logging.
Omit `reader_url` until a public read-only reader preserves the same evidence
scope; retain `source_url` and citation replay in the meantime.
Pilot exit also requires the frozen transport suite, pilot-volume load and
consented product-usefulness measurements before any directory submission.

## Production architecture requirements

### Decide the effective hosting contract

Resolve the complete scope of draft #431 before platform-specific integration.
Its proposed ADR supersedes the Railway hosting clause while also introducing
Neon database state, Blob storage and queue-triggered execution. The accepted
stack assigns database, Auth and Storage to Supabase and jobs to PostgreSQL.
The decision must enumerate which clauses change and which identity, role,
storage and job contracts continue. Record deployable names, runtime versions,
plan capabilities, regions, resource limits, staging/production boundaries,
operating budget and rollback target.

For the authenticated product release, validate the web-to-API service binding
with a real authenticated request in the selected hosted environment. This
gate does not add #324 to the read-only pilot's recorded prerequisites.
A binding grants internal connectivity and can
bypass platform firewall/middleware protections, so API identity and tenant
authorization must execute on every request. Test absent/expired/wrong-tenant
identity over the binding. Decide explicit public `/mcp` routing separately from
private business APIs while preserving the opt-in MCP mount. Explicitly
supersede or retain the Railway destination accepted in
[ADR-0034 owner input 3](../decisions/ADR-0034-public-read-only-evidence-surface.md#owner-inputs).
The PR's current
static-health preview is preliminary build evidence. [Vercel bindings](https://vercel.com/docs/services/bindings)

### Runtime database privileges and pooling

Under [#423](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/423),
separate migration-owner credentials from runtime API, worker and public-read
credentials. Runtime logins must lack superuser, BYPASSRLS, ownership and the
ability to assume an owner role. Preserve the current tenant membership checks
and role-specific grants. Review FORCE RLS per tenant table with explicit
policies and negative tests. FORCE RLS alone cannot constrain a superuser or
BYPASSRLS login. [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

Use a separate SELECT-only corpus-lane login. Test actual runtime DSNs after
`RESET ROLE`, including transitive membership and managed `neon_superuser`
paths, to ensure role switching cannot recover owner privileges.

Route retrieval reads through bounded role-appropriate pools. Include old/new
deployment overlap, workers and remaining unpooled lanes when proving peak
sessions plus reserved headroom fit the effective connection budget. Establish claims,
role, statement timeout and vector tuning inside the transaction. Prove tenant
A followed by B on the same reused connection cannot inherit A's state, including
a failure/rollback between requests. The current worker uses session-level
role binding, so retain a direct endpoint for it until every claim/heartbeat
path is verified with transaction-local binding. Exercise pooled transaction mode as well
as a direct local endpoint. Use the direct endpoint for the existing migration
applier, which holds a session advisory lock across transactions. Neon transaction
pooling does not preserve arbitrary session state. [Neon pooling](https://neon.com/docs/connect/connection-pooling)

Acceptance must run migrations and grants using the exact managed-service
migration role, then deny cross-tenant reads/writes, runtime DDL, role escalation,
audit mutation and unauthorized public-role access. Confirm the provisioned
PostgreSQL and pgvector versions with SQL. Rehearse the proposed PostgreSQL 18
transition against both supported versions before changing CI/local pins.

### Durable retrieval, ingestion and index publication

Under [#424](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/424),
admit retrieval by atomically persisting the resolved query pins, authorized
actor, idempotency mapping, cost reservation and durable job. Return the existing
run identity promptly. Execute model/network work outside database transactions.
Reuse PostgreSQL claim, lease, heartbeat and terminal-state logic with bounded
retry/backoff. Commit the terminal run state, terminal event and reservation
settlement together so SSE replay and run state agree after restart.

A stale worker must fail every durable stage, result, event and usage mutation
after lease loss; each transaction verifies the current lease/generation. Duplicate
requests and job delivery must yield one logical run, one terminal result and
one accounting settlement. A crash after a provider may have charged requires
an explicit unknown-outcome reconciliation state and retry policy. Local
idempotency alone cannot guarantee exactly-once external billing. Test crash
boundaries before/after admission, provider response, result persistence and
terminal event, plus cancellation, stale intermediate effects and exhausted retry budgets.

Under [#425](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/425),
add authorized ingestion admission and durable index-build orchestration after
corpus publication. Reuse `build_index`, `publish_index_version` and immutable
index metadata, preserving published and explicitly pinned superseded versions.
Freeze corpus, chunker/parser, provider/model/dimensions and build configuration.
Define resumable build checkpoints or a reviewed attempt policy for deterministic
IDs already recorded as failed. Never alter a pin merely to bypass a failed ID.
Publish only after every artifact, count and hash verifies, using a serialized
activation transaction fenced by the current lease/generation. Compare the
expected active predecessor or enforce monotonic selection so a late older
build cannot replace a newer active version. Test racing different builds and
stale workers. A failed new build must leave the prior index usable.
Prove one eligible filing through ingestion, published index, query and citation;
include after-cutoff evidence and an in-progress index as rejection traps, and
replay an explicitly pinned superseded index.

If Vercel Queues is selected, use it as an authenticated wake-up mechanism around
PostgreSQL job authority unless a separate contract replaces that authority.
Atomically retain an outbox and reconcile lost or expired notifications. Verify
consumer identity, duplicate delivery, message age, bounded function execution
and old/new worker compatibility. Deployment-bound consumers can outlive a
rollback, so drain/fence them explicitly. Confirm the chosen Python/container
subscriber deployment in a pilot. [Vercel Queues](https://vercel.com/docs/queues/concepts)

### Immutable evidence storage and recovery

Under [#427](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/427)
and existing PRO-07/10/11, bind the same storage contract in ingestion, reader
and extraction evidence paths. Use deterministic object identifiers, conditional
creation, verified digest/length, bounded streamed reads and private access.
An equal-key/equal-byte retry succeeds. Equal-key/different-byte writes fail.
Concurrent writes must use atomic provider guarantees or a reviewed mediation
layer. A check-then-replace sequence is insufficient.

Test restart and reads from separate API/worker hosts, concurrent writers,
truncation, hash mismatch, oversized content, missing objects and authorization
boundaries. Verify actual runtime credential permissions for read, create,
overwrite and delete. The Blob SDK exposes overwrite/delete capabilities, so an
application `allow_overwrite=False` flag alone does not establish immutable
storage permissions. [Blob Python SDK](https://vercel.com/docs/vercel-blob/python-sdk-reference)

Recover database metadata and referenced raw/canonical bytes together. Inventory
the coherent database checkpoint, object keys/lengths/hashes and retained pins;
include role/grant/configuration and required encryption-key reconstruction.
Restore into
an isolated target, verify every required object digest and immutable citation
reference, then run the reader and extraction acceptance suites. Exercise missing
and corrupt objects and unavailable keys as failed restores. Record measured
recovery time, recovered cutoff and retention policy. Keep canonical evidence
backup ownership distinct from the production proposal's security-evidence
archive. The operator must approve recovery-point/time objectives before hosted
release acceptance.

### Release, readiness and observability

Under [#428](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/428),
[#429](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/429)
and PRO-05/06/10–14, build versioned artifacts from locked dependencies and stamp
commit/image identity into release metadata and Sentry. Freeze compatible schema
versions and runtime requirements with each artifact. Use separate staging and
production credentials, data stores and object namespaces.

One deployment step owns migration application using the direct owner endpoint.
Order release as migration receipt, compatible API/worker readiness, smoke gates,
then authorized promotion. Gate new work until schema/runtime compatibility is
verified, including overlapping old/new workers.
Runtime readiness must be read-only and check connection/role, expected migration
checksums, supported schema compatibility, required storage and bound providers
for its mode. The current migration `--check` path creates its ledger and takes
a session lock, so it is unsuitable as a least-privileged request-time readiness
probe. Preserve liveness separately. Test startup with an unavailable DB, wrong
role, drifted checksum, missing storage and incomplete mode configuration.

Run health, authenticated HTTP, worker-to-browser, failure recovery and smoke
checks before promotion. Record deployment, environment, artifact digest and
actual runtime versions. Promotion must preserve the tested staged artifact and
environment relationship, verified by observed digest/deployment ID. A rebuild
creates a new candidate that must pass the gates before promotion.
[Vercel promotion behavior](https://vercel.com/docs/deployments/promoting-a-deployment)

Rollback must restore compatible code/configuration and drain or fence newer
workers without reversing immutable evidence or blindly undoing migrations.
Use expand/contract migrations with an explicit backward-compatibility window.
A destructive schema transition requires its own restore/forward-repair plan.
Test promotion interruption, migration failure, stale consumers, degraded DB,
provider timeout and recovery. Preserve request/run/job correlation across web,
API and worker through the existing PRO-03/04/10/11/12/23 ownership map.

## Public sessions, providers and extraction quality

[#324](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/324)
owns contract freezing for verified signup/login/reset/logout, idempotent private
organization onboarding and request-scoped sessions. Derive API identity from
the current user and enforce membership from PostgreSQL on every private read
and write. Define cookie/CSRF behavior and private-cache boundaries. Verify two
concurrent users, revoked membership/session, recovery, replay and cross-workspace
access under normal server-rendered and streamed routes. The existing public
web guard changes only with this integrated acceptance.

Freeze the persistence, endpoints and admission lifecycle from the
[BYOK proposal](public-auth-byok-contract.md) under that owner. Accepted ADR-0026
already requires OpenRouter S256 PKCE first, server-side code exchange, and
Fernet/MultiFernet with a deployment-managed keyring outside the database. Bind
purpose, credential, user and organization into the authenticated encrypted
payload and verify all identities on decrypt. Persist key version/status with
ownership and only opaque references in jobs. Resolve and reauthorize immediately before each billable
operation. Test rotation/revocation between enqueue and claim, exhausted quota,
wrong tenant, decryption failure, provider rejection and duplicate retry. An
unavailable actor credential stops the operation before provider invocation.
Prohibit owner-key fallback across generation, embeddings, verification, retries
and background jobs. Enforce fixed/allowlisted routes and an approved serving
provider retention/training policy; unknown policy fails closed. No silent
provider or model fallback is permitted.

[#195](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/195),
[#426](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/426)
and [#191](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/191)
shall share validated provider configuration and injection for API and workers.
Reuse explicit-key adapters already in `packages/providers`; preserve mock-mode
behavior and stored provider identities. OpenAI remains the approved baseline
under ADR-0002; its live binding still needs implementation and acceptance.
Reject mock bindings in hosted billable modes. ADR-0012 remains a proposed substitution. Reconcile the
accepted OpenRouter credential flow with baseline model routing and usage
accounting before activation; direct OpenAI/Anthropic key flows are later,
independently reviewed packages.

Meter generation, embeddings and every billable retry with atomic reservations,
actual usage settlement and reconciliation for uncertain outcomes. Enforce the
canonical per-query/user/organization limits under concurrent admission. Test
with a non-echo fake provider, then scoped authorized live calls. New semantic
citation verification must be separately versioned and evaluated while keeping
`deterministic-v1` replay compatible. Exact span integrity and numerical metadata
checks remain mandatory even when entailment is model-assisted.

Preserve the current gates for extraction calibration. [#62](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/62)
requires both #61's actual load acceptance and #177's live cutover. Integrate the
offline calibration primitives only through their reviewed runtime contract and
an adjudicated, versioned human-label dataset. Test dataset separation, sparse
samples, calibration version replay, threshold changes and budget enforcement.
Preserve record confidence as the minimum required-field confidence and citation
failure as zero. The record/field review thresholds remain 0.85/0.80. Require the
frozen adjudicated support of at least 100 rows, 20 negative and 20 positive
outcomes per required calibration/evaluation family/field cell. Report training
support separately under the offline contract's readiness semantics.
All proposals require human review under M3-CAL-004;
confidence never auto-approves a monetary fact, guidance item or assumption.
The hosted extraction service remains under #362 after its live binding prerequisite.

## Modeling, forecasting and export integration

The accepted [storage boundary ADR](../decisions/ADR-0023-model-and-forecast-storage-boundaries.md)
and canonical plan section 7 govern persistence. Implement separate reviewed
contracts/migrations before their runtime consumers.

| Owner | Required implementation | Acceptance evidence |
| --- | --- | --- |
| [#64](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/64) | Bind immutable approved extraction versions to source nodes, persist exact engine snapshots and sparse scenario revisions | Same-tenant cross-workspace rejection, snapshot round-trip hash identity, branching restore, concurrent idempotency, reported-history immutability and Decimal unit/sign/scale correctness |
| [#65](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/65) | Wire driver graph, formulas, analytics, lineage, diff and restore to persisted model APIs | Actual engine/API values, source drill-through, keyboard/table equivalents, stale-version conflicts and scenario non-mutation |
| [#66](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/66) | Freeze forecast request/results and implement quarterly baseline and analyst-driver workflows | Versioned data/model/scenario/cutoff pins, finite Decimal outputs, 1–8-quarter validation and atomic success/abstention/failure |
| [#67](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/67) | Rolling-origin backtests and calibrated 50/80/95% intervals | Only vintages available at each origin, short-history disclosure, independent numerical oracles and the seasonal-naive eligibility gate |
| [#68](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/68) | Immutable research export bundles and complete audit traversal | Exact extraction/model/scenario/forecast versions, artifact hashes, source citations, renderer version and reproducible manifest verification |

Reuse `packages/calculation-engine` as the sole financial evaluator. Preserve
its versioned canonical bytes, formula AST, cyclic-group policy and injected
telemetry interface. Restoring a model creates a child version. Base scenarios
retain the base snapshot; alternatives override eligible assumptions/drivers
under the engine policy.
Publish outputs transactionally after validation. A failed computation or export
must expose a typed failure and cannot publish a partial successful bundle.

The M4 product integration follows the registered #62 dependency. #65 and #66
share web paths, so serialize their UI integration or explicitly narrow ownership.
#67 follows #66, and #68 follows the registered forecast/live-cutover gates.

## Implementation slices and sequencing

This table maps proposed delivery increments onto existing owners. It is a
planning cross-reference. The canonical task ledger and registry retain their
respective task-state and dispatch authority.

| Slice | Owning issue/proposal | Entry condition | Deliverable and exit evidence |
| --- | --- | --- | --- |
| Local lifecycle and portability | New child proposed under #433 | Register a narrow tooling issue/branch | `scripts/dev/**`, named lifecycle tests and local/test documentation; macOS/Linux lifecycle and guard acceptance |
| Local HTTP acceptance | #108 reader scope; explicitly registered tooling child for extraction/fixture/guard harness changes; #61 consulted for load | Isolated targets and current merged fixture producers | Reader plus extraction acceptance through normal entry points, repeated success and interrupt cleanup |
| Financial and error repairs | #410/#411/#412 | #393 releases worker test ownership; #412 serializes with #394 API tests | Existing issue regression proofs and complete scoped gates |
| Publication and shared evidence | #394, #393/#417, #395/#416/#418 | Current contracts, resolved path ownership and required reviews | #394 before #417; #416 before #418; real PostgreSQL temporal/replay tests |
| MCP delivery | #397/#398/#399 then #400 | Interface mocks permit offline work; integrated evidence/verifier and pilot prerequisites gate release | Transport/plugin/evaluation evidence, then authorized hosted proof |
| Hosting decision and build | #431/#428, PRO-00/05/06 | Accepted complete hosting decision for platform-specific changes | Reproducible deployables and exact managed-database migration proof |
| Runtime safety and storage | #423/#427, PRO-07/10/11 | Reviewed role/storage contracts and serialized migrations | Runtime-role negative tests, shared-object concurrency and joint restore |
| Durable execution and indexing | #424/#425, PRO-08/10/11/23 | Frozen job/admission contracts, resolved worker host | Retry/crash/cancel/accounting and atomic index publication evidence |
| Public sessions and live inference | #324/#292, #195/#426/#191/#177 | Frozen identity/credential contracts and explicitly provisioned live target | User isolation, revocation, cost concurrency and real provider/retrieval gates |
| Hosted operational acceptance | #108/#61/#203/#429, PRO-09/13–21 | Integrated build, storage, worker, admission and observability | Hosted reader/load/restore, trusted security evidence and promotion/rollback proof |
| Calibration and downstream product | #62/#362, #64–#68 | Existing dependency and milestone exit gates | Approved-source model lineage, calibrated forecasts, verified exports and release artifact |

The tooling child should claim new `scripts/dev/**`,
`scripts/agent/tests/test_path_guard.py` and exact portions of
`docs/development/local.md` and `docs/development/testing.md`. Reader harness
changes stay within #108's registered scope unless explicitly reallocated.
Register exact extraction/fixture/deployment-guard harness and Playwright paths
with the tooling child before changes; #61's active slice owns load acceptance,
not those browser configurations. Any new collection entry in `pyproject.toml`, Makefile or CI is
a serialized shared-path change under the applicable authorization.

Reconcile #423–#429 with the [production ownership map](production-readiness/parallel-work-packages.md)
and #431 before registering implementation. A finding issue identifies a gap;
PRO package names are still proposals. Assign one owner per changed path and
avoid parallel replacement implementations. Root files, `.github`, contracts,
migrations and the registry remain serialized. Preserve the accepted limit of
three implementation agents plus the coordinator for the current wave and its
different-vendor review requirement where applicable.

Independent local tooling and offline interface tests can proceed while hosting
choices are reviewed. The hosted pilot, provider activation and downstream model
integration each wait only for their actual recorded prerequisites. Changes to
those dependencies require the lead's explicit registry/ADR reconciliation.

## Verification and release evidence

Every implementation PR shall identify the requirement section it satisfies,
its owning issue, base/head commits, changed paths, tests, residual limitations
and next action. Record separately the evidence produced by code inspection,
synthetic tests, live providers and the hosted environment. Store sanitized
reports with immutable hashes and source/fixture/model/configuration versions.
Keep credentials and private raw traces outside public artifacts.

| Gate | Acceptance result | Evidence owner |
| --- | --- | --- |
| Developer reproducibility | Two clean runs and one interrupted run on macOS/Linux, protected foreign resources, owned cleanup | Proposed tooling child |
| Local integration | Reader, extraction and deployment-guard suites pass through their normal HTTP/browser entry points | #108 reader scope and registered tooling/harness child |
| Financial/tenant/temporal integrity | Regression and concurrency tests pass using actual runtime roles, immutable pins and code-point/hash checks | Existing repair, evidence and privilege owners |
| MCP | Frozen eight-tool schemas, replay and limits pass; temporal validity 100%; pilot search p95 <2 s and citation p95 <500 ms on its specified corpus | #399/#400 |
| Extraction load | Existing 25-client protocol, strict creation/bulk-review/reconnect targets and durable correctness all pass | #61 |
| Operational release | Managed migrations, immutable objects, bounded readiness, trusted CI evidence, promotion, rollback and joint restore pass | #423–#429 mapped to PRO owners |
| Live research quality | Applicable registered live corpus/retrieval/extraction subset gates pass; downstream forecast gates remain at MVP release | #177/#132/#62 |
| MVP | Frozen dual-adjudicated benchmark, every canonical section 19.6 gate and the full section 26 definition pass | #68 and integration lead |

The extraction load protocol retains strict p95 limits of 500 ms for creation,
1,000 ms for 100-item review and 2,000 ms for either reconnect operation. Its
recorded bulk-review p95 of 1,501.912 ms exceeds that gate. Run the same protocol
on a dedicated, documented target before claiming acceptance. Larger user-count
experiments follow the [load specification](application-load-testing/implementation-spec.md)
and supplement the canonical 25-user reference profile.

The canonical financial-quality gates include 100% temporal validity, at least
99% numeric value/unit/period/sign/scale accuracy, at least 95% citation entailment
precision and at least 90% Recall@10. The complete metric set and dataset rules
remain in [canonical sections 19.5 and 19.6](../../specs/001-financial-evidence-lab/spec.md#195-benchmark-set-and-phasing).
The frozen MVP dataset has at least 300 questions, 20 issuers and 30 examples in
each of ten categories, with two qualified adjudicators. Advanced forecast default
eligibility requires a strict median-MAE win over seasonal-naive across supported
horizons one through four. The full release requires empirical coverage of
75%–85% for its 80% forecast intervals.
Use independent expected numbers and source locators in numerical tests.

## Decisions and rollout checkpoints

| Decision | Required record | Gates |
| --- | --- | --- |
| Complete hosting architecture | Accepted ADR covering runtime, database/Auth, storage, worker trigger, MCP route and superseded clauses | Host-specific integration and production provisioning |
| Local tooling ownership | New child issue, exact files, registered branch and shared collection authorization if needed | Committed developer tooling |
| MCP dependency reconciliation | Lead record and updated registry/ADR where dependency changes | Narrowing #400's current #177 prerequisite and integrating stacked evidence slices |
| Public identity and credential protocol | Frozen #324 contract plus provisioning by credential name | Session/custody implementation and billable workflows |
| Provider and usage contract | Model routing, embedding usage, semantic verifier version and unknown-charge policy | Live activation and reliable spend limits |
| Managed resources and operational budget | Named isolated targets, quotas, worker deadlines, object permissions and measured RPO/RTO targets | Hosted load, restore and pilot acceptance |
| Model/forecast/export contracts | Accepted storage/API changes, typed source eligibility and immutable lineage | #64/#66/#68 persistence consumers |

Roll out local tooling first, then the integrated offline MCP and HTTP evidence
paths. Promote hosted evidence only after the registered corpus and operational
prerequisites. Enable user sessions and paid capabilities per reviewed policy
and target-specific acceptance. Advance downstream model/forecast releases
through their existing milestone gates. Persist proof of each transition in its
owning PR and committed reports, with the lead updating authoritative ledgers.

## Research sources and review

Three GPT 6.1 Sol subagents researched local acceptance, production architecture,
and product dependencies independently. Local research reproduced the guard test
result of 74 passes and one filesystem failure. Product research reproduced the
three financial/error defects with synthetic inputs. The coordinator cross-checked
canonical requirements, GitHub PR state and the primary platform documentation.
The source baseline and observations above are dated evidence.

| Primary source | Claim or decision it supports |
| --- | --- |
| [Local guide](../development/local.md), [testing guide](../development/testing.md), [CI workflow](../../.github/workflows/ci.yml), [Makefile](../../Makefile) | Runtime pins, install/test entry points and current local/CI differences |
| [Reader Playwright config](../../apps/web/playwright.reader-prod-smoke.config.ts), [extraction config](../../apps/web/playwright.cross-stack.config.ts), [extraction workflow](../../.github/workflows/extraction-acceptance.yml) | Harness environment, ownership and process topology |
| [Playwright web servers](https://playwright.dev/docs/test-webserver), [Next CLI](https://nextjs.org/docs/app/api-reference/cli/next) | Server reuse, readiness, shutdown and explicit loopback binding |
| [Database context](../../apps/api/app/db.py), [lane connection](../../apps/api/app/retrieval.py), [migration applier](../../scripts/db/migrate.py) | Current role/transaction and readiness integration boundaries |
| [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), [Neon roles](https://neon.com/docs/manage/roles), [Neon pooling](https://neon.com/docs/connect/connection-pooling) | Ownership/BYPASSRLS behavior, managed privileges and session limitations |
| [Index builder](../../packages/retrieval/fel_retrieval/index_build.py), [index selection](../../apps/api/app/retrieval_queries.py), [job queue](../../workers/src/fel_workers/queue.py) | Existing immutable pins, publication and lease logic to reuse |
| [Vercel bindings](https://vercel.com/docs/services/bindings), [Queues](https://vercel.com/docs/queues/concepts), [Python queue SDK](https://vercel.com/docs/queues/python-sdk) | Connectivity, authorization boundary, delivery/versioning and subscriber verification |
| [Local storage](../../workers/src/fel_workers/storage.py), [storage protocol](../../packages/providers/fel_providers/interfaces.py), [Blob SDK](https://vercel.com/docs/vercel-blob/python-sdk-reference) | Atomic creation, read bounds and actual permission verification |
| [Vercel promotion](https://vercel.com/docs/deployments/promoting-a-deployment), [rollback](https://vercel.com/docs/instant-rollback) | Artifact/environment identity and rollback acceptance |
| [MCP frozen design](mcp-evidence-server-spec.md), [MCP implementation plan](../../specs/006-mcp-evidence-server/plan.md) | Public-read contract, replay, limits and pilot dependencies |
| [Production ownership](production-readiness/parallel-work-packages.md), [load follow-up](application-load-testing/review-follow-up.md) | Existing proposed owners, workload and numerical-oracle responsibilities |
| [Model storage plan](../../specs/001-financial-evidence-lab/plan.md#7-m4m5-storage-sketch-and-delivery-ownership), [calibration contract](offline-calibration-contract.md) | Immutable financial lineage and calibration integration boundaries |

All three agents reviewed the revised specification after their findings were
resolved and reported no remaining material defects in their assigned scopes.
Independent specification review and documentation validation are recorded in
[#434](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/434).
GPT 6.1 Sol research and review provide OpenAI-authored evidence. The
ADR-0034 different-vendor review gate remains applicable to affected MCP changes.

## Related pages

- [Research index](README.md)
- [Handoff source of truth](../handoff/README.md#source-of-truth)
- [Production readiness proposal](production-readiness/README.md)
- [Application load-testing proposal](application-load-testing/README.md)
- [Canonical task ledger](../../specs/001-financial-evidence-lab/tasks.md)

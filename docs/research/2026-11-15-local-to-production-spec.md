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
dependencies before launching services.

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
database outside harness reset/cleanup. Require explicit target markers before
adopting existing storage. Absolute manifest paths and the selected Python
executable must reach every subprocess with safe argument quoting.

| Suite | Existing entry points | Local port allocation |
| --- | --- | --- |
| Fixture browser | `apps/web/playwright.config.ts` | Web 3210 |
| Reader HTTP | `evals.harness.reader_prod_smoke setup`; `apps/web/playwright.reader-prod-smoke.config.ts` | API 8218, web 3218; auth variants 3219 and 3220 |
| Extraction HTTP | Existing extraction acceptance workflow, seeder and Playwright config | API 8211, web 3211 |
| Deployment guard | `apps/web/playwright.deployment-guard.config.ts` | Web 3234 |

Serialize builds within a checkout, because these suites write `.next` and
`next-env.d.ts`. Concurrent executions use isolated checkouts. Capture initial
working-tree state, and account for generated-file changes without overwriting
pre-existing user edits. A successful verification command must shut down its
owned test services and preserve the intended development services.

The reader suite shall ingest committed filing bytes through the real worker,
read canonical content through FastAPI and `HttpEvidenceSource`, and assert
exact highlighted text and hashes. Exercise corrupt content, future/direct-URL
reads, amendment resolution, repeat replay and typed authorization/upstream
failures. The extraction suite shall create a run through HTTP, execute its
durable mock worker, resume SSE, review source-bound proposals in Chromium and
verify immutable approval and correction history in PostgreSQL. Repeat both
runs to expose contamination and teardown failures.

Each run shall emit commit SHA, working-tree cleanliness, tool and image
versions, suite/fixture versions, mode, target identifier, test counts, skips,
exit status and sanitized artifact paths. Reader/extraction manifests containing
private identity metadata stay in ignored or access-controlled storage. Record
fixture-provider mode in every report so its quality claims remain bounded.

# Containers and horizontal scaling for FEL

Research for #419 · Baseline `33c6a635c05460624c894d00363d8710a780adc3` · Reviewed 2026-11-14

## Decision requested

Prototype immutable web and Python runtime images and validate them in an isolated
fixture environment. Keep Railway, PostgreSQL jobs, and the existing application
stack. Do not change the live builder or replica count as a consequence of this
research. A production switch requires a reviewed rollout, a rollback, evidence
from the actual platform, and any ADR or contract-change approval required by
`AGENTS.md`. A stack change requires an ADR and benchmark evidence under
[ADR-0002](../../decisions/ADR-0002-mvp-stack.md). Docker packaging is a proposal,
not a claim that FEL is already containerized or horizontally ready.

Proposed runtime units:

| Unit | Artifact and command | Responsibility |
| --- | --- | --- |
| API | Shared Python image; `uvicorn app.main:app --host 0.0.0.0 --port ...` | Request serving, separate restricted runtime identity |
| Worker | Same Python image; `python -m fel_workers run` with explicit queue and role | Claim, heartbeat, process and fence jobs |
| Web | Next.js standalone image; generated `server.js` | Web serving; separate process and configuration |
| Migration | Same Python artifact, one-shot migration command with separate privileged credential | One controlled release step, never on each replica startup |

The specific shell/exec wrapper and generated Next server path must be verified in
the built image. Migration execution must be serialized, fail the release on
error, and maintain compatibility with old and new application replicas while
they overlap. Use expand/backfill/contract migrations and a tested rollback or
forward fix; rolling back an image does not reverse database changes. The existing
migration runner has a database lock and ledger; verify its behavior before
changing orchestration. Do not give the runtime processes migration credentials.

## Evidence at the baseline

- [ADR-0002](../../decisions/ADR-0002-mvp-stack.md) locks Railway, Next.js,
  FastAPI, a Python worker, Supabase Postgres/Auth/Storage, a claim-short
  PostgreSQL queue and Sentry/JSON logs. Redis, Celery and Kafka are deferred;
  it names sustained >100 jobs/sec as a queue revisit trigger, not a capacity
  guarantee. WebSocket evaluation is triggered for streams over 15 minutes.
- [Railway configuration](../../../infra/railway/README.md) and
  [`api.json`](../../../infra/railway/api.json),
  [`worker.json`](../../../infra/railway/worker.json),
  [`web.json`](../../../infra/railway/web.json) select `RAILPACK`, not Docker.
  API pre-deploy applies migrations; worker pre-deploy checks the ledger.
  The worker command explicitly selects `fel_worker`, removes the migration URL,
  and consumes the default ingestion queue. Hosted extraction is not deployed.
  Configuration files do not prove a hosted deployment or its effective settings.
- [`scripts/runtime/install.sh`](../../../scripts/runtime/install.sh) installs
  hash-locked third-party dependencies, uses separately locked build tools to
  build first-party wheels without dependency resolution, runs `pip check`, and
  invokes [`verify.py`](../../../scripts/runtime/verify.py) in isolated mode.
  It checks API, worker and extraction imports and rejects developer tools.
  [`workers/pyproject.toml`](../../../workers/pyproject.toml) includes prompt,
  schema and contract resources. Preserve those checks and assets in the image;
  the clean-environment checks do not prove identical image bytes.
- [`apps/web/next.config.ts`](../../../apps/web/next.config.ts) transpiles the
  source-exporting `@fel/contracts` workspace and sets the Turbopack root; it
  does not enable standalone output or set the output tracing root. Root
  [`package.json`](../../../package.json), [`pnpm-lock.yaml`](../../../pnpm-lock.yaml)
  and [`apps/web/package.json`](../../../apps/web/package.json) pin pnpm, Node
  and web dependencies. The monorepo root is the required build context.
- [`queue.py`](../../../workers/src/fel_workers/queue.py) claims briefly using
  `SKIP LOCKED`, gives each claim a lease token, fences heartbeat and terminal
  updates, and reaps stale claims subject to attempt limits. The
  [`consumer`](../../../workers/src/fel_workers/consumer.py) has a separate
  heartbeat connection and checks lost leases. This supports recovery, not
  exactly-once external side effects.
- [`health.py`](../../../workers/src/fel_workers/health.py) and the
  [worker entrypoint](../../../workers/src/fel_workers/__main__.py) provide
  startup health and a 120-second progress watchdog. Idle loop progress or a
  successful lease heartbeat feeds it; a heartbeat does not prove a handler
  advances. Signal handlers exist; full bounded drain under container teardown
  remains an acceptance test, not an established property.
- [`storage.py`](../../../workers/src/fel_workers/storage.py) is a local,
  content-addressed provider. The Railway runbook requires a mounted durable
  path for live ingestion. A local volume is not evidence that multiple
  replicas can read identical objects or safely coordinate writes.
- [`ratelimit.py`](../../../apps/api/app/ratelimit.py) uses in-process API
  buckets, and [`sec_client.py`](../../../workers/src/fel_workers/ingestion/sec_client.py)
  limits a client locally. Adding processes multiplies these allowances.
  [`db.py`](../../../apps/api/app/db.py) creates a per-process pool and uses
  transaction-local role and JWT claims; worker heartbeats add connections.
  The retrieval and extraction event endpoints support `Last-Event-ID` replay
  ([retrieval](../../../apps/api/app/retrieval.py),
  [extraction](../../../apps/api/app/extraction/routes_events.py)).

## What the platform documentation establishes

- Docker recommends [multi-stage builds](https://docs.docker.com/build/building/best-practices/)
  to separate build dependencies from runtime; its
  [build secrets documentation](https://docs.docker.com/build/building/secrets/)
  says build arguments and environment variables are unsuitable for secrets.
  Exec-form entrypoints avoid a shell that fails to forward signals
  ([Dockerfile reference](https://docs.docker.com/reference/dockerfile/#entrypoint)).
- [Next.js output tracing](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)
  documents standalone output and the monorepo tracing root/includes. Validate
  the generated tree and explicitly copy static/public assets required by the
  application. Turbopack's root is not a substitute for the tracing root.
- Railway's [healthcheck](https://docs.railway.com/deployments/healthchecks)
  waits for a 2xx on the injected `PORT` before switching traffic; it does not
  monitor that endpoint after deployment. Its
  [pre-deploy command](https://docs.railway.com/deployments/pre-deploy-command)
  runs in a separate container without mounted volumes; filesystem changes do
  not persist. [Scaling](https://docs.railway.com/deployments/scaling) starts
  new replicas from the existing deployment image and drains removed replicas.
  Verify actual signal timing and configured grace period in the target account;
  this research does not establish an available grace-period value.
- PostgreSQL documents that [`SKIP LOCKED`](https://www.postgresql.org/docs/current/sql-select.html)
  gives an inconsistent view suited to queue-like consumers, and that
  [`SET LOCAL`](https://www.postgresql.org/docs/current/sql-set.html) expires at
  transaction end. Neither fact gives exactly-once processing or automatically
  cleans unrelated session settings.

These primary sources were accessed 2026-11-14. The initially attempted Railway
`/deployments/deployments` URL returned 404; `/deployments/teardown` and
`/deployments/dockerfiles` returned not-found pages. No teardown timing claim is
based on those pages. Confirm platform capabilities and current URLs at rollout.

## Proposed image and release design

1. Build the Python artifact from pinned base-image digests with BuildKit and
   multi-stage builds. Preserve `requirements.lock`, `scripts/runtime/build.lock`,
   `install.sh`/`verify.py`, first-party wheels, packaged resource files and
   `pip check`. Test imports from the installed environment with no source tree
   on `PYTHONPATH`. Pin platform architecture and update base digests through
   reviewed changes. Keep compiler and build tools out of the runtime stage.
   Explicitly copy the migration runner and required SQL files: installed wheels
   do not include those repository assets. Before approving the digest, run the
   real migration apply/check from the image against an isolated fixture database
   with a test-only migration identity; runtime invocations receive no such identity.
2. Build the web artifact with Node 24, the pinned pnpm version and frozen
   workspace lock. Enable standalone tracing rooted at the repository, include
   only needed untraced files, and copy the generated server, static assets and
   public assets. Smoke an actual shared-contract route from the final image.
   Treat `NEXT_PUBLIC_*` and static output as build-time public data; keep hosted
   credentials out of builds and client bundles.
3. Use non-root numeric users, minimal runtime packages, exec-form commands,
   read-only root filesystems where the platform supports them, and explicitly
   writable ephemeral temp/cache paths. Identify Next cache/write needs in a
   read-only smoke; shared cache semantics require separate design. Do not treat
   temp or container filesystems as durable or shared storage. Drop unneeded
   capabilities and avoid privileged containers where supported.
4. Never bake provider, database or migration credentials into context, layers,
   arguments, public assets, logs or fixtures. Supply runtime credentials through
   the platform. If a private dependency genuinely needs build authentication,
   use a scoped BuildKit secret mount and inspect output for accidental copies;
   no hosted application credentials are needed merely to compile.
5. Produce an SBOM and scan the built final images; run runtime and functional
   tests against those same digests. Record source SHA, dependency/base digests,
   architecture, scan policy/results and final image digest in the release record.
   Promote the tested digest, not a mutable tag or a fresh rebuild. Verify the
   Railway service's actual builder, effective command, image digest, variables,
   and migration order. Current JSON selects Railpack: merely adding Dockerfiles
   changes nothing. Verify that the chosen Railway image/deploy mechanism supports
   immutable digest promotion before proposing a switch; if not, resolve that gap
   explicitly. Do not silently replace the production builder.

## Scaling gates and failure semantics

- **Lifecycle:** distinguish startup/readiness (configuration and required
  dependencies ready for traffic or claims) from liveness (process progress).
  Probe failures during a temporary database outage must not create a restart
  storm. Railway's deployment probe is not continuous liveness. Retain and test
  the worker watchdog and external alerting. Health endpoints must not disclose
  credentials or tenant data.
- **Drain:** on SIGTERM stop admitting new requests and new job claims, mark
  readiness false where routing honors it, continue heartbeats while safely
  finishing bounded work, then close pools and exit before the verified platform
  deadline. If work cannot finish, abandon it for stale-lease recovery; do not
  acknowledge it as complete. A forced kill must produce the same safe eventual
  outcome. Fence every durable write with the current lease in its transaction,
  including checkpoints and terminal effects; check that external writes cannot
  be committed by a stale holder. Measure teardown rather than assuming an
  arbitrary grace period or that Railway continuously polls readiness.
- **Delivery:** retries and reaping make jobs at-least-once. Use stable operation
  IDs, uniqueness constraints/conditional writes, provider idempotency keys or
  an outbox/reconciliation design for each side effect. A lease check alone
  cannot retract an already issued network call. Establish bounded retries,
  dead-letter visibility and operator replay rules.
- **Storage:** before more than one live ingestion worker, implement and test a
  shared durable provider consistent with the existing storage boundary. Retain
  content-derived keys, byte/hash verification, atomic create-if-absent and
  explicit conflict detection; test concurrent identical and conflicting writes,
  cross-replica reads, tenant authorization, backup and restore. Migrate existing
  blobs with integrity verification before switching reads; database backups alone
  do not restore blob contents. Avoid assuming a Railway volume is shared.
  The API also needs the adapter: `apps/api/app/reader.py::_read_canonical_text`
  currently opens a local path, and extraction evidence validation reuses it.
  PRO-10 owns that binding and the worker-to-different-API-replica citation test.
- **Limits:** implement a shared, atomic organization/route limiter and global
  SEC/provider admission budget or prove another centrally enforced limit.
  Account for every process and retry, including overlapping deployments. Keep
  SEC identification and fair access. Preserve tenant cost reservations and
  reconcile failed/in-flight work; fail closed or apply a documented conservative
  fallback if the shared coordinator is unavailable. Do not add Redis by default;
  benchmark a Postgres-backed approach within the existing stack first.
- **Connections and tenancy:** budget peak connections as API replicas × server
  processes × pool maximum, plus worker claim/handler/heartbeat connections,
  migration, operations, monitoring and deployment overlap, with database
  headroom. Measure pool wait and exhaustion. Validate actual pooler mode and
  session semantics; use explicit transactions and transaction-local role and
  claims on every request, rollback/reset pooled sessions, and test cross-tenant
  reuse after errors. Audit session-level settings, including retrieval timeout,
  and do not assume `SET LOCAL` clears prior session state.
- **Streams:** persist ordered events and resume by `Last-Event-ID` across
  replicas/restarts, preserve authorization and ordering, and test duplicates,
  gaps, retention expiry and disconnects. Bound open streams and database use;
  compare behavior to Railway's documented idle/total limits and ADR-0002's
  revisit trigger. Load balancer affinity is not a recovery mechanism.

## Independently reviewable implementation packages

The paths below are proposed ownership boundaries, not authorization to edit
shared paths. Dependencies and actual issue ownership must be assigned by the
integration lead; changes to shared contracts, migrations, ADRs and root locks
follow `AGENTS.md` review rules. Work can be tested in isolated databases and
fixtures without live provider credentials.

| Package | Candidate paths / owner boundary | Evidence and dependency |
| --- | --- | --- |
| Image prototype | New `infra/containers/` Dockerfiles and `.dockerignore`; web tracing in `apps/web/next.config.ts`; Python runtime scripts owned with their maintainers | Clean final-image imports, resources, health and shared-contract page; digest, SBOM and scan. Shared root ignore/locks need lead coordination. |
| Lifecycle | `workers/src/fel_workers/{__main__,consumer,health}.py`, `apps/api/app/main.py`, focused tests | Requires image prototype; verify PID 1, signals, drain, heartbeat, fencing and bounded exit. |
| Storage | `workers/src/fel_workers/storage.py`, provider implementation/tests, storage contract owner | Fixture object store or isolated test service; concurrency, hash, migration and restore. Contract changes require lead review/ADR as applicable. |
| Shared limits | `apps/api/app/ratelimit.py`, `workers/src/fel_workers/ingestion/sec_client.py`, cost and tests | Two processes share a cap, including failures/retries. Schema/contract changes require separate approved work. |
| Deployment | `infra/railway/` and release automation under lead ownership | Requires prior gates, platform digest feasibility and explicit approved rollout; isolated environment first. |
| Scale validation | Existing API/worker integration tests plus isolated fixture harness under owning issue | Requires lifecycle, storage, limits and connection budgets; no production data or mock workers on production queues. |

Optional local Compose is a development fixture, not a production architecture:
use an isolated project and explicit fake credentials/provider modes, a named DB
volume, and a named storage fixture. Default startup must never contact a hosted
service. Normal stop/restart preserves volumes; destructive removal/reset must be
an explicit documented operator action. Provide deterministic seed and cleanup,
without embedding real credentials or requiring live provider calls.

## Acceptance and rollout evidence

Run the following against a disposable, isolated environment with test-only
identities, deterministic jobs and blobs. Capture commands, commit SHA, image
digests, effective replica counts, timestamps, sanitized logs, metrics and
pass/fail results in the release record; never capture secrets or tenant content.

1. Build both images once, inspect user/layers, run resource/import checks and
   scan them. Boot API, worker and web with read-only filesystems and writable
   temp paths; verify configured ports, startup health and a real shared-contract
   route. Exercise missing and invalid configuration as fail-closed cases.
2. Run two API and two worker replicas with unique process IDs. Race many jobs;
   record claims, lease IDs, attempts and outcomes. Kill a worker mid-handler,
   wait for stale recovery and prove the replacement completes while the stale
   lease cannot commit checkpoints or terminal state. Repeat at side-effect
   boundaries and verify the chosen idempotency mechanism prevents duplicates.
3. Send SIGTERM during idle and in-flight work; record last claim, heartbeats,
   completion/abandonment and exit time. Force-kill separately. Confirm no new
   claim after drain starts and compare observed timing with actual platform
   grace. Exercise watchdog and failure recovery without restart storms.
4. Race blob creation, fetch from a different replica, restart, restore database
   and blobs to an isolated target, and verify hashes and citation resolution.
   Test same-key conflicting bytes and permissions failure explicitly.
5. Drive both API replicas and workers concurrently against a fixed shared rate
   and provider budget; test exhaustion and coordinator failure. Saturate pools
   and perform alternating tenant requests through reused connections, including
   rollback/error paths; verify no role, claims or session state leaks.
6. Disconnect and resume streams against another replica, including after restart,
   checking ordering, duplicates, authorization and expired cursor behavior.
   Measure throughput, queue age, p95/p99 latency, pool waits, DB connections,
   memory, rate denials and errors at one and two replicas and during overlap.
   Define numerical SLOs and headroom before judging the benchmark; this document
   supplies no invented capacity target.
7. In a staging Railway environment, verify actual builder/image digest, migration
   single execution, role isolation, health switch, signal and restart behavior,
   then rehearse deployment and rollback with a compatible schema. Compare the
   deployed digest to the scanned and tested digest. Record any mismatch as a
   failed gate. Only after independent review authorize a production rollout.

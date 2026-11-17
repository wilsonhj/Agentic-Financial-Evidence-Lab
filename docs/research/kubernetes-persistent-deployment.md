# Persistent FEL on Kubernetes: architecture proposal

Status: Proposed, under [#439](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/439).
Research date: 2026-11-16 UTC. Application baseline: `ef75bce`.
This document defines a separately reviewable persistent-deployment milestone;
it does not provision that environment or complete a product release gate.

[ADR-0035](../decisions/ADR-0035-vercel-hosting.md) makes Vercel the web/API host
of record and Neon PostgreSQL 18 the database. That accepted decision governs
older Railway wording in the parent spec/plan. Kubernetes remains an optional
validation platform. Replacing the host of record requires a new accepted ADR
with requirements, measured evidence, cost and operating ownership.

## Preserve the working lab

Keep [the existing chart](../../infra/helm/fel/README.md) and
[reproduction guide](2026-11-15-kubernetes-helm-lab.md) as a disposable regression
environment. Its fixture Deployment and separate synthetic acceptance Job do
not constitute a persistent application. The Job deliberately uses loopback,
generated credentials and `emptyDir`; those properties must remain intact.

Create a separate runtime chart only after the contracts below are implemented.
It should deploy independently versioned web, API and worker images, migration
and acceptance Jobs, Services and policy. Tests must exercise the installed
runtime Services and durable stores. Passing a separate disposable stack is
useful regression evidence but does not verify that deployment's wiring.

## Proposed runtime and state boundaries

| Component | Proposed responsibility | Required evidence |
| --- | --- | --- |
| Web Deployment | HTTPS entry point; request-scoped identity; server-side API calls | Real session, CSRF/cache controls, tenant isolation and logout/revocation |
| Private API Deployment | Authorize requests; use bounded DB transactions; admit durable work | Application DB role, membership checks, migrations ready, no privileged fallback |
| Worker Deployment | Consume the existing PostgreSQL queue with bounded concurrency | Least-privilege role, heartbeat/reaper, restart recovery and idempotent effects |
| Migration Job | Apply the committed migration ledger once per release | Dedicated migration identity; serialization; checksum and privilege checks |
| Managed database | Persist evidence metadata, memberships, queue and history | PostgreSQL 18/pgvector parity, TLS, restore drill and connection budget |
| Shared object provider | Store immutable source/canonical bytes and exports | API and worker resolve the same keys; hashes and access policy survive restore |

Start with one web, API and worker replica in a private staging namespace.
Replication, autoscaling and multi-node availability follow measured behavior.
Do not introduce Redis, a second queue or a local model server for this change.
The accepted Vercel path's queue-triggered functions and a Kubernetes worker
process need a shared durable-job contract; their lifecycle differences must be
tested rather than bypassed by Kubernetes's longer process lifetime.

### Database choice and compatibility

Prefer a dedicated Neon staging project/branch for the first persistent trial,
preserving ADR-0035's database choice. The trial needs scoped credentials,
extension/role verification and a bounded connection budget across API pools,
workers, migrations and operators. Use a database endpoint suitable for each
operation; verify session/transaction behavior before introducing pooling.
Never test destructive recovery against the owner's existing database.

The local chart currently pins PostgreSQL 17/pgvector 0.8.5. Hosted parity
therefore requires an additional PostgreSQL 18/pgvector 0.8.6 run against an
immutable image, including migrations, role/RLS checks and application tests.
The earlier PG17 run is retained as compatibility evidence, not relabeled.

An in-cluster database is an alternative requiring its own operator/storage
decision: supported operator/version, CSI class, reclaim policy, WAL archive,
restore procedure, upgrade ownership and on-call capacity. A PostgreSQL
StatefulSet plus a PVC alone does not establish those capabilities. Kubernetes
documents that dynamically provisioned volumes commonly use `Delete`, while
`Retain` preserves the backing volume after claim deletion; choose and test the
policy explicitly. [Persistent-volume lifecycle](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)

### Shared object storage and retention

[#427](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/427)
must route both the worker and API reader through one `StorageProvider`.
[The reader](../../apps/api/app/reader.py) currently reads local files directly;
[the durable provider](../../workers/src/fel_workers/storage.py) is local-directory
storage. ADR-0035 selects a Vercel Blob adapter; implement and validate that
contract first. Any alternative provider for Kubernetes needs an explicit
compatibility/security decision, not a chart-only substitution.

Require identical writes to be idempotent, conflicting writes to immutable keys
to fail, hash verification before use, private tenant-aware reads, bounded
expiring links and no credentials in object keys or URLs recorded in logs.
Source/canonical objects must outlive every retained database reference.
Garbage collection must prove an object is unreferenced across retained pins,
history and recoverable backups. Export retention may differ from evidence
retention under the parent specification's policy; no blanket bucket expiry.

Two independent PVCs cannot provide shared evidence. `ReadWriteOnce` permits
multiple Pods on one node, not unrestricted multi-node sharing; even an RWX
filesystem does not supply object immutability or tenant authorization.
[Kubernetes access modes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes)

## Identity, network and secret boundary

Public multi-user readiness remains owned by
[#324](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/324):
request-scoped sessions, verified membership, encrypted user-funded credential
custody and revocation. Live provider binding/usage remains under
[#195](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/195)
and the existing live-cutover gates. Do not use an owner API key or a shared
deployment bearer to make a persistent demonstration appear authenticated.

The [synthetic guard](../../apps/api/app/deployment.py) intentionally rejects a
non-loopback database. An API Pod and a database Service require a separately
approved integrated-test deployment contract. Do not relax `synthetic-http`
or enable public routes through mock flags. Keep private staging inaccessible
until its actual identity path and negative authorization tests pass.

Expose only the web ingress through TLS; keep API, database and controllers
private. Use namespace-scoped service accounts/RBAC, disable unused API tokens,
non-root containers and explicit CPU/memory/storage limits. Default-deny traffic
and allow only measured dependencies, including DNS. External-provider hostname
allowlists require an appropriate egress control; a DNS name alone is not a
portable Kubernetes NetworkPolicy rule. Prove allow and deny behavior on the
chosen CNI with controlled endpoints before claiming isolation.

The private environment repository stores chart/image references, environment
values, controller policies and secret references. A managed secret store or
approved encrypted-secret mechanism supplies values. Scope Argo to read and
Kargo to the intended environment write path, use branch protections, and
record credential names/owners/rotation in the registry. Verify secret scanning,
push protection and access settings for that repository independently. Scan
image layers and runtime evidence; do not treat private visibility as encryption.

## Release order, readiness and recovery

Use one serialized migration Job with its dedicated identity; application
containers only check compatibility. For a newly provisioned in-cluster DB,
order ordinary Sync resources for storage/DB before a migration **Sync** hook,
then application Deployments in later waves. A PreSync migration is appropriate
only when its database and credential dependencies already exist. Argo orders
phase before wave, and selective sync skips hooks; promotion must use a full
sync. [Argo phases and waves](https://github.com/argoproj/argo-cd/blob/v3.6.1/docs/user-guide/sync-waves.md)

Use expand/contract migrations with an explicit supported image/schema window.
Test the previous image on the expanded schema before permitting image rollback.
Never promise that rolling back a chart reverses a database migration. A failed
migration blocks new workloads; a failed PostSync acceptance blocks promotion.
Restore or roll forward after incompatible data changes under a reviewed runbook.
Retain source/chart/image digests, schema version, exact Git revision, hook UIDs
and operation results with each release; preserve failed-run evidence as well.

Liveness checks process progress without restarting healthy processes during a
database outage. Readiness checks bounded database connectivity, ledger
compatibility and required storage access; report the failing dependency without
credentials. Startup permits measured initialization time. A worker additionally
reports queue-consumer/heartbeat state. Current static health responses do not
satisfy these proposed readiness checks. On termination, stop admitting work,
drain bounded requests and leave recoverable leases/checkpoints; test SIGTERM
and an abrupt worker kill during a real job.

Back up PostgreSQL **and** immutable object inventory/content with a common
recovery manifest containing timestamp/LSN, schema identity, object keys and
hashes. The existing [backup smoke](../../infra/scripts/backup_restore_smoke.sh)
checks database roles/data/ledger; it does not prove object recovery. Rebuild in
an isolated target, validate all referenced object hashes in the drill dataset,
and replay citations and approved-record history before switching traffic.

Proposed pilot targets for owner/budget approval: RPO at most one hour and RTO
at most four hours, demonstrated by a timed restore exercise. These are design
targets, not current service guarantees. Daily backups remain required by the
parent specification. Neon point-in-time restore is bounded by the configured
history window; choose retention and independent exports against the actual
plan and incident-detection period. Preserve the pre-restore state and stop
writes during a coordinated recovery. [Neon recovery documentation](https://github.com/neondatabase/website/blob/main/content/docs/guides/backup-restore.md)

## Budgets, observability and implementation ownership

The 16/24/32 GB Mac profiles are lab budgets. They do not establish production
capacity or availability; a single sleeping desktop is not a production HA
platform. Measure build peaks separately from steady-state workloads, database
connections, queue age, CPU throttling, OOM/eviction events and object-store
latency. Set namespace quotas, admission/concurrency bounds and spend limits
before increasing replicas. Keep the parent spec's reference workload and
latency/availability gates; do not replace them with a light local smoke run.

Use existing structured JSON logs and Sentry with release/environment identity,
correlation IDs and redaction. Alert on failed promotions/migrations, queue age,
stale heartbeats, DB-pool exhaustion, object-integrity failures and backup age.
Verify delivery of a synthetic alert and a redacted failure trace. Adding a
large monitoring stack is a separate resource/operations decision.

| Work package | Existing ownership or required new scope | Acceptance before the next stage |
| --- | --- | --- |
| Lab reproducibility and delivery | #439, scoped chart/scripts/CI/private environment configuration | Real success, forced failure and recovery; measured profiles; independent review |
| Session/BYOK and live provider path | #324, #195, #177; retain their dependency gates | Request identity, cross-tenant denial, revoked-key refusal and metered user-funded calls |
| Shared storage and restore | #427 and hosted reader #108 | Worker-written bytes resolve through API on another node; object/DB restore succeeds |
| Durable retrieval/index jobs | #424 and #425 | Admission returns before long work; restart recovers jobs; index publication is atomic |
| Runtime delivery/readiness | #429, #423 runtime DB identity, #203 observability | Ordered migration, least privilege, versioned rollout and diagnosed dependency failure |
| Persistent Kubernetes trial | New registered issue/paths and hosting decision after prerequisites | Separate runtime chart; private staging; complete failure and restore matrix |

The production-blocker issues are findings, not automatic authoring permissions.
Register their paths and owners before implementation; #439 does not dispatch
their application changes. No canonical task checkbox is changed by this design.

## Acceptance sequence for the persistent milestone

1. Freeze the hosting exception, schema/image compatibility, identity/test mode,
   storage contract, budget and recovery objectives in reviewed decisions.
2. Build immutable artifacts and deploy private staging from its environment
   repository. Assert no public business route bypasses its existing guard.
3. Run browser-to-installed-Service acceptance on PostgreSQL 18, including tenant
   denial, review/correction history, source hashes, queue work and SSE replay.
4. Reschedule API and worker onto different nodes; delete/recreate application
   Pods; require every seeded object/citation and approved history to remain valid.
5. Inject DB/storage outage, worker termination, duplicate delivery, failed
   migration and failed PostSync acceptance. Require bounded failures, no false
   successful promotion and no duplicate approved effects or stranded reservations.
6. Restore DB and objects into a clean target within the approved RPO/RTO, then
   verify prior-image/schema compatibility or explicitly require roll-forward.
7. Run the existing load, financial, temporal, isolation and live-provider release
   gates on their required data/profile. Archive evidence and obtain lead review
   before exposing a persistent service or changing the host of record.

Developer documentation above was retrieved through Context7. This proposal
does not claim that these persistent-runtime or recovery tests have run.

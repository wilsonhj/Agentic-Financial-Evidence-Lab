# ADR-0036: Run the API with one worker process per vCPU

Status: Proposed
Date: 2026-11-20
Related: #61 (`M3-REVIEW-LOAD-ACCEPTANCE`),
[ADR-0034](ADR-0034-public-read-only-evidence-surface.md) (public MCP surface),
[ADR-0035](ADR-0035-vercel-hosting.md) (Vercel hosting),
`apps/api/EXTRACTION_LOAD.md`.

## Context

The subordinate extraction specification requires a review mutation p95 below
1 s on a 100-item bulk action (`specs/003-agentic-extraction/spec.md:178`),
measured with 25 concurrent active users on the reference profile of 8 vCPU and
32 GB for the API and workers (`specs/001-financial-evidence-lab/spec.md`,
§16.1). All three acceptance runs of 2026-09-14 failed: the best bulk-review
p95 was 1,002 ms and the last was 1,502 ms.

Every start command in the repository runs one Uvicorn process:

- `infra/docker/api.Dockerfile`, the image that ADR-0035 deploys;
- `infra/railway/api.json`;
- the load harness, `apps/api/benchmarks/extraction_load.py`.

The review route validates the body on the event loop and runs the
synchronous `review.apply` in the default thread pool
(`apps/api/app/extraction/routes_review.py`). The threads share one Python
interpreter lock, so one process uses at most about one CPU core for this work.

A diagnostic sweep on 2026-11-16 measured this directly on a 4-CPU host with
PostgreSQL 18.7:

- Latency grew linearly, by about 70 to 80 ms for each added client: p50 was
  102 to 111 ms at 1 client (`c01`, `p2_c01`), 364 to 375 ms at 5 (`c05`,
  `p2_c05`), 704 to 836 ms at 10 (`c10`, `p2_c10`), and 1,476 to 1,666 ms at 25
  (`c25a`, `c25b`, `p2_c25a`, `p2_c25b`).
- In the 2026-11-16 activity logs (which were not retained in the repository,
  unlike `summary.json` and the 2026-11-20 `samples.jsonl`; see the diagnostic
  README), the API process used 0.89 to 0.97 of one core and database
  connections were mostly `idle in transaction`. Commit p95 in the instrumented
  2026-11-16 runs (recorded in `summary.json`) was 4 to 61 ms.
- A pool of 25 connections instead of 10 (`cfgdiag_pool25_c25`) removed the
  pool wait but raised p50 to 2,061 ms.

With one process, 25 requests of about 75 ms of serialized work cannot all
finish within 1,000 ms on a core of similar speed. The 8 vCPUs of the reference
profile stay unused.

A second diagnostic on 2026-11-20 changed only the number of Uvicorn
processes, on the same host and with the same waves. Each run had 4 measured
waves and 0 errors:

| API processes | Clients | Review p50 ms | Review p95 ms | Max ms |
|---|---|---|---|---|
| 1 | 25 | 1,222 / 1,252 | 1,593 / 1,707 | 1,713 / 1,791 |
| 2 | 25 | 704 / 670 | 886 / 1,307 | 937 / 1,367 |
| 4 | 25 | 549 | 648 | 694 |
| 4 | 10 | 246 | 416 | 425 |

Two values are the first run and the repeat. The 2-process repeat had one slow
wave, because the load client and the database share the host. These runs are
diagnostic, not acceptance runs. The data is in
[`apps/api/benchmarks/results/2026-11-20-worker-diagnostic/`](../../apps/api/benchmarks/results/2026-11-20-worker-diagnostic/README.md).

`EXTRACTION_LOAD.md` forbids tuning the pool "to relabel a failure", and says
the runner owns one Uvicorn process. A change to the process count is therefore
a deployment decision that this ADR records before any acceptance run uses it.

## Decision

1. **The API runs `WEB_CONCURRENCY` Uvicorn worker processes.** The start
   command in `infra/docker/api.Dockerfile` and `infra/railway/api.json` adds
   `--workers "${WEB_CONCURRENCY:-1}"`. The default stays 1, so a host that
   sets nothing behaves as today.
2. **Each deployment sizes `WEB_CONCURRENCY` to the vCPUs available to the API,
   up to one process per dedicated API vCPU, leaving headroom for co-located
   workloads and OS overhead.** Specification §16.1 co-locates the API and
   background worker processes on the same 8 vCPU / 32 GB reference server.
   An isolated API load run where background workers are idle outside measured
   waves (as in `extraction_load.py`) or a dedicated 8 vCPU API host may run up
   to `WEB_CONCURRENCY=8`, whereas a production reference deployment with
   co-located workers must leave CPU headroom for workers and OS overhead
   (setting `WEB_CONCURRENCY` below 8, rather than blindly setting 8). On
   Vercel containers (ADR-0035), `WEB_CONCURRENCY` is further bounded by the
   container's allocated vCPU and 2 GB memory ceiling.
3. **The pool budget is per process and scales across replicas.** Each process
   owns its own `psycopg_pool.ConnectionPool` (`apps/api/app/db.py`). Under
   multi-replica horizontal scaling — including the accepted Vercel container
   runtime ([ADR-0035](ADR-0035-vercel-hosting.md)) — total peak API
   connections are `replicas × WEB_CONCURRENCY × FEL_DB_POOL_MAX`. A deployment
   sets `FEL_DB_POOL_MAX` so that
   `replicas × WEB_CONCURRENCY × FEL_DB_POOL_MAX` stays below the database
   connection limit with headroom for workers, migrations, admin sessions, and
   any separate pools (such as the `fel_public_read` pool in
   [ADR-0034](ADR-0034-public-read-only-evidence-surface.md)):
   - **Default `FEL_DB_POOL_MAX=10` footgun:** `apps/api/app/config.py`
     defaults `FEL_DB_POOL_MAX` to `10`. Raising `WEB_CONCURRENCY` without
     lowering `FEL_DB_POOL_MAX` multiplies connections silently (for example,
     8 workers × 10 = 80 connections per replica). When this ADR is
     implemented, any deployment setting `WEB_CONCURRENCY > 1` must explicitly
     set `FEL_DB_POOL_MAX`, and the implementation should add a startup guard
     (error or explicit validation) when `WEB_CONCURRENCY > 1` is paired with
     an unset `FEL_DB_POOL_MAX`.
   - **Managed starter tiers and transaction-mode poolers:** Managed starter
     tiers impose tight direct connection limits (for example, Supabase Micro
     and Neon Free). Those deployments must size `WEB_CONCURRENCY` and
     `FEL_DB_POOL_MAX` conservatively or route through a transaction-mode
     pooler (such as PgBouncer, Supavisor, or Neon's pooled endpoint). Because
     `psycopg` 3 enables server-side prepared statements by default, using a
     transaction-mode pooler requires passing `prepare_threshold=None` in the
     pool's connection `kwargs` (`apps/api/app/db.py`) to avoid prepared
     statement collisions across pooled backends; the existing
     transaction-local `SET LOCAL ROLE fel_app` and `set_config(..., true)` RLS
     pattern remains compatible with transaction pooling.
   - **Reference profile example:** On a single-replica reference host against
     a 100-connection limit, `1 × 8 × 6 = 48` (or `1 × 6 × 6 = 36` with
     co-located worker headroom) leaves headroom for workers and migrations.
4. **The rate limiter is per process** (`apps/api/app/ratelimit.py`), so the
   effective limit scales by `replicas × WEB_CONCURRENCY`, as that module
   already states for replicas. A deployment divides `FEL_RATE_LIMIT_QPS` and
   `FEL_RATE_LIMIT_BURST` by `WEB_CONCURRENCY` (and replica count where fixed).
   Note that `RateLimiter` clamps per-process burst to `max(burst, 1.0)` when
   `qps > 0`, so effective burst cannot be pushed below `1.0` per worker
   process. A shared limiter is a separate follow-up. Today this applies to
   retrieval routes; future public MCP routes mounted in `apps/api`
   ([ADR-0034](ADR-0034-public-read-only-evidence-surface.md)) will share the
   same per-worker scaling behavior for any in-process rate limiting.
5. **The load harness aligns its worker count with the deployment
   configuration.** `apps/api/benchmarks/extraction_load.py` gains a
   `--workers` option whose default reads `WEB_CONCURRENCY` and falls back to
   `1` when `WEB_CONCURRENCY` is unset, and records the process count and pool
   settings in its output. `EXTRACTION_LOAD.md` states that an acceptance run
   uses the process count of the deployment it certifies. Changing the count in
   one run to pass is still forbidden. Production-command parity caveat: the
   harness starts Uvicorn with a pre-bound socket (`--fd`) and
   `--no-access-log` rather than the production container `CMD` flags, and
   running multiple workers adds a Uvicorn supervisor plus child processes, so
   the harness teardown path (`terminate()` with a 10 s timeout before
   `kill()`) must ensure all worker children exit cleanly without leaking
   orphaned processes.

## Consequences

- State that is safe with several processes: idempotency keys and run events
  are in the database (`receipts.py`, `routes_events.py`); the token-verifier
  cache (`dependencies.py`) is per process and is rebuilt per process.
- Memory grows with each process. On Vercel containers (ADR-0035), per-process
  resident set size (RSS, in RAM) — distinct from container image size on disk
  (339 MB, measured in ADR-0035) — is what consumes the 2 GB container memory
  limit. Both one process's RSS under load and the container's Vercel vCPU
  limit must be verified before setting `WEB_CONCURRENCY` above 2 there; adding
  workers past the container's vCPU allocation adds memory overhead and context
  switching without adding CPU capacity.
- The Python work per review is still worth reducing (`review.py`,
  `approved.py`). That is code work in the #61 lane, not part of this decision.
- The gate closes only with an unchanged-harness run on the reference profile.
  This ADR does not certify performance.

## Alternatives rejected

- **A larger pool in one process.** Measured: it makes the median worse.
- **Async database access throughout the review path.** It removes thread
  overhead but not the single-core limit for CPU-bound work, and it is a large
  change to code that the review and approval tests protect.
- **Change the requirement.** The specification is shared; the measurements
  show the requirement is reachable with the declared hardware.

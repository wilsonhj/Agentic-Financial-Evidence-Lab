# ADR-0036: Run the API with one worker process per vCPU

Status: Proposed
Date: 2026-11-20
Related: #61 (`M3-REVIEW-LOAD-ACCEPTANCE`), [ADR-0035](ADR-0035-vercel-hosting.md)
(Vercel hosting), `apps/api/EXTRACTION_LOAD.md`.

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
  102 ms at 1 client, 375 ms at 5, 704 to 836 ms at 10 and 1,476 to 1,666 ms
  at 25.
- The API process used 0.89 to 0.97 of one core. The database connections were
  mostly idle in transaction, and commit p95 was 4 to 61 ms.
- A pool of 25 connections instead of 10 removed the pool wait but raised p50
  to 2,061 ms.

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
2. **The reference profile and each production deployment set
   `WEB_CONCURRENCY` to the vCPU count of the API host.** The reference
   profile uses 8.
3. **The pool budget is per process.** Each process owns its pool
   (`apps/api/app/db.py`). A deployment sets `FEL_DB_POOL_MAX` so that
   `WEB_CONCURRENCY × FEL_DB_POOL_MAX` stays below the database connection
   limit with headroom for workers and migrations. For the reference profile:
   8 × 6 = 48 connections against a limit of 100.
4. **The rate limiter is per process** (`apps/api/app/ratelimit.py`), so the
   effective limit is the configured limit multiplied by the process count, as
   that module already states for replicas. A deployment divides
   `FEL_RATE_LIMIT_QPS` and `FEL_RATE_LIMIT_BURST` by `WEB_CONCURRENCY`. A
   shared limiter is a separate follow-up. It affects retrieval routes only.
5. **The load harness starts the declared production command.**
   `apps/api/benchmarks/extraction_load.py` gains a `--workers` option, which
   defaults to `WEB_CONCURRENCY`, and records the process count and the pool
   settings in its output. `EXTRACTION_LOAD.md` states that an acceptance run
   uses the process count of the deployment it certifies. Changing the count
   in one run to pass is still forbidden.

## Consequences

- State that is safe with several processes: idempotency keys and run events
  are in the database (`receipts.py`, `routes_events.py`); the token-verifier
  cache (`dependencies.py`) is per process and is rebuilt per process.
- Memory grows with each process. The 2 GB container limit of ADR-0035 bounds
  the process count on Vercel; the image size and one process's resident
  memory must be measured before a value above 2 is set there.
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

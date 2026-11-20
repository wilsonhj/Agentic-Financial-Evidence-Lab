# Worker-count diagnostic, 2026-11-16 and 2026-11-20

**Diagnostic only. This is not an acceptance run.** It does not certify the
review p95 requirement of #61. The gate closes only with an unchanged-harness
run on the reference profile. See
[ADR-0036](../../../../../docs/decisions/ADR-0036-api-process-model.md).

## Setup

- Host: a 4-CPU sandbox. The load client, the API and PostgreSQL share the host.
- Database: PostgreSQL 18.7, `fsync` on, `synchronous_commit` on,
  `shared_buffers` 128MB, `max_connections` 100.
- Code: `main` at `6b61ed3`.
- Load: the `wave` function and the fixture of
  `apps/api/benchmarks/extraction_load.py`, unchanged. One 1-client preflight,
  one 25-client warmup, then 4 measured waves of the 100-item bulk review. Only
  the client count and the API process count change.
- p50 and p95 are nearest-rank values, as in the harness.

## Results

One API process, pool maximum 10 unless stated (2026-11-16):

| Run | Clients | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| `c01`, `p2_c01` | 1 | 102 / 111 | 118 / 122 | 118 / 122 |
| `c05`, `p2_c05` | 5 | 375 / 364 | 406 / 391 | 410 / 402 |
| `c10`, `p2_c10` | 10 | 704 / 836 | 796 / 921 | 804 / 946 |
| `c25a`, `c25b`, `p2_c25a`, `p2_c25b` | 25 | 1,476 to 1,666 | 1,967 to 2,145 | 2,109 to 2,196 |
| `cfgdiag_pool25_c25` (pool 25) | 25 | 2,061 | 2,233 | 2,256 |

API process count (2026-11-20):

| Run | API processes | Clients | p50 ms | p95 ms | max ms |
|---|---|---|---|---|---|
| `w1_c25`, `w1_c25b` | 1 | 25 | 1,222 / 1,252 | 1,593 / 1,707 | 1,713 / 1,791 |
| `w2_c25`, `w2_c25b` | 2 | 25 | 704 / 670 | 886 / 1,307 | 937 / 1,367 |
| `w4_c25` | 4 | 25 | 549 | 648 | 694 |
| `w4_c10` | 4 | 10 | 246 | 416 | 425 |

Each run had 0 errors. The host load average was 7 to 14 during the
2026-11-20 runs, so the values have noise. The 2-process repeat had one slow
wave.

## Files

- `runs/<label>/metadata.json`: settings of each run. Process count, pool
  settings, PostgreSQL settings and host load.
- `runs/<label>/samples.jsonl`: each request of the 2026-11-20 runs. The rows
  contain only synthetic identifiers and monotonic timestamps. The samples and
  the pool and activity logs of the 2026-11-16 runs are not kept.
- `summary.json`: the output of `scripts/analyze.py` for all runs, which
  includes the pool wait, SQL and commit times from the instrumented 2026-11-16
  runs.
- `scripts/`: the drivers and the analysis. `sweep_workers.py` starts
  `uvicorn --workers N`. `sweep_driver.py` starts one process through
  `instrumented_uvicorn.py`, which records pool checkout timings.
  `sampler.py` samples `pg_stat_activity` and CPU use. `run_workers.sh` runs
  the 2026-11-20 sequence. It needs a disposable database: the driver refuses a
  database name that does not start with `fel_load`.

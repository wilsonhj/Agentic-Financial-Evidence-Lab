# Source register and independent reproducibility

Research date: **2026-11-14**. Code baseline:
`33c6a635c05460624c894d00363d8710a780adc3`. All repository links below are pinned
to that revision. External pages are dated observations; re-fetch before
implementation because vendor behavior and limits can change. The
[evidence manifest](evidence.json) retains repository file hashes and short
external excerpts with hashes. An excerpt/hash establishes what was recorded;
it does not independently prove a vendor deployed that behavior in our account.

## Method and claim classification

- **R:** inspected source code, configuration, specification or committed artifact.
  A requirement is not measured capacity; checked-in configuration is not hosted state.
- **E:** directly read official platform/library documentation. Next.js and Uvicorn
  documentation were also read at the versions pinned by this repository.
- **D:** explicit arithmetic from stated assumptions, not a benchmark or forecast.
- **Proposed:** requirements, budgets, test durations, file paths and implementation
  choices in the spec. They are recommendations with source-backed rationale,
  not empirical claims. Their acceptance tests are how implementation is verified.

GitHub was used for repository evidence; official pages were retrieved with
Tavily, and Context7 corroborated k6 workload semantics and Next.js multi-instance
requirements. Search snippets alone were not used as authority. The Uvicorn
website failed extraction twice; its official repository's `0.52.4` documentation
was read instead. Supabase's changelog was consulted; actual connection/storage
client compatibility remains an implementation test, not an assumed hosted result.

The current GitHub issues #61, #324 and #362 were read as open during this research;
their state is mutable. Use the pinned code evidence below for lasting claims.
PR #420 was read at its immutable head recorded in [README](README.md); its
proposed implementation packages are coordination context, not accepted architecture.

## Repository evidence

| ID | Narrow claim and independent inspection | Pinned evidence |
| --- | --- | --- |
| R01 | §16.1 specifies the 25-user reference corpus/hardware and latency/job gates; §18.2 sets cost/timeout requirements. These are targets. | [Parent spec §§16.1, 18.2](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/specs/001-financial-evidence-lab/spec.md) |
| R02 | Historical projected run: 100 samples/operation, 25 overlap, review p95 1501.912 ms against strict 1000 ms; full reference profile false. Worker/model production excluded from timed workload. | [Report](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/benchmarks/results/2026-09-14-projected/report.json); [Protocol](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/EXTRACTION_LOAD.md); [Report algorithm](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/benchmarks/extraction_load_report.py) |
| R03 | Public web guard refuses business access; independently verified public API identities remain allowed. | [assertDeploymentMode](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/web/src/lib/deployment-mode.ts); [Web boundary](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/web/src/proxy.ts); [API guard](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/deployment.py); [ADR-0027](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/docs/decisions/ADR-0027-deployment-modes.md) |
| R04 | Configured hosted worker has no extraction queue flag; runtime extraction binding/create gate require explicit mock configuration, with further policy/corpus checks. | [Worker command](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/infra/railway/worker.json); [build_structured_llm / validate_extraction_model_binding](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/workers/src/fel_workers/__main__.py); [create gate](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/extraction/runs.py); [Deployment runbook](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/infra/railway/README.md) |
| R05 | Default tenant pool min/max 1/10; process-local pool registry; transaction-local role and claims. | [Settings](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/config.py); [pool_for / tenant_connection](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/db.py) |
| R06 | Each selected lane opens a direct psycopg connection; pipeline runs in a tenant transaction before POST returns; failure recording is attempted; inability to persist it can leave the queued run/reservation. Retrieval SSE replays a captured high-water mark. | [_lane_call / _corpus_read_connection / _run_pipeline_or_fail / create_query](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/retrieval.py) |
| R07 | Sleep 0.2 s, heartbeat 20 s, durable Last-Event-ID replay and terminal close; fetch re-resolves membership, reads at most 200 events per batch and releases tenant connections between polls. | [stream_events](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/extraction/routes_events.py); [fetch](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/extraction/events.py); [resolve_membership](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/dependencies.py) |
| R08 | Process-local org/route bucket, defaults 5 QPS/20 burst; applied to selected retrieval mutations, not every route. | [Limiter](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/ratelimit.py); [Defaults](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/config.py); [Route dependencies](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/retrieval.py) |
| R09 | Organization advisory transaction lock serializes query admission; audit reservations include in-flight spend. | [lock_query_budget / reserve_query_cost / spend_snapshot](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/costs.py); [Admission and execution](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/retrieval.py); [_insert_run reservation call](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/retrieval_queries.py) |
| R10 | API reader opens local canonical files; extraction validation uses that reader; live worker binds LocalDirStorageProvider. The protocol defines put/get/signed_url. | [_read_canonical_text](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/reader.py); [Evidence read](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/extraction/evidence.py); [Local provider](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/workers/src/fel_workers/storage.py); [Binding](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/workers/src/fel_workers/__main__.py); [StorageProvider](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/packages/providers/fel_providers/interfaces.py) |
| R11 | Committed Railway JSON uses Railpack, no explicit replica count; API command omits --workers; API pre-deploy applies migrations. | [API](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/infra/railway/api.json); [Web](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/infra/railway/web.json); [Worker](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/infra/railway/worker.json) |
| R12 | Runner requires local fel_load* DSN, current mode/marker configuration, fresh output; measured waves hard-code 25; preflight-only fails acceptance. | [Runner main / wave](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/benchmarks/extraction_load.py); [prepare_synthetic_target](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/benchmarks/synthetic_target.py); [Runtime guard](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/deployment.py) |
| R13 | Accepted stack/change rule; deferred coordination components; queue and stream revisit triggers are decision triggers, not capacity promises. | [ADR-0002](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/docs/decisions/ADR-0002-mvp-stack.md); [Constitution](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/.specify/memory/constitution.md) |
| R14 | Queue claims use SKIP LOCKED with lease tokens; consumer heartbeat/reaper/fencing paths exist. A queue job can complete while extraction waits for review. No exactly-once external-effects assertion follows. | [claim_one / heartbeat / terminal writes](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/workers/src/fel_workers/queue.py); [Consumer lifecycle](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/workers/src/fel_workers/consumer.py) |
| R15 | API health handler returns a static liveness response. | [health](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/api/app/main.py) |
| R16 | Versions inspected: Next.js 16.4.2, Uvicorn 0.52.4, psycopg-pool 3.3.1. | [Web manifest](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/apps/web/package.json); [Python lock](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/blob/33c6a635c05460624c894d00363d8710a780adc3/requirements.lock) |

## External primary sources

Read the named sections, not just an excerpt. These sources establish documented
behavior; the spec separately requires target-account tests. No hardware capacity,
billing estimate or unverified account entitlement is inferred from them.

| ID | Official source / section | Supported claim and limit of inference |
| --- | --- | --- |
| E01 | [Railway scaling](https://docs.railway.com/deployments/scaling), load balancing/sticky sessions/metrics | Public routing is random within a region, nearest-region for multi-region; no sticky sessions; aggregate metrics do not prove individual replica balance. |
| E02 | [Railway volumes](https://docs.railway.com/volumes/reference), Caveats | Replicas cannot use attached volumes; volume attachment can entail redeploy downtime. Does not establish any shared-object adapter. |
| E03 | [Railway healthchecks](https://docs.railway.com/deployments/healthchecks), How it works/Continuous healthchecks | Deployment activation uses successful 2xx checks; the endpoint is not continuously monitored afterward. |
| E04 | [Railway private networking](https://docs.railway.com/networking/private-networking/how-it-works), Internal DNS | DNS resolves internal service addresses. No per-request private balancing guarantee is asserted by this source or this spec. |
| E05 | [Railway edge specifications](https://docs.railway.com/networking/public-networking/specs-and-limits), Edge Traffic/Rate limits | 15-minute transferring HTTP / five-minute no-data limits; 10,000 concurrent connections and approximately 11,000 RPS to a domain; limits subject to change. Connection scope across domains/services requires confirmation. |
| E06 | [Railway teardown](https://docs.railway.com/deployments/deployment-teardown), overlap/draining | Configurable overlap and SIGTERM-to-SIGKILL draining; no default or observed grace duration is assumed. |
| E07 | [k6 open/closed models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/) | Closed iterations depend on completion; open arrivals do not. Explains why both models are required. |
| E08 | [k6 dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/) | Missing free VUs can cause dropped arrival-rate iterations; generator allocation and SUT slowdown are distinct possible causes. |
| E09 | [Psycopg pools](https://www.psycopg.org/psycopg3/docs/advanced/pool.html), lifecycle/sizing/statistics; [API](https://www.psycopg.org/psycopg3/docs/api/pool.html) | Bounded connection counts, queued callers, wait timeouts and statistics. Pool size is a measured tuning choice, not a user-count ratio. |
| E10 | [Next.js v16.4.2 self-hosting](https://github.com/vercel/next.js/blob/v16.4.2/docs/01-app/02-guides/self-hosting.mdx), multi-server/streaming/cache | Same build, compatible action encryption, deployment skew handling and cache coordination; proxies must preserve streaming. Does not imply this repo is configured correctly. |
| E11 | [Uvicorn 0.52.4 settings](https://github.com/Kludex/uvicorn/blob/0.52.4/docs/settings.md), workers/resource limits/timeouts | Worker default uses WEB_CONCURRENCY or 1; concurrency admission can return 503; graceful-shutdown timeout is configurable. |
| E12 | [PostgreSQL 17 NOTIFY](https://www.postgresql.org/docs/17/sql-notify.html), Description/Notes | Transaction-bound delivery and possible duplicate folding; notifications are signaling, not the application's durable event-history store. |
| E13 | [Supabase standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads), overwriting/concurrency | Default existing-path error and first-completer wins; upsert allows overwrite. Immutable readback and authorization still need adapter tests. |
| E14 | [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres), connection methods/client configuration | Direct, session and transaction connection modes have different semantics. Verify actual pooler and prepared-statement/session behavior. |
| E15 | [k6 distributed testing](https://grafana.com/docs/k6/latest/testing-guides/running-distributed-tests/) | Distribution addresses load-generator/multiple-origin needs; choosing Kubernetes or a paid runner is not mandatory for this proposal. |

## Derivations and design choices

| ID | Reproducible reasoning | What it does not establish |
| --- | --- | --- |
| D01 | By definition, N action starts per 10 s gives N/10 starts/s: 100, 500, 1000 for N=1000,5000,10000. A sequential closed user waits R+Z seconds per iteration, giving steady-state approximation N/(R+Z); E07 explains the completion coupling. | Real user behavior, HTTP fan-out, bottleneck capacity or provider throughput. |
| D02 | Sum every process's maximum concurrently open connections, including tenant/read pools, workers/listeners/ops and old+new overlap. Compare with effective client and DB backend budgets separately if pooled. | That all pools fill at once, or that a pooler removes DB CPU/storage limits. |
| D03 | R07 sleeps 0.2 s after each fetch, so cycles/s per stream = 1/(0.2+fetch/dispatch time), approaching 5 as work approaches zero; 10000×5=50000. | An observed SQL rate; each cycle has multiple statements and real fetch time reduces the cycle rate. |
| D04 | If each of 10000 users holds one HTTP/1.1 SSE connection, 10000 connections are occupied before extra traffic. Compare with E05 while retaining its scope uncertainty. | HTTP/2 connection counts, idle-session load, account-specific limits or a guaranteed route around the cap. |

All proposed mixes, 1.5/3-second composite-reader budgets, 20% headroom, repetition
counts, 120-second recovery target, 0.5–1.5 share band and hold/soak durations
are **engineering acceptance choices** to freeze before testing. They are not
presented as published industry standards or existing successful measurements.

## Reproduce the code and historical benchmark checks

From a repository checkout containing the baseline commit:

```sh
git show 33c6a635c05460624c894d00363d8710a780adc3:apps/api/benchmarks/results/2026-09-14-projected/report.json
git show 33c6a635c05460624c894d00363d8710a780adc3:apps/api/app/extraction/routes_events.py
git show 33c6a635c05460624c894d00363d8710a780adc3:apps/api/app/retrieval.py
```

Verify all source hashes without checking out or executing repository code:

```sh
python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
m = json.loads(Path("docs/research/application-load-testing/evidence.json").read_text())
for source in m["repository_sources"]:
    data = subprocess.check_output(["git", "show", m["baseline_commit"] + ":" + source["path"]])
    assert hashlib.sha256(data).hexdigest() == source["sha256"], source["path"]
for source in m["external_sources"]:
    assert hashlib.sha256(source["excerpt"].encode()).hexdigest() == source["excerpt_sha256"], source["id"]
print("Pinned source and recorded excerpt hashes verified")
PY
```

To recompute historical p95, read the pinned `samples.jsonl`, select
`phase == "measured"`, group by operation, sort `end_ns - start_ns`, and choose
index `ceil(0.95*n)-1`; divide by 1e6 for milliseconds. Also verify statuses,
`verified`, identities, complete sample counts and overlap using the pinned
`extraction_load_report.py`. Percentiles alone cannot reproduce its PASS/FAIL.

External reproduction: visit each official URL/section, compare the narrow
claim and recorded excerpt, and note any changed documentation. Re-run
platform acceptance when docs change; a historical hash is not a guarantee of
current platform behavior. Unavailable or contradictory sources block the affected
claim until reconciled, not the independent remainder of the test program.

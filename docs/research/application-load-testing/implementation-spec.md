# Application load testing and load balancing implementation specification

**Proposed requirements, not implemented behavior.** Baseline and governance:
[research index](README.md). Every factual baseline/platform assertion below uses
the identifiers in the [source register](sources.md). All new numerical budgets,
test durations, algorithms and file paths are design proposals unless explicitly
identified as an existing requirement or recorded measurement.

## 1. Outcome and evidence boundaries

Produce a repeatable answer to: which workload, corpus, hardware, deployment and
provider configuration can sustain 1,000, 5,000 or 10,000 concurrent user sessions?
Report maximum verified capacity separately for browsing, retrieval, extraction,
streaming and their combined workload. Never equate sessions, in-flight HTTP
requests, transport connections, open streams, queued jobs or active workers.

The existing reference profile is 25 active users, 100 issuers/eight years,
10 million passages and 15 million embeddings, with 8-vCPU/32-GB API/worker
resources and a separate 8-vCPU/32-GB database [R01]. Preserve that gate.
Additional scale tiers extend the test program; they do not replace it.

The local extraction report records create/review/waiting-reconnect/terminal-
reconnect p95 of 152.483084/1501.912/218.224167/284.669292 ms, respectively,
against strict 500/1000/2000/2000-ms budgets, 100 samples per operation and
25-way overlap. The review gate failed. This is historical synthetic evidence,
not a measurement of current production or of real-model throughput [R02].

The code baseline has these constraints:

| Observation | Implementation implication | Evidence |
| --- | --- | --- |
| Public web business routes refuse access until request-scoped identity exists | Full public-user acceptance depends on #324; direct API tests may proceed with verified individual identities | [R03] |
| Hosted worker config selects ingestion; extraction runtime is mock-gated | Separate API admission from worker completion; live extraction acceptance depends on the model binding and extraction deployment | [R04] |
| Tenant pools default to 1–10 connections per process; retrieval opens separate lane connections and executes before POST returns | Bound and measure both connection classes; 202 is not proof of successful asynchronous execution; failed failure-persistence can leave a queued run/reservation | [R05], [R06] |
| Extraction SSE sleeps 0.2 seconds between database fetches, releasing connections between polls | Test sustained streams, polling work, revocation and reconnects independently | [R07] |
| Selected retrieval routes have process-local organization/route buckets, default 5 QPS/burst 20 | Replica count changes aggregate allowance; implement shared enforcement before certifying a global quota | [R08] |
| Query admission already has transaction-scoped organization locking and durable reservations | Preserve and test it; do not recreate it or hold its lock during provider calls | [R09] |
| API canonical-text reads and the live worker storage binding use local files | Shared immutable storage must reach API reader and extraction validation as well as workers | [R10] |
| Railway config has no explicit replica count or API worker count | Record effective hosted settings; do not infer the actual topology from JSON alone | [R11], [E11] |

## 2. Test manifest and workload definition

Implement one versioned `load-profile/v1` manifest consumed by all runners and the
reporter. Reject missing required fields rather than substituting favorable values.
The future contract owner decides whether its schema belongs under shared
contracts; any shared schema/migration change needs the existing approval process.

Required manifest fields:

- Test ID, source/tree SHA, dirty-tree status, runner version/digest, seed version,
  corpus/index/model pins, mode (`synthetic`, `staging-provider`, `live`) and purpose
  (`normal`, `overload`, `fault`, `recovery`). Require a clean tested revision.
- Named target, explicit allowed origins, environment identifier, network path
  (`direct-api`, `web-api`, `edge`), region/RTT/bandwidth and approved spend ceiling.
- Counts of distinct users, organizations, workspaces, documents and versions;
  tenant-size distribution; role distribution; document-size and sibling fan-out
  distribution; cutoff/index filters; cold/warm-cache definition.
- Session count, independent arrival rates, action mix, think-time distribution,
  number of streams, stream/run sharing ratio, event emissions/sec, event payload-size
  and batch-size distributions, subscriber fan-out, submitted jobs/sec and worker slots.
- Web/API/worker replica counts, processes per replica, CPU/RAM limits, DB compute,
  pooler mode, all connection ceilings, durability settings, replica overlap,
  storage adapter, admission policy, provider quotas and effective cost limits.
- Ramp/hold/soak/drain durations, per-operation deadlines and latency thresholds,
  minimum observations, generator shards/resources, clock synchronization evidence,
  stop rules and artifact destinations. References to secrets, never their values.

Seed real database memberships for distinct users, including several users in
one organization; one token copied 10,000 times is not 10,000 identities. Seed
parsed canonical objects and corpus membership, preserving source hashes, spans,
cutoffs and RLS. Use representative document sizes and enough unique documents to
avoid certifying only a single hot cache entry. The reference corpus gate must
use the specified scale; proportionally reduced fixtures remain labeled synthetic.
Token provisioning and refresh must not turn into an accidental login-provider
stress test; measure login/refresh separately and ensure tokens remain valid.

### Session and arrival-rate profiles

Use k6 closed-model VUs for user journeys and separate open-model arrival-rate
scenarios for fixed offered traffic. In the closed model, slower iterations lower
throughput; arrival-rate executors decouple arrivals from completions. Dropped
iterations can indicate insufficient generator allocation or target slowdown,
and must be investigated rather than silently omitted [E07], [E08].

An **illustration**, not a measured demand forecast: if each of N users starts
one action every 10 seconds, offered actions/sec = N/10 [D01].

| User sessions | Illustrative offered actions/sec | Required certification |
| --- | ---: | --- |
| 1,000 | 100 | Full normal mix, individual component results, failure/recovery |
| 5,000 | 500 | Same, plus validated generator capacity and multi-replica distribution |
| 10,000 | 1,000 | Same, plus explicit platform connection headroom and edge-limit review |

Actions are not HTTP requests: include each action's fan-out, status polls and
retries. For a closed journey with mean response time R and think time Z, use
N/(R+Z) only as a steady-state planning approximation, then measure actual starts,
completions and in-flight work [D01]. Do not infer required machine count from N.

Until production usage supplies a distribution, use a labeled planning mix of
90% read journeys, 8% retrieval and 2% extraction submissions, plus separate
100-item review and SSE cohorts. This mix is a proposed experiment, not a claim
about real users. Run read-heavy, write-heavy, one-hot-tenant and many-tenant
variants. Explicitly record the number of active streams, independent of VUs.
A combined-tier certificate requires HTTP, sustained SSE and worker/review cohorts
to run simultaneously on the same deployment during the same hold window. Report
N unique active identities across the cohorts, with any intentional identity overlap
explicit; do not sum separate component passes or accidentally run N users in each
cohort and label their combined load N. Report transport connections separately.

## 3. Harness and correctness requirements

Use a pinned k6 executable for HTTP workloads, an independent Python async HTTP
stream reader for SSE/worker lifecycle measurements, and a small Playwright cohort
for actual browser rendering/session behavior. Large protocol tests do not prove
browser UX. These are proposed test-tool choices; pin versions and supply-chain
digests through the repository's dependency approval workflow before execution.

| Scenario | Required behavior and oracle |
| --- | --- |
| Metadata and reader | Real authorized workspace/document calls; validate IDs, corpus/version/cutoff, pagination, span hashes and response bounds; small/large documents with/without siblings |
| Retrieval | POST query with a unique idempotency key for new work; inspect durable run status, result and citation/cutoff integrity; measure request, first real event and full completion separately; 202 with a failed run fails the workflow |
| Extraction | Create → actual queue consumer → proposals → atomic review → approved immutable record; measure queue wait and execution independently; new work cannot pass solely by enqueueing |
| Review contention | Independent 100-item reviews plus explicit same-record conflicts; verify one valid winner, expected conflict responses, unchanged prior versions, hashes, audit and provenance |
| SSE | Parse complete frames, not response headers/comments; measure first useful event, ongoing delivery and Last-Event-ID replay; idle/active runs, shared/unique runs, abrupt disconnect, expired/foreign cursor, revoked member and terminal close |
| Browser | Production Next build and web-to-API path; distinct user sessions, navigation, reads, review and reconnect; sample client CPU/rendering/network separately from API timing |
| Overload and faults | Expected 429/402/conflict responses are separate named scenarios; DB/storage/provider failures, slow clients, replica loss and rolling deploy must preserve financial/tenant invariants |

The SSE client must handle chunk splitting, multiple frames per chunk, bounded
buffers, heartbeat-only intervals and explicit deadlines; prove its parser with
fragmented fixtures. Durable event IDs are the oracle; application-side deduplication
may handle replayed IDs but missing events, reordered durable history or unauthorized
delivery fail. Record replay duplicates rather than claiming exactly-once transport.

Measure first-useful-event, initial-cited-answer and complete-answer latency from
the initiating user action/POST start, including query POST time and event-URL
discovery, as well as separately measuring stream-connection-to-first-event.
The baseline query POST executes the pipeline before returning, and its retrieval
event endpoint replays a captured high-water mark rather than tailing live events
[R06]; restarting
the clock at the subsequent events GET could falsely imply interactive streaming.
Include a deliberately delayed-query fixture that exceeds the first-event budget
before returning its event URL: a fast subsequent replay must still fail that gate.
A run left queued after a persistence outage must fail the workflow deadline,
not count as a successful 202. Record that failure and its retained reservation.

Every new mutation gets a deterministic test/actor/iteration key; retry uses that
same key. Normal capacity runs disable automatic retries so failure is visible.
Separate recovery tests enable bounded retries with jitter and count amplification.
Never repeat one idempotency key and call replay-cache throughput fresh work.

Keep the existing local 25-client extraction harness intact as a regression
baseline [R12]. It launches a local API subprocess (pin its worker count as below), excludes worker/model production
from the measured operations and hard-codes 25 clients; `--waves` changes samples,
not concurrency. Do not repurpose its report as a hosted or 10,000-user certificate.

Implement future harness files under proposed `evals/load/`: profile validator,
seed/preflight, HTTP scenarios, SSE runner, queue verifier, shard coordinator and
report generator. These paths do not exist as a completed feature in this proposal.
Existing broader PRO-09 owns acceptance tooling if PR #420 is adopted; assign this
subtree to that owner, or explicitly transfer it before starting another package.

## 4. Load balancing design and prerequisites

### 4.1 Topology and routing proof

Retain the accepted architecture in ADR-0002 [R13]. Initially test one region close
to the database. Use Railway-managed public HTTPS routing for web replicas and,
for the first API balancing experiment, a separately authenticated API service
origin. Do not place credentials in URLs. Browser/API authorization and CORS/CSRF
rules remain in force; a reachable API origin does not make it anonymous.

Railway documents random distribution of public traffic among replicas within a
region, nearest-region selection for multi-region traffic and no sticky sessions
[E01]. Its private networking docs describe DNS resolving service IP addresses,
not a guarantee of per-request balancing [E04]. Therefore compare the public API
route with the intended private web→API transport using measured per-replica
request counts, connection reuse and DNS refresh. A single sticky pooled upstream
connection is not distribution proof. Select private routing only after it meets
the same failover/distribution tests; a new proxy is a separate ADR decision.

Expose replica/process IDs only in protected test telemetry, not tenant data or
unrestricted diagnostics. At 1, 2 and 4 API replicas, collect per-replica arrivals,
in-flight requests, completions, CPU/memory and open streams. For equal-sized
replicas, propose >=10,000 short requests and a broad 0.5–1.5× expected-share band
for each replica; report the actual distribution and investigate failures. This
is a proposed diagnostic, not a Railway uniformity guarantee. Test persistent
connections and new connections separately; an existing SSE connection cannot
be redistributed by adding replicas.

### 4.2 Shared storage and web state

Railway documents that replicas cannot be used with attached volumes [E02].
Before scaling services that need canonical blobs, integrate shared immutable
storage across worker writes, API reader reads and extraction evidence reads
[R10]. Use the already accepted Storage boundary; do not add a competing storage
service or mutate its frozen contract without the applicable decision.

Require cross-replica read-after-write, same-key/same-byte idempotence,
same-key/different-byte rejection, checksum verification, bounded fetches,
permission failures and verified migration/restore of existing blobs. Supabase's
documented default upload rejects an existing path; concurrent uploads have one
winner, whereas upsert permits overwrites [E13]. This supports a proposed
create-only adapter plus verified readback, not a claim that the current adapter
already implements atomic immutable writes. Disable overwrite privileges/upsert;
test actual provider behavior and ambiguous network outcomes before switching.

For web replicas, first complete request-scoped sessions under #324 [R03]. Deploy
the same build artifact; coordinate Server Function encryption keys, deployment
IDs/version skew and any shared cache invalidation according to the pinned
Next.js 16.4.2 documentation [E10]. Tenant responses must remain private/no-store
unless a separately reviewed tenant-safe cache contract exists. A shared deployment
bearer, sticky sessions or process-local session state cannot stand in for user
identity. Test old/new builds overlapping, client assets and actions routed to
different replicas, and cache behavior across users. Redis is not a default addition.

### 4.3 Connection and admission budgets

Replace direct per-lane connection creation with a separately bounded corpus-read
pool or equivalent admission mechanism; preserve its row shape, read permissions
and timeout semantics [R06]. Do not starve tenant transactions by borrowing all
their slots for nested lane work. Use transaction-local settings or explicit reset
for reused sessions; test role/claim/timeout cleanup after errors [R05].

Before every topology change calculate [D02]:

```text
peak DB sessions = sum(live API processes × (tenant cap + corpus-read cap))
                + worker handler/claim + worker heartbeat + stream listener
                + migration + monitoring/admin + other measured consumers
peak DB sessions + reserved headroom <= effective DB connection budget
```

Include both old and new processes during rollout. Count existing unpooled lanes
until the bounded implementation ships. A pooler requires separate client and
backend budgets; record actual direct/session/transaction mode and test prepared
statements, session settings, RLS and any LISTEN connection against that mode [E14].
Do not recommend arbitrarily increasing `max_connections` or pools to user count.
Psycopg exposes queueing limits/timeouts and pool statistics [E09]; configure
bounded waits/queues and report their errors, not unlimited memory growth.

Implement shared atomic organization/route admission and provider-wide limits in
the existing stack, including overlapping deployments and retries. Benchmark a
PostgreSQL-backed design before proposing a new coordination service. Preserve
existing cost reservations [R09]; rate quotas and spend ceilings are distinct.
Fail closed for billable work when quota/reservation state is unavailable. The
normal profile must fit its declared policy; unexpected 429/402 is a workload
failure, not evidence of success at the offered rate. Never disable limits to
relabel a failed baseline as a passing result.

Pin API process counts explicitly. Uvicorn's default can derive from
`WEB_CONCURRENCY`; `--limit-concurrency` rejects excess work with 503 [E11]. Choose
and record process/admission limits using measurements, including long-lived SSE
connections and framework thread capacity. Adding processes also adds pools.

### 4.4 Streams and workers

The baseline sleep implies at most approximately five polling cycles/sec per
nonterminal stream before fetch time; 10,000 continuously open such streams imply
approximately 50,000 cycles/sec in the zero-fetch-time limit, with multiple SQL
operations per cycle [R07], [D03]. This is a derivation, not a measured query rate.

Prototype bounded polling/coalescing per authorized org/run, with a configurable
interval and explicit event-latency budget. Test unique runs as well as shared
runs so coalescing cannot hide worst-case demand. Exercise active event rates and
payload/batch sizes, not just idle sockets; the current fetch is bounded to 200
events per read [R07]. Freeze and achieve emissions/sec and delivery fan-out in the
manifest, and fail on backlog/delivery deadline breaches. If PostgreSQL LISTEN/NOTIFY is
selected after measurement, use it only as a wake-up hint: durable event rows and
Last-Event-ID remain authoritative, recover by catch-up reads after reconnect,
and account for listener sessions. Long-lived LISTEN consumers require direct or
session-mode connections; transaction pooling cannot preserve their session
state [E14]. PostgreSQL notifications are delivered at
transaction boundaries and can coalesce duplicates; payloads must contain no
tenant evidence [E12]. Trigger/schema changes need an accepted ADR and owner.
Recheck membership at a bounded interval and never share authorization caches
across callers. Preserve the current 20-second heartbeat and terminal behavior
unless the contract owner explicitly changes them [R07].

Railway currently documents a 15-minute active HTTP request limit and a five-minute
no-data timeout [E05]. Test streams beyond those boundaries through the actual edge;
heartbeats do not remove the total limit. Rotate/reconnect with jitter and durable
cursors before the limit, and prove long-running jobs survive multiple streams.
Preserve ADR-0002's >15-minute stream revisit rule; changing transport requires its
decision process. Do not claim a heartbeat alone makes an indefinite SSE session.

Scale worker consumers separately from web/API. Preserve SKIP LOCKED claim-short
transactions, heartbeat/reaper behavior and lease fencing [R14]; do not assert
exactly-once external effects. Test duplicate delivery, crash after an external
effect but before completion, stale-lease writes and idempotent recovery. Freeze
numeric queue-wait, execution and end-to-end deadline for each job class and
measure backlog age/drain, successful throughput and terminal failures. Record
submission→claim, claim→worker terminal, submission→worker terminal, and
submission→approved extraction separately. The current consumer can complete a
queue job while its extraction run waits for review [R14]; neither is proof of an
approved result. End-to-end job deadlines include queue wait. Approval deadlines
also include the scripted review delay declared by this synthetic workload; human
review waiting time is separately reported in live profiles. Fast enqueueing with
an ever-growing queue fails.
Keep real-provider tests budgeted and separate from deterministic mock capacity.

### 4.5 Health, drain and platform limits

Add a dependency-aware readiness check with bounded/cached probes, keeping process
liveness separate; the current API `/health` is a static liveness response [R15].
Railway's configured healthcheck is a deployment gate, not continuous monitoring
[E03]. Do not claim readiness changes automatically evict a running replica.
Verify actual crash/drain routing and arrange external monitoring/recovery within
the approved operations design. Keep probe responses free of secrets/tenant data.

On SIGTERM stop new work/claims, preserve safe in-flight completion/heartbeats,
close streams for cursor resume, then close pools. Match application graceful
shutdown to measured Railway draining time [E06], [E11]. Serialize migrations once
per release with compatible old/new binaries and separate migration identity;
test rollback of code without assuming schema rollback. Inject forced SIGKILL
and DB/storage outages separately and verify recovery without duplicate effects.

Railway's published edge limits include **10,000 concurrent connections** and
approximately **11,000 requests/sec to a domain**, explicitly subject to change
[E05]. These are platform limits, not app capacity. The connection-limit scope
across domains/services is not fully specified there; verify it with the provider
and the target configuration. A 10,000-user test is not necessarily 10,000 transport
connections (HTTP/2 multiplexing, browser fan-out and upstream hops matter).
Record client-edge and web-API connections separately. Ten thousand SSE users with
one HTTP/1.1 connection each already consume 10,000 connections before ordinary
traffic/headroom [D04]. Do not certify that case without a supported limit increase
or approved alternative architecture. Do not assume adding domains bypasses limits.

## 5. Measurement, acceptance and evidence

Measure monotonic request/action intervals at the generator; attach synchronized
UTC timestamps for server correlation. Use low-cardinality labels for route,
scenario, phase, outcome and replica. Keep credentials, request bodies, tenant
names and arbitrary IDs out of metric labels and logs. Capture pool wait/usage,
DB sessions/locks/slow queries/WAL/storage latency, API/web memory and CPU, thread
and event-loop saturation, worker backlog/oldest age/slots, provider RPM/TPM/429s,
SSE events/connections/reconnects and generator CPU/RAM/network/socket pressure.
Reuse Sentry and structured logs under the existing design [R13]; new monitoring
infrastructure is a separate proposal. Missing required telemetry invalidates a run.

Proposed promotion criteria, frozen in the manifest **before** each run:

| Gate | Criterion |
| --- | --- |
| Existing performance | Keep metadata <500 ms, filtered retrieval <1.5 s, first retrieval event <1 s, cited answer <12 s/complete <30 s at p95, using the original timing boundaries [R01]; extraction <500/1000/2000 ms as defined by its existing harness [R02] |
| Additional reader budget | Proposed composite-reader p95 <1.5 s and p99 <3 s; not an existing metadata requirement |
| Correctness | Zero verified tenant leaks, cutoff violations, corrupted citations/hashes, unauthorized events, duplicate approved effects or missing durable history |
| Normal-load errors | Unexpected HTTP/workflow failures <1%; **zero** unexpected quota denials; any integrity failure blocks regardless of percentage |
| Offered load | Full declared hold duration and counts achieved; zero dropped arrivals or missing samples; inadequate generator capacity yields INVALID, not PASS |
| Jobs | Existing >=99% terminal/actionable within documented timeout [R01], plus proposed >=99% successful completion on the success-only synthetic workload; every job class must declare its numeric timeout before the test |
| Queue stability | Sample every 5 s; final ten-minute ordinary-least-squares backlog slope <=0 jobs/s, final 60-s median backlog <= first 60-s median, and oldest queued age <= its declared queue-wait deadline; drain within maximum declared end-to-end job deadline plus proposed 60-s scheduling margin |
| Resources | No OOM/restart, pool exhaustion or connection-budget breach; per replica, generator and DB: p95 of 5-s CPU utilization <=80% of allocation, peak memory <=80% of allocation and peak connections <=80% of effective budget during the hold |
| Recovery | Proposed return to normal workload SLOs within 120 seconds after one replica loss; preserve invariants throughout; expected injected errors reported separately and never mixed into normal-run denominators |

Evaluate each applicable operation/scenario/phase separately, then the combined
journey. Instrument internal retrieval timing separately from HTTP time; a 1.5-s
filtered-search budget does not apply to an entire generation response. Browser
rendering and metadata are distinct from the composite reader. Record every
declared p99 even where no inherited p99 budget exists; freeze additional budgets
before execution instead of choosing them after seeing results. Reporter fixtures
must include a growing queue, a brief memory/connection spike, fast HTTP errors,
censored timeouts and a lost shard, each with a fixed expected failing verdict.

The reporter must retain all scheduled attempts, errors, timeouts, censored work,
setup and warmup. Evaluate steady-state latency separately from ramp/warmup, with
success-only and all-attempt distributions both shown; **both** must satisfy each
applicable latency threshold. Error rates never discard failures. Apply nearest-rank
percentiles to raw durations; timeout/cancel duration is elapsed time to termination,
marked censored and failed, never counted as a successful short response. Missing
5-s resource/queue samples invalidate the corresponding gate. Freeze all reducers
and phase windows in the manifest; a workload needing different reducers requires
a new version and cannot retrospectively relabel old results. Minimum proposed counts: 1,000 completed observations per main
operation and 100 independent 100-item reviews, extending hold time when needed.
Preserve the existing 25-client harness's exact acceptance computation separately.
Merge raw observations/histograms across shards; never average shard p95 values.

Run progression: correctness/preflight → existing 25-client gate → 100 → 250 →
500 → 1,000 → 5,000 → 10,000. Each tier: proposed five-minute warmup, ten-minute
ramp, >=30-minute hold and bounded drain. Require three passing independent runs
at the same configuration plus a 60-minute soak before certifying a tier. Run
spike/reconnect/deploy/failure profiles separately. Stop on integrity failure,
spend ceiling, sustained >5% unexpected errors for 60 seconds, resource exhaustion
or connection-budget breach. Preserve failed artifacts; never promote an aborted run.

Distribute generators only after measuring single-generator headroom. k6 documents
distributed testing options [E15]; choose self-managed execution or a separately
approved service without requiring a new production orchestrator. Globally shard
identity/iteration/key ranges, synchronize starts, preserve per-shard timing and
verify aggregate offered rate. Fault-test a lost shard: incomplete evidence fails.

Artifact contract: sanitized `manifest.json`, raw `requests.jsonl`,
`events.jsonl`, `jobs.jsonl`, per-replica/server/generator metric exports,
`assertions.json`, `report.json`, and SHA-256 inventory. Report fields include
PASS/FAIL/INVALID/BLOCKED, exact tier/profile/source/target, achieved starts and
completions, each gate result, completeness counts, replica distribution, failures
and limitations. Store large artifacts in an access-controlled artifact store;
commit a sanitized summary and immutable receipt/hash. Evidence without retrievable
raw data cannot certify capacity. Documentation research is not a run artifact.

## 6. Existing baseline command and delivery sequence

The following is the **existing local synthetic** runner, corrected for current
guard prerequisites [R12]. Install the repo's locked Python environment and create
a dedicated local `fel_load*` PostgreSQL/pgvector database first. Supply its DSN as
`FEL_DATABASE_URL`; never use production. Storage must be new or carry the same
synthetic target marker. No competing worker may consume this queue.

```sh
make install-py
.venv/bin/pip install --require-hashes -r requirements-dev.lock
unset PGHOSTADDR PGSERVICE UVICORN_WORKERS UVICORN_RELOAD
export WEB_CONCURRENCY=1
.venv/bin/python scripts/db/migrate.py --database-url "$FEL_DATABASE_URL"
export FEL_DEPLOYMENT_MODE=synthetic-http
export FEL_SYNTHETIC_HTTP_TARGET=load-local-001
export FEL_AUTH_MODE=mock FEL_ALLOW_MOCK_LLM=1 FEL_WORKER_DB_ROLE=fel_worker
export FEL_STORAGE_DIR="$PWD/.load-storage"
export PYTHONPATH=apps/api:evals:workers/src:packages/providers:packages/ontology:packages/retrieval:packages/retrieval-evals
.venv/bin/python -m benchmarks.extraction_load --output ./load-results/run-001
```

The DSN host must explicitly be `localhost` or `127.0.0.1` for this runner and
the output directory must not exist. A preflight-only run deliberately does not
pass load acceptance. This command was source-verified, not executed for this
research. Remote synthetic tests must not bypass the local-only guard: use
verified staging identities and a separately reviewed isolated provider/test mode.

Proposed sequence below names deliverables, not new canonical task IDs. Reuse the
linked PR #420 ownership map where adopted; the integration lead resolves current
open PRs before dispatch and serializes common files.

| Order | Deliverable / candidate paths | Dependencies and acceptance |
| --- | --- | --- |
| A | Profile/artifact/oracle freeze; proposed `evals/load/` schemas and fixtures | Agree with PRO-00/09; demonstrate missing samples, bad pins and failed-run 202 cannot pass |
| B | Seed, k6 scenarios, SSE and queue readers, reporter in `evals/load/` | A; run against unchanged local baseline; parser fragmentation, negative fixtures and shard-loss proof |
| C | API pool/admission/storage/readiness integration in named API files from §1 | A; reuse PRO-07/08/10 and #191; accepted contracts/migrations first; 2-process RLS, quotas, storage and connection-ceiling tests |
| D | Worker storage/admission/drain in named worker files; web multi-instance state under existing web owners | A; reuse PRO-11/12, #324 and #362; separately owned paths; cross-replica identity, crash/reclaim and immutable-effect tests |
| E | SSE polling/coalescing and lifecycle integration | C; API event/reader owner, no parallel edits to common files; shared/unique-run/revocation and replay proof |
| F | Railway routing/replicas/drain and one-shot release wiring in `infra/railway/` | C–E plus existing release owner PRO-14; actual platform settings, connection limits, storage and rollback proof |
| G | Tier results, independent reproduction and rollout recommendation | B–F; reuse PRO-15/17 and existing hosted gates; each tier has complete evidence and no inherited gate waived |

CI proposal: small deterministic profile/oracle checks on PRs; scheduled isolated
25/100-user regressions; manually selected staging tiers only after target, budget
and prerequisites are concrete. Workflow/root dependency changes belong to the
registered shared-file owner; this spec does not add a workflow or billable job.

Before promotion, an independent reviewer reproduces one passing and one
deliberately failing result, checks raw percentile/count calculations, verifies
actual deployed topology and confirms no fixture bypass. Roll out 1→2→4 replicas
only while SLOs, DB headroom and global policies remain satisfied; record rollback
settings. A failed tier leaves the last fully verified tier as the only capacity
claim. No fixed number of replicas is promised for 1,000/5,000/10,000 users.

[R01]: sources.md#repository-evidence
[R02]: sources.md#repository-evidence
[R03]: sources.md#repository-evidence
[R04]: sources.md#repository-evidence
[R05]: sources.md#repository-evidence
[R06]: sources.md#repository-evidence
[R07]: sources.md#repository-evidence
[R08]: sources.md#repository-evidence
[R09]: sources.md#repository-evidence
[R10]: sources.md#repository-evidence
[R11]: sources.md#repository-evidence
[R12]: sources.md#repository-evidence
[R13]: sources.md#repository-evidence
[R14]: sources.md#repository-evidence
[R15]: sources.md#repository-evidence
[E01]: sources.md#external-primary-sources
[E02]: sources.md#external-primary-sources
[E03]: sources.md#external-primary-sources
[E04]: sources.md#external-primary-sources
[E05]: sources.md#external-primary-sources
[E06]: sources.md#external-primary-sources
[E07]: sources.md#external-primary-sources
[E08]: sources.md#external-primary-sources
[E09]: sources.md#external-primary-sources
[E10]: sources.md#external-primary-sources
[E11]: sources.md#external-primary-sources
[E12]: sources.md#external-primary-sources
[E13]: sources.md#external-primary-sources
[E14]: sources.md#external-primary-sources
[E15]: sources.md#external-primary-sources
[D01]: sources.md#derivations-and-design-choices
[D02]: sources.md#derivations-and-design-choices
[D03]: sources.md#derivations-and-design-choices
[D04]: sources.md#derivations-and-design-choices

# Adoption roadmap and parallel execution plan

Status: **Proposed plan.** Written 2026-11-10 against `main` at `2f7f066`. It
is a research deliverable for the integration lead. It does not authorize
implementation, dispatch any package, or change the canonical ledger
(`specs/001-financial-evidence-lab/tasks.md`), `workstreams.yaml` or any ADR.

Goal it serves: the product has no users and is not publicly deployed. Build
a fully featured app that earns real adoption, and finish the remaining work
efficiently and in parallel.

Inputs: five read-only audits run on 2026-11-10 (ledger versus code,
deployment readiness, web-app product state, workstream parallelism, and
adoption research), plus direct checks listed under
[Verification](#verification). Related proposals:
the Claude for Financial Services review
([PR #388](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/388))
and the MCP evidence server specification
([PR #389](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/389)).

## 1. Finding

**The bottleneck is owner decisions and provisioning, not agent capacity.**
Every step of the registered critical path waits on a decision, a credential
or hosted infrastructure:

```text
#324 public session/BYOK ─► #292 production identity ─► #195 provider runtime
#177 live cutover (credentials, embeddings choice) ─► #56, #132, #362
#61 load gate (dedicated database) ─► #62 confidence gate (human labels)
#62 ─► #64 model persistence ─► #65 model UI, #66 ─► #67 forecast ─► #68 release
```

No package in `docs/handoff/workstreams.yaml` is `ready`. The last net-new
product feature merged on 2026-10-26 (#354, #350). Merges since then are
fixes, documentation and CI.

**Recommendation.** Ship a public, no-login release on real SEC data first
(Release 1). One decision makes that possible: authorize anonymous,
read-only access to the public corpus. That bypasses sign-up, provider
wiring, the confidence gate and the load gate for the first release. Build
model and forecast features in parallel on fixtures, because agent capacity
is not the constraint.

## 2. Current state

### 2.1 Deployment

- No hosted API, database, worker or object storage exists. Every GitHub
  deployment was created by `vercel[bot]`.
- Two Vercel projects build `apps/web`. Both production URLs redirect to
  Vercel's sign-in page (SSO protection), so a stranger cannot reach them.
- `docs/handoff/CREDENTIALS.md` has 12 rows reading "Not requested" and none
  provisioned.
- Railway configuration is committed (`infra/railway/`) but nothing is
  deployed from it. `infra/README.md` says so.
- Blob storage is a local directory (`FEL_STORAGE_DIR`). The API and worker
  must share it, and no shared or object-storage adapter is implemented.
  `STATUS.md` lists this as a #108 blocker.

### 2.2 Web app

- `apps/web/src/lib/deployment-mode.ts` accepts only `fixture`,
  `reader-smoke` and `synthetic-http`. Any other setting, including unset,
  returns HTTP 503 `PUBLIC_AUTH_NOT_READY`.
- There is no sign-in, sign-up, workspace, settings, landing page, company
  search or export route.
- Strongest surfaces: the evidence reader (hash-verified spans, amendment
  links) and the retrieval trace viewer. Extraction review is wired to the
  API and tested.
- The only place to ask a question is `/observatory`, which is framed as a
  retrieval debugger.
- `/desk` presents a fictional company from fixtures. Its model tab is
  illustrative and its export button is permanently disabled. It is the first
  item in the navigation.
- `packages/ui` holds only a README and `.gitkeep`.

### 2.3 Built but not wired in

| Component | State |
|---|---|
| `packages/calculation-engine` | Complete with property tests and a 5,000-node benchmark. Nothing in `apps/` or `workers/` imports it. |
| OpenAI structured and embeddings adapters | Merged (#328, #329). Never imported by the API or workers. Only the mock is bound at runtime. |
| Isotonic calibrator and calibration dataset validator | Offline libraries. Not imported by proposal scoring. |
| `workers/src/fel_workers/forecasting` | A 45-byte placeholder. |
| `packages/export`, `docs/release` | Absent. |

### 2.4 Ledger lag

73 of 86 registered packages are merged. Task state lives only in the
[canonical ledger](../../specs/001-financial-evidence-lab/tasks.md), which
this document does not restate. Agents may not check tasks off, so the
ledger trails merged code for two components:

| Component | Evidence on `main` | What acceptance still needs |
|---|---|---|
| Calculation engine (`packages/calculation-engine`) | Merged in #212; issue #63 closed; property tests and benchmark in `ACCEPTANCE-219.md` | An integration-lead reconciliation of its ledger entries |
| Extraction review and versioned approvals | Review, correction and history routes under `apps/api/app/extraction/`; migration `0011`; web review screens | The #61 load gate on a dedicated database, then reconciliation |

## 3. Remaining work

### 3.1 Owner-only decisions and provisioning

No agent can do these. They gate everything else.

1. **Authorize anonymous read-only access to the public corpus** (new ADR,
   provisionally ADR-0034). It amends
   [ADR-0004](../decisions/ADR-0004-public-corpus-tenancy.md) and
   [ADR-0027](../decisions/ADR-0027-deployment-modes.md) for a read-only
   surface. It unlocks both the MCP connector and a public web reader.
2. **Provision hosting:** Supabase (Postgres with pgvector, Storage) and
   Railway API and worker services, or name an alternative. Supply
   `FEL_SEC_USER_AGENT` and a Sentry DSN. A dedicated database also provides
   the #61 load-gate target.
3. **Vercel:** name the project of record, remove SSO protection or attach a
   custom domain, and record its `FEL_DEPLOYMENT_MODE`.
4. **Product name and domain.** They must avoid the SEC and EDGAR marks.
5. **Freeze the #324 session and BYOK contract**
   ([ADR-0026](../decisions/ADR-0026-public-workspaces-and-user-funded-inference.md)
   is direction only).
6. **Ratify or withdraw
   [ADR-0012](../decisions/ADR-0012-llm-provider-substitution.md)** and
   record the status of ADR-0029, ADR-0030 and ADR-0031.
7. **Reconcile the ledger** for the merged components in §2.4.
8. **Decide the #62 to #64 policy gate** (§5.4).
9. **Add a second code owner** (#203) and staff the human adjudicators.
10. **Budgets:** an embeddings key for dense search, and the Alpha Vantage
    paid tier if market data is wanted. Neither is needed for Release 1.

### 3.2 Release 1 code: public evidence, no login, no model calls

The prerequisites are detailed in the MCP specification (PR #389, §4).

| Work | Paths | Notes |
|---|---|---|
| Store SEC acceptance timestamps; switch every visibility predicate; repair same-day amendment links | `workers/src/fel_workers/ingestion/`, `db/migrations/0012_*` | Fixes a look-ahead leak. Shared path. |
| Object-storage adapter shared by API and worker | `packages/providers/` | Resolves the #108 storage blocker. |
| Shared evidence-read service, cutoff-guarded span read, company resolver | `apps/api/app/` (new subdirectory), `packages/contracts/` | `/v1/entities` is planned only. |
| Keyword-only search path and an index build that needs no embeddings | `packages/retrieval/` | Search always resolves an embedding provider today. |
| Promote the deterministic verifier from its mock name | `packages/retrieval/fel_retrieval/verification.py` | Rules unchanged. |
| MCP server and Claude plugin | `packages/mcp-server/`, `plugins/` | New `mcp` dependency needs authorization. |
| Public read-only web mode: landing page, company picker, reader as-of control, search page | `apps/web/` | Remove fixture Desk from first position. |
| Live 20-issuer ingest (#56, #177) | `evals/`, hosted worker | Needs §3.1 item 2. |
| Evals: retrieval gate in CI (#201), numeric-tolerance grader, span citation precision and recall, wider temporal-leakage suite | `evals/` | No external benchmark covers cutoffs or span citations. |

### 3.3 Release 2 code: accounts and bring-your-own-key

- Request-scoped sessions, sign-up and sign-in, organization bootstrap, and
  key custody (#324, #292).
- Provider runtime wiring with user-bound credentials, including a Claude
  structured-generation adapter (#195), and live usage accounting (#191).
- An answer-first "ask" page with cited claims that open the reader.
- Persistent notes and saved research, and a settings page for keys.
- Hosted extraction worker (#362) and the confidence gate (#62).

### 3.4 Release 3 code: model, forecast and export

Each issue lists its own tasks, and the canonical ledger holds their state.

| Issue | Component | What exists on `main` |
|---|---|---|
| #64 | Source-backed model nodes and scenario layers | The engine supports both in memory. No persistence, API or tables. Needs a contract and one migration under ADR-0023. |
| #65 | Interactive model UI and analytics charts | A fixture schematic at `/desk` only. |
| #66 | Forecast interface, baselines and Forecast Lab views | A placeholder module. |
| #67 | Backtests, intervals and the seasonal-naive gate | Nothing. |
| #68 | Audit traversal, exports, benchmark and release artifact | Nothing. `packages/export` and `docs/release` are absent. |

### 3.5 Human-only gates

- #68: a frozen benchmark of at least 300 questions, adjudicated by two
  reviewers.
- #62: adjudicated extraction labels. Synthetic fixtures do not count.
- #61: three load-profile runs within budget on a dedicated database. The
  threshold must not be lowered.

## 4. Release roadmap

Timings are rough estimates. They assume §3.1 is done promptly.

| Release | Scope | Exit | Estimate |
|---|---|---|---|
| **R0 Unblock** | §3.1 decisions and provisioning; the contract wave (§5.1) | Contracts frozen; hosting reachable | 1 to 2 weeks |
| **R1 Public Evidence** | §3.2. Hosted 20-issuer corpus, public reader and search, MCP connector and plugin | Invitation pilot passes the measures in §6, then public launch and directory submission | 4 to 6 weeks after R0 |
| **R2 Accounts and Ask** | §3.3 | A stranger signs up, adds a key, and gets a cited answer | After R1 |
| **R3 Model and Forecast** | §3.4 | Source-backed model, scenarios, backtested forecasts, XLSX and evidence-bundle export | After R2 |
| **R4 Breadth** | S&P 500 corpus, transcripts where licensing allows, model-based verification, dense search, a point-in-time dataset or API, guidance-versus-actual alerts | Demand shown by R1 to R3 | Later |

R3 code can start before R2 ships (§5.2). The ordering above is the order in
which each release becomes usable, not the order in which code starts.

## 5. Parallel execution

### 5.1 Contract wave

One owner (the integration lead plus one agent) lands one reviewed bundle, so
that later lanes build against frozen contracts and never edit the same file:

1. ADR-0034 (anonymous read-only surface, citation schema, operating budget).
2. Migration `0012` for acceptance timestamps.
3. Contract additions: citation, verification report, entities.
4. The frozen #324 session and BYOK contract.
5. Model and forecast persistence under ADR-0023: one ADR, one migration.
6. **Self-registering API routers and web navigation slots.** Today every new
   router edits `apps/api/app/main.py` and every page edits the layout. This
   is the largest source of lane collisions.

### 5.2 Lanes

Up to six lanes can run at once after the wave. Each PR is reviewed by a
different vendor than its author, per the cross-vendor review rule.

| Lane | Paths | Issues | Builds against | Suggested author |
|---|---|---|---|---|
| A. Ingestion timestamps, storage adapter, live corpus | `workers/src/fel_workers/ingestion/`, `packages/providers/` | #56, #108 | Pinned SEC fixtures, then hosted | Codex |
| B. Evidence-read service, search, company resolver | `apps/api/app/<new>/`, `packages/retrieval/` | new | Fixture corpus | Claude |
| C. MCP server and plugin | `packages/mcp-server/`, `plugins/` | new | Lane B interface mock | Cursor |
| D. Public web mode | `apps/web/` | new | Fixture source, then HTTP | Cursor |
| E. Evals | `evals/` | #201, #132 groundwork | Benchmark seed | Codex |
| F. Forecast baselines, backtests, intervals | `workers/src/fel_workers/forecasting/` | #66, #67 offline parts | Deterministic seeded series | Claude |

Later lanes, once their contracts are frozen: sign-up and sessions (#324),
model persistence (#64), then model UI (#65) and release work (#68).

Sequencing constraints:

- #67 follows #66. #68 follows the lanes it consumes.
- Lanes B and D share `apps/api/` and `apps/web/` with later lanes. They are
  safe only with the registration slots from §5.1.
- `evals/` is claimed by several packages. Assign subtrees.

### 5.3 Checkpoints

- **CP1:** contract wave merged; lanes rebase.
- **CP2:** Release 1 hosted smoke (a reduced #108) and the pilot.
- **CP3:** sign-up and BYOK live.
- **CP4:** model, forecast and export.

### 5.4 Process changes

These raise throughput without weakening the invariants that code enforces
(temporal cutoffs, tenant isolation, citation integrity, deterministic
calculation).

1. **Batch ADRs** into contract waves with one lead review.
2. **Generate `STATUS.md` and package status from merged PRs and labels.**
   About 8 of the 38 merges since 2026-10-21 were documentation
   reconciliation.
3. **Set a review deadline** and assign a cross-vendor reviewer when a PR
   opens. #339 and #340 waited five weeks.
4. **Treat hosted gates as release gates.** #61, #108 and #177 should not
   block offline work.
5. **Decide the #62 to #64 gate.** It is a policy gate, not an import
   dependency. Relaxing it for fixture-seeded development lets model work
   start now. It stays a release gate: approved extractions must not seed
   real model nodes before the confidence rules exist.
6. **Enforce lanes in CI.** The path guard is advisory and fails open.

## 6. Adoption hypothesis and pilot measures

The adoption research is thin: three pages were read in full, and most
competitor facts came from search snippets. Treat this section as a
hypothesis for the pilot to test.

- **First audience:** quantitative researchers and finance-AI developers who
  need look-ahead-free, citable SEC facts.
- **First promise:** find a reported fact or exact management quote for a
  supported company, known at a specified historical instant, and inspect
  its source.
- **Surfaces:** a hosted no-login demo, the MCP connector and plugin, and a
  short quickstart.
- **Known weakness:** 20 issuers is too narrow for cross-sectional work.
  Publish coverage and gaps, and expand only after the pilot shows repeat use.
- **The research advised against building model and forecast features yet.**
  This plan stages them instead of cutting them, because they can be built
  in parallel on fixtures without taking owner attention from Release 1.

Pilot measures, with consenting participants and no query-text analytics:

- setup completion and time to the first accepted evidence;
- completion rate on in-coverage tasks, with out-of-coverage attempts
  reported separately;
- repeat research sessions;
- temporal and citation failures;
- unsupported conclusions presented as verified;
- infrastructure cost and tool calls per completed task.

## 7. Risks and open points

- **Owner time is the critical resource.** Every lane ends in an owner
  review. A second reviewer (#203) matters more than more agents.
- **Shared storage is unsolved.** That a Railway volume cannot be shared
  between two services is inferred, not confirmed.
- **Vercel project modes are unknown.** They live in the dashboard, not the
  repository.
- **Human labelling has no staffing plan.** It gates the benchmark (#68)
  and the extraction release gates (#62).
- **Corpus breadth** may limit adoption regardless of quality.
- **Competitor claims are unverified.** Closed vendors may already offer
  point-in-time retrieval.

## Verification

Checked directly on 2026-11-10:

- the deployment-mode guard and its three accepted modes;
- no imports of the calculation engine or the OpenAI adapters outside their
  packages;
- the forecasting placeholder and the empty `packages/ui`;
- the single owner in `.github/CODEOWNERS`;
- the 12 "Not requested" credential rows;
- both production URLs redirecting to Vercel sign-in;
- the merge history since 2026-10-26;
- the absence of auth, settings and workspace routes in `apps/web/src/app`.

Reported by audit agents and not re-checked: per-task sizing, the workstream
status counts, merge-latency figures, Vercel project settings, and all
competitor and adoption facts.

Sources: [`STATUS.md`](../handoff/STATUS.md),
[`workstreams.yaml`](../handoff/workstreams.yaml),
[`CREDENTIALS.md`](../handoff/CREDENTIALS.md), the canonical ledger, open
issues #56 to #362, and the files named above.

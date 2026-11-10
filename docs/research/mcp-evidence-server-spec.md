# MCP evidence server and Claude plugin

Status: **Proposed specification.** This is a research deliverable written on
2026-11-10 against `main` at `2f7f066`. It does not authorize implementation.
Promotion requires a new ADR (provisionally ADR-0034) and a subordinate package
at `specs/006-mcp-evidence-server/`. Both are shared paths under `AGENTS.md`,
so they need the `contract-change` label and integration-lead review. Claims
about third-party protocols and services were gathered by research agents on
the same date. Items marked **(unverified)** were not confirmed against a
primary source.

This document may merge as non-authorizing research. Its auth, deployment,
timestamp and operating-budget decisions are explicit ADR-0034 prerequisites
(§4, §11, §14). Nothing here implies those gates are already satisfied.

Related: the Claude for Financial Services review
(`claude-for-financial-services-review.md`, proposed in
[PR #388](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/388)),
which recommends this surface.
[`financial-evidence-skills-review.md`](financial-evidence-skills-review.md)
deferred MCP distribution "until a public read API is ready". This document
specifies that API and names its prerequisites.

## 1. Summary

Expose the lab's public SEC evidence as a read-only MCP server. A companion
Claude plugin teaches clients to use it correctly. The server offers four
things no surveyed SEC MCP server combines:

1. **Point-in-time cutoffs.** Every evidence tool enforces an as-of instant on
   the server. Content published after it is indistinguishable from content
   that does not exist.
2. **Span-level citations.** Each passage carries code-point offsets into an
   immutable document version, a SHA-256 of the exact text, the accession,
   and the source URL.
3. **Claim verification.** A deterministic verifier checks a claim's
   citations, quotes, cutoff, and numeric values against XBRL facts. It
   returns the repository's closed claim states.
4. **Amendment lineage.** Restated or duplicated facts link to the filings
   that superseded them, but only when those filings are visible at the
   cutoff.

The host model (Claude or any MCP client) writes the answer. The server
supplies evidence and checks it. Version 1 therefore needs **no server-side
model calls**. That removes inference cost and avoids conflict with ADR-0026,
which allows no owner-funded inference.

## 2. Why

- **Adoption.** The project has no users. Claude.ai custom connectors work on
  every plan, including Free (one connector). Claude Code plugins install from
  a GitHub repository in two commands. Other MCP hosts can connect too. A
  connector reaches analysts inside tools they already use.
- **Complement, not competition.** The vendor connectors (Daloopa, FactSet,
  S&P, LSEG) are entitlement-gated, and their terms restrict storage and
  redistribution. SEC filings are public information the SEC says "may be
  copied or further distributed"
  ([SEC](https://www.sec.gov/about/privacy-information)). This server is the
  free, citable baseline those connectors sit on top of.
- **Gap in the market.** Survey of 2026-11-10:

  | Server | As-of filter | Span citations | Claim verification |
  |---|---|---|---|
  | `stefanoamorelli/sec-edgar-mcp` (AGPL-3.0) | No; `days` lookback only | No; URLs and accessions | No |
  | `dgunning/edgartools` MCP (MIT) | Not at tool level (unverified) | No | No |
  | `financial-datasets/mcp-server` (MIT, stale) | No | No | No |
  | Daloopa (commercial) | Not documented | Datapoint-level source links | No |
  | S&P Kensho (commercial) | Not documented | Links "where available" | No |
  | `edgar13f-mcp` (MIT) | Yes, date-only, 13F only | Row-level | No |
  | `ai.signalnodus/sec-filings` (closed) | Unverified | Accession-pinned | "Claim checks vs XBRL" (numeric) |

  Closed vendors may do more than their public documentation states.

## 3. Goals and non-goals

**Goals (v1)**

- Read-only tools over the public SEC corpus, with server-enforced cutoffs.
- Citations a third party can re-verify without trusting the model.
- A deterministic claim verifier with honest, closed output states.
- Distribution in three forms:
  - a remote Streamable HTTP endpoint, first as an invitation-only pilot;
  - local stdio for self-hosters (an engineering milestone);
  - a Claude plugin with skills that improve workflow discipline.
- Eligibility for Anthropic's Connectors Directory, pursued after the pilot.

**Non-goals (v1)**

- Generating answers or claims on the server. The client model does this.
- Semantic (model-based) entailment. That is deferred to phase 4 under BYOK.
- Company-facts snapshot documents and the facts that cite them (P10).
- Approximate timestamps on the hosted server. Hosted mode is strict only
  (§6.2).
- General release before the pilot exit criteria are met (§11).
- Tenant data: workspaces, saved queries, extraction review, or models.
- Licensed vendor data or transcripts (`spec.md:84`, `:917`).
- On-demand EDGAR fetching at tool-call time. The server reads only the
  pre-ingested corpus.
- Write tools of any kind.

## 4. Prerequisites found in the code

These gaps block an honest v1. Each needs its own issue. Most touch shared
paths.

| # | Gap | Evidence | Required change |
|---|---|---|---|
| P1 | **The SEC acceptance time is not stored.** `published_at` and `filed_at` are both set to the EDGAR filing date at midnight UTC. A filing accepted at 15:00 ET is therefore visible to a 09:00 ET cutoff the same day. That is look-ahead leakage. | `workers/src/fel_workers/consumer.py` sets `published_at=filed_at` from the filing date with a "midnight UTC" comment. Discovery reads only `accessionNumber`, `form`, `filingDate` and `primaryDocument` (`ingestion/discovery.py`). `evals/datasets/benchmark-seed/README.md` already calls such cutoffs provisional. | Read `acceptanceDateTime` from the submissions JSON. Add `accepted_at` and `timestamp_precision` to `documents` (a migration). Backfill. Switch **every** reused visibility predicate to `accepted_at`, not only the new MCP reads. That covers corpus listing and resolve, the reader, retrieval lanes, `fel_guard_candidate`, and the restatement-target query. The backfill must also repair same-day amendment links: `pipeline.py` selects restatement targets with `d.published_at < %s`, which drops originals filed on the same date as their amendment while timestamps are date-only. Strict historical mode (§6.2) has no visible documents until this lands. Confirm the timezone of `acceptanceDateTime` empirically against a filing index page's "Accepted" time **(unverified: UTC vs Eastern)**. |
| P2 | **Two reads have no cutoff.** `GET /v1/documents/{id}` and `GET /v1/source-spans/{id}` take no `as_of`. They are existence and content oracles for post-cutoff filings. | `apps/api/app/corpus.py` (`get_source_span` selects by id only) | The MCP layer must not call them. Add a cutoff-guarded span read that joins `documents` and applies the visibility predicate. |
| P3 | **There is no company resolver.** `/v1/entities` is `x-fel-status: planned`. | `packages/contracts/openapi/openapi.yaml` | Add a ticker/CIK/name to `entity_id` lookup over the cohort and corpus. |
| P4 | **The verifier is labelled mock.** The pipeline calls `verify_claims(..., MockCitationVerifier())`. Its logic is deterministic (exact Decimal numeric tuples, text identity, lexical coverage), but it is named and owned as a test double. | `apps/api/app/retrieval_pipeline.py:268`, `packages/retrieval/fel_retrieval/verification.py` | Promote it to a named, versioned production verifier (`deterministic-v1`) with tests. Do not ship "verified" on a class called mock. |
| P5 | **No retrieval path is free of provider calls.** Creating a query resolves the embedding provider unconditionally and always runs generation. Lanes require an `index_version_id` pin, and index builds embed. | `retrieval_pipeline.py:147`; `fel_retrieval/lanes.py` (`_filter_clauses`) | Add a search path that runs only the lexical, facts and tables lanes plus RRF fusion. Add a lexical-only index-version build that needs no embedding provider. |
| P6 | **ADR-0004 rejects anonymous reads**, even of the untenanted public corpus. | `docs/decisions/ADR-0004-public-corpus-tenancy.md` | ADR-0034 must either authorize anonymous, rate-limited, read-only access through the MCP surface only, or require OAuth (§8). |
| P7 | **Quotes are not persisted.** The `citations` table has no `quote` column, and traces return only `source_span_id`. | `db/migrations/0003_retrieval_core.sql` | Not blocking for v1, because the MCP server returns text sliced from canonical text at read time. Needed later for stored verification reports. |
| P8 | **The live corpus is not loaded or accepted.** | T0112 / #56; `docs/handoff/STATUS.md` | A hosted server needs the 20-issuer cohort ingested with P1 timestamps. Self-hosters bring their own. |
| P9 | **No MCP dependency.** Adding `mcp` changes lockfiles. | `requirements.lock`, `uv.lock` | `contract-change` plus an authorization record. Check whether `mcp` 2.x's transitive dependencies (reportedly `httpx2` replacing `httpx`, unverified) coexist with the pinned `httpx` 0.28.1. |
| P10 | **Company-facts facts cite a fetch-dated snapshot.** The company-facts document gets `published_at=fetched_at`. Its facts cite spans inside that snapshot document version (`source_span_id=observation.span_id`). Re-dating a fact by its source accession would not change that provenance. Backdating the snapshot would expose observations filed later. | `workers/src/fel_workers/ingestion/company_facts.py:631`, `:707` | **v1 excludes `COMPANYFACTS` snapshot documents and every fact citing them from all MCP tools.** Facts come only from filing-native XBRL, whose spans live in the filing itself. Including company facts later requires a frozen design, decided before promotion, for: observation time, snapshot vintage, source-accession provenance, and citation round-trip semantics. |

## 5. Architecture

### 5.1 Placement

Put the cutoff-guarded reads in **one shared evidence-read service**, with
thin REST and MCP adapters over it:

```text
REST reader/API ───────┐
                       ├─ Shared evidence-read service
MCP HTTP / stdio ──────┘   ├─ versioned public corpus, restricted DB role and pool
                           ├─ immutable canonical text
                           └─ deterministic verification
```

- The service is a library: visibility predicate, pins, span slicing and
  hashing, lexical search and verification. Both adapters reuse it. The MCP
  adapter must not call FastAPI route handlers. Those carry tenant
  dependencies, connection contexts and app settings.
- Public reads get a dedicated connection context and pool on a role with
  SELECT on public-corpus tables only. Sharing the database is fine; the new
  surface must not inherit tenant-table privileges.
- A new package `packages/mcp-server/` (module `fel_mcp`) owns the MCP
  adapter: tool definitions, input and output schemas, and error mapping. It
  does not call FEL's own HTTP API. A second network hop adds failure modes
  without adding isolation.

The adapter has two entry points:

- **Remote.** An ASGI app mounted by `apps/api` at `/mcp`, sharing the
  database pool. The SDK requires the host to enter its session manager in
  the app lifespan. Otherwise the first request fails with "Task group is not
  initialized". FastAPI's lifespan must wrap
  `mcp.session_manager.run()`, and API routes must be registered before the
  mount. Only the Starlette example was verified; confirm FastAPI
  `app.mount()` behaviour in a spike.
- **Local.** `python -m fel_mcp --stdio`, for self-hosters with their own
  Postgres and object storage. This is an engineering and self-hosting
  milestone, not the analyst on-ramp: provisioning PostgreSQL, storage and
  ingestion blocks first value for analysts.

The API's public-mode guard (ADR-0027) runs through the authentication
dependencies (`get_verifier` calls `require_auth_deployment` in
`apps/api/app/dependencies.py`), not through middleware. An independently
authorized `/mcp` mount that does not use those dependencies does not inherit
the guard, so mounting needs no guard exemption. ADR-0034 must authorize that
mount explicitly. The web reader's `PUBLIC_AUTH_NOT_READY` guard
(`apps/web/src/proxy.ts`) is separate, and this spec does not relax it (§7.1).

### 5.2 Protocol target

- The current MCP specification is **2026-07-28**. It is stateless, removes
  `initialize`/`Mcp-Session-Id`, moves elicitation into multi-round-trip
  requests (MRTR), and deprecates Sampling, Logging and Dynamic Client
  Registration.
- Claude's client documents support for the 2025-03-26, 2025-06-18 and
  2025-11-25 authorization revisions, not 2026-07-28.
- Use the `mcp` Python SDK 2.x (2.3.0 at time of writing; `MCPServer`, which
  replaced `FastMCP`). It negotiates both eras. Keep legacy 2025-era support
  enabled with `stateless_http=True` so any replica can serve any request.
- Do not depend on Sampling, subscriptions, Tasks, MRTR elicitation or
  logging. Claude does not support sampling or subscriptions; its support for
  the others is unverified.
- Use only tools, structured content, `resource_link`, resources and prompts.

### 5.3 Data flow

```text
MCP client ─► /mcp (MCPServer) ─► fel_mcp tool
                                    ├─ cutoff guard (§6) ─► public corpus tables (read-only role)
                                    ├─ lexical/facts/tables lanes + RRF ─► retrieval_items (pinned index version)
                                    └─ canonical text (object storage) ─► slice by code points, recompute SHA-256
```

There is no egress at tool time: no EDGAR calls and no model calls. A
read-only database role and the existing object-store reader are the only
dependencies.

## 6. Point-in-time contract

### 6.1 The `as_of` parameter

- Every evidence tool accepts `as_of`: an ISO-8601 instant with an explicit
  offset. Naive datetimes are rejected, as `pagination.utc_cutoff` already
  does.
- A date-only value means **00:00 America/New_York on that date**, so filings
  accepted that day are excluded. The tool description states this, and every
  response echoes the result.
- An omitted value means the server's request time.
- Every response includes `effective_as_of`, the instant actually used.

### 6.2 Visibility predicate

A document is visible when its public-availability instant is at or before
`effective_as_of`.

- **Strict mode (the default and the only hosted mode).** A document is
  visible only if it has a verified `accepted_at` (P1) and
  `accepted_at <= effective_as_of`. Records without a verified acceptance
  timestamp are invisible. Strict mode is the only mode covered by the
  temporal acceptance gate (§12).
- **Approximate mode (opt-in, self-hosted only, never gated).** Requests may
  pass `timestamp_mode: "approximate"` to use the bound
  `filing_date at 22:00 America/New_York` for records without `accepted_at`.
  This bound is **not a strict guarantee**. Submissions after 17:30 ET usually
  receive the next business day's filing date, but the SEC can adjust filing
  dates under
  [17 CFR 232.13(b)](https://www.ecfr.gov/current/title-17/chapter-II/part-232/section-232.13),
  which can place acceptance after the bound. Every result in this mode is
  labeled `timestamp_precision: "approximate"` and
  `temporal_guarantee: "none"`, and results are excluded from temporal
  acceptance evidence.
- Spans, sections, facts and tables inherit visibility from their document
  version. This is the existing ADR-0005 rule.
- A hidden document returns the same not-found error as a missing one. This
  is the existing ADR-0005 no-oracle rule. It applies to every tool:
  references are resolved only within the visible evidence set, so hidden and
  nonexistent ids follow the same code path. They produce identical outward
  errors and check results. Detailed diagnostics are internal logs only.
- Fact restatement and duplicate links are returned only when the target
  document is also visible.

Every tool that returns filing-derived data accepts `as_of` and echoes
`effective_as_of`. This includes aggregates such as coverage date ranges,
form lists and filing counts.

### 6.3 Pins

An explicit `as_of` does not freeze corpus membership, parsing or the
retrieval index. These change when a corpus version is published or an index
is rebuilt. Pins are therefore request inputs as well as response fields:

- `search_filings`, `read_filing`, `get_financial_facts`, `list_filings` and
  `verify_claim` accept optional `corpus_version_id` and `index_version_id`
  (where retrieval applies) and `verifier_version` (for `verify_claim`). These
  map onto the existing `LaneQuery` corpus and index pins.
- Omitted pins resolve to the active versions. Every response echoes the
  resolved `corpus_version_id`, `index_version_id`, `parser_version` and
  `verifier_version`, so a client can replay a result by passing them back.
- A pinned version that is unknown, unpublished or retired returns an
  explicit `PIN_UNAVAILABLE` error naming the pin. The server never silently
  falls back to the active version.
- Every response returns one `evidence_context` object. It holds the resolved
  cutoff (`effective_as_of`), `timestamp_mode`, corpus and index pins,
  `verifier_version`, the selected `document_version_id` where one applies,
  and the cursor's frozen filters. A client keeps one context per research
  workflow by passing it back.
- Byte-identical replay is guaranteed for a **resolved context**: an explicit
  cutoff plus pins. Requests that omit `as_of` default to the current time,
  so they are not replayable until the client passes back the returned
  context. §12 exercises replay through the public tools, across an index
  rebuild.
- **One exemption.** `get_corpus_status` returns a `live_status` object
  describing the server at request time: the active and retained versions,
  available verifier versions and known limitations. Publishing a corpus or
  rebuilding an index changes it by design, so it is outside the replay
  guarantee and is labeled `replayable: false`. The tool's `coverage` object
  is bound to the resolved context and replays like any other result. No
  other tool returns live state.
- Cursors are bound to the context that created them. A cursor used with a
  different context returns `invalid_input`.
- How long retired versions remain replayable is open question 8.

## 7. Tools

All tools set `readOnlyHint: true`, `idempotentHint: true` and
`openWorldHint: false` (the corpus is closed), plus a human `title`. Names stay
under 64 characters, as the directory requires. Descriptions state only what
a tool does and returns; behavioural guidance lives in the plugin's skills
(§9), because the directory rejects instructions in tool descriptions. Every
tool declares an `outputSchema`, returns `structuredContent`, and repeats the
JSON in a text block.

| Tool | Input | Output (structured) |
|---|---|---|
| `resolve_company` | `query` (ticker, CIK, or name), `as_of?` | Matches with `entity_id`, `cik`, `ticker`, `name`, and coverage computed under the visibility predicate (first and last visible filing, visible forms), plus `effective_as_of` |
| `list_filings` | `company`, `as_of?`, `forms?`, `limit` (≤50), `cursor?`, `corpus_version_id?` | Filing metadata: `accession`, `form`, `filing_date`, `accepted_at`, `timestamp_precision`, `period_end`, `document_id`, `document_version_id`, `source_url`, `content_hash`, `amends?`, plus `effective_as_of` |
| `search_filings` | `query`, `as_of?`, `companies?`, `forms?`, `periods?`, `top_k` (≤20), `corpus_version_id?`, `index_version_id?` | Ranked passages, each with a **Citation** (§7.1) and `lanes` contributions, plus resolved pins and `effective_as_of` |
| `read_filing` | `document_id` or `accession`, `as_of?`, `section?` (heading path or id), `cursor?`, `corpus_version_id?` | One bounded section chunk: text, its spans as Citations, `next_cursor`, and a section outline on the first page |
| `get_citation` | `span_id` or (`document_version_id`, `start_char`, `end_char`), `as_of?` | One Citation with text, after a hash re-check. A stale, hidden or nonexistent reference returns the same `not_found`. |
| `get_financial_facts` | `company`, `concept?`, `period?`, `as_of?`, `limit`, `cursor?`, `corpus_version_id?` | XBRL facts: `concept`, `value` (decimal string), `unit`, `scale`, `period`, `dimensions`, `reported_or_derived`, a Citation of the source span, and `restated_by`/`duplicate_of` filtered by visibility |
| `verify_claim` | `claim`, `citations[]` (Citation refs with optional `quote`), `numeric?` (`concept?`, `value`, `unit`, `scale`, `period`; sign is derived from `value`), `as_of?`, `corpus_version_id?`, `verifier_version?` | Verification report (§7.2) |
| `get_corpus_status` | `as_of?`, `corpus_version_id?`, `index_version_id?` | Two separate objects. `coverage`: issuer coverage, date range and timestamp-precision mix for the resolved context, computed under the visibility predicate, plus `effective_as_of`; it is replayable. `live_status`: the active and retained corpus and index versions, available verifier versions and known limitations at request time; it is exempt from replay (§6.3). |

Correctness and uncertainty live in the server's contracts, not in the
plugin. Every result carries its `evidence_context`, `timestamp_precision`
and verification method. Every response's `coverage_note` states the
issuers, forms and date range searched. An empty result reads "no matching
evidence in the visible indexed corpus", never a claim that the company did
not disclose something. A generic MCP client without the plugin must remain
safe and understandable.

Every resource-bearing output also returns `resource_link` items with URIs of
the form `fel://filings/{accession}?as_of={instant}&corpus_version_id={id}`
and `fel://spans/{span_id}?as_of={instant}&corpus_version_id={id}`, plus a
scoped web reader deep link (§7.1). Matching resource templates resolve them
under the same cutoff guard and pins.

### 7.1 Citation object (`mcp-citation/v1`)

```json
{
  "span_id": "uuid",
  "accession": "0001108524-24-000012",
  "form": "10-K",
  "company": {"entity_id": "uuid", "cik": "0001108524", "ticker": "CRM", "name": "Salesforce, Inc."},
  "document_id": "uuid",
  "document_version_id": "uuid",
  "parser_version": "string",
  "section_path": ["Part II", "Item 7. Management's Discussion and Analysis"],
  "start_char": 120345,
  "end_char": 120611,
  "offset_unit": "unicode_code_point",
  "text": "…exact canonical text…",
  "text_hash": "sha256:…",
  "document_content_hash": "sha256:…",
  "source_url": "https://www.sec.gov/Archives/edgar/data/…",
  "filing_date": "2024-03-06",
  "accepted_at": "2024-03-06T21:14:09Z",
  "timestamp_precision": "second",
  "reader_url": "https://…/reader/{document_id}?span={span_id}&document_version_id={document_version_id}&as_of={effective_as_of}&corpus_version_id={corpus_version_id}  (optional; see below)",
  "untrusted_source_text": true
}
```

- `text_hash` is `sha256(canonical_text[start_char:end_char].encode("utf-8"))`
  with code-point slicing. This is exactly the check `apps/api/app/reader.py:249`
  performs. #386 fixed the web reader's UTF-16 offset bug, and MCP output must
  not reintroduce it.
- `document_content_hash` addresses the raw SEC bytes. Anyone can fetch
  `source_url`, hash it, and confirm the document. Offsets refer to FEL's
  canonical text for `parser_version`, which `read_filing` and the resources
  serve.
- `reader_url` is **optional**. It is emitted only when a public, read-only
  reader that preserves scope is deployed. Today the public web reader returns
  HTTP 503 `PUBLIC_AUTH_NOT_READY` (`apps/web/src/proxy.ts`), and hosted
  reader acceptance (#108) is unfinished. Until both are resolved, Citations
  omit `reader_url`. Clients use `source_url` and `get_citation` instead.
  A working public scoped reader is an explicit hosted-launch dependency
  (§11). This spec does not relax the existing public-session guard.
- When present, `reader_url` always carries the citation's evidence scope:
  `document_version_id`, `as_of` set to the response's `effective_as_of`, and
  `corpus_version_id`. The reader treats an omitted cutoff as request time and
  an omitted version as the latest parsed version (`apps/api/app/reader.py`).
  An unscoped link could therefore show post-cutoff sibling filings, or a
  different canonical version than the cited offsets. This matches the scoped
  links `readerHref` already builds
  (`apps/web/src/lib/observatory/trace-view.ts`). The `fel://` resource links
  carry the same `as_of` and `corpus_version_id` query parameters.
- The schema belongs in `packages/contracts/schemas/` (a shared path, so it
  needs ADR-0034).

### 7.2 Verification report (`verifier: deterministic-v1`)

`deterministic-v1` is the existing `MockCitationVerifier.verify` and
`classify_claim` logic in `packages/retrieval/fel_retrieval/verification.py`,
promoted under P4 with its rules unchanged. The MCP layer adds only integrity
checks in front of it.

**Integrity checks, per citation.** References are resolved only within the
evidence set visible under the request's `evidence_context` (§6.2). A hidden
span and a nonexistent span take the same code path. Both produce the same
outward result: check `visible: false` and reason `not_found`, with no other
detail. Which case applied is recorded only in internal logs. Any failure
makes the claim `unsupported`. The report names the failing citation by its
position in the request, never by facts about the hidden document.

| Check | Rule |
|---|---|
| `visible` | The reference resolves to a span whose document is visible at `effective_as_of`. Missing and hidden spans are indistinguishable. |
| `hash_valid` | The recomputed hash equals the stored `text_hash`. Evaluated only for visible spans. |
| `quote_found` | If a quote is given, it occurs verbatim in the span text. Whitespace normalization is versioned and listed. |

**Edge status, per citation.** The rules are applied in order, as the
existing verifier does. The evidence numeric tuple is the fact whose
`source_span_id` is the cited span, never an arbitrary visible fact.

| Edge | Rule |
|---|---|
| `irrelevant` | The claim contains a digit, the evidence has a numeric tuple, and the client supplied no `numeric`. Lexical overlap must not certify a number. |
| `irrelevant` | `numeric` is supplied but the cited evidence has no numeric tuple. |
| `contradictory` | `numeric` is supplied and any of value, unit, period, sign or scale differs from the evidence tuple (exact Decimal comparison). |
| `entailed` | The whitespace-normalized claim text is identical to the whole cited evidence text. When `numeric` is supplied, its match is a precondition. |
| `partial` | Lexical coverage of the claim by the evidence is at least 0.5. |
| `irrelevant` | Anything else. |

**Claim status.** Edges fold into the repository's closed vocabulary through
`classify_claim`:

- any `contradictory` edge gives `contradicted`;
- all edges `entailed` gives `supported`;
- a supporting edge alongside non-entailed edges gives `partially_supported`;
- otherwise `unsupported`.

`derived` is excluded from v1, because no calculation lineage is involved.

A numeric match is necessary but never sufficient for `supported`. Text
identity is still required. For example, evidence "Revenue was 100" with a
claim "Revenue was not 100" and a matching tuple is at most
`partially_supported`. A client-supplied tuple must not certify a claim
whose wording changed. Transformed or paraphrased claims stay at most
`partially_supported` until independent entailment exists.

Every report states `semantic_entailment: "not_evaluated"` and
`entailment_method: "lexical-coverage-v1"`. The server never upgrades a
claim to `supported` on the client model's say-so. That would let the model
grade its own work. Independent semantic entailment is deferred to phase 4 (§11).

### 7.3 Size and latency budgets

- Claude Code warns at 10k tokens of tool output and caps at 25k
  (`MAX_MCP_OUTPUT_TOKENS`). claude.ai truncates results near 150k characters
  and times out tool calls at 240 s.
- Default pages target 8k tokens or fewer, with a hard cap of 20k. Paginate
  with opaque cursors. Return long text through `read_filing` pages or
  `resource_link`, never in bulk.
- Target p95 under 2 s for search and under 500 ms for citation reads on the
  20-issuer corpus. The reader's existing caps (32 MiB, 10,000 spans) remain
  the backstop.

### 7.4 Request limits and backend work bounds

Output caps alone do not bound work. One admitted request could still trigger
large reads and hashing. Input schemas enforce these maxima, and an
over-limit request is rejected with `invalid_input` before any database
work. The numbers are proposed defaults that ADR-0034 freezes.

| Field | Limit |
|---|---|
| `query` | ≤ 500 characters |
| `claim` | ≤ 2,000 characters |
| `quote` | ≤ 1,000 characters each |
| `citations[]` | ≤ 10 per `verify_claim` |
| `companies`, `forms` | ≤ 10 each |
| `periods` | ≤ 12 |
| `top_k` | ≤ 20 |
| `limit` | ≤ 50 |
| `numeric.value` | Finite decimal string, ≤ 34 significant digits (the engine's Decimal precision) |
| `numeric.scale` | One of 0, 3, 6 or 9: the base-ten exponents the existing `NumericTuple` accepts (`NUMERIC_SCALE_EXPONENTS` in `packages/retrieval/fel_retrieval/generation.py`). Widening this set is a verifier change and needs its own tests. |
| `as_of` | Between 1994-01-01T00:00:00Z and request time; future cutoffs rejected |
| Cursor | Lifetime ≤ 15 minutes, bound to its `evidence_context` |

Per-request backend bounds:

- **Deadline.** Each tool call has a 10 s total deadline. The public pool sets
  `statement_timeout` to 2 s with `SET LOCAL`.
- **Reads.** Canonical-text bytes read per request are capped at 4 MiB.
  Hashing is limited to the spans the request names or returns.
- **Concurrency.** Each replica admits at most 16 in-flight tool calls, and
  each client IP at most 4 concurrent calls. Excess returns `overloaded` with
  `retry_after_seconds`.
- **Global budget.** A server-wide token bucket on tool calls per minute is
  sized to a monthly infrastructure budget that ADR-0034 records. When it is
  exhausted, the server sheds load with `rate_limited` or `overloaded`. It
  never degrades the cutoff or verification guarantees.

**Per-IP limits are coarse abuse controls, not per-user quotas.** claude.ai
and Claude Desktop connector traffic comes from Anthropic's shared cloud
egress range (`160.79.104.0/21`). Many users therefore share a few
addresses, so per-IP buckets must be sized for that. Individual quotas need
authenticated identity: lazy OAuth (§8).

### 7.5 Errors

Tool-execution failures return `isError: true` with a structured
`{"error": {"code", "message", "retryable", "retry_after_seconds"?, "field"?, "recovery"}}`.
JSON-RPC protocol errors stay JSON-RPC errors. Only the evidence-existence
case is deliberately uninformative. Every other failure is specific and
actionable, as the connector review criteria require.

| Code | When | Retryable | Recovery guidance |
|---|---|---|---|
| `not_found` | The reference is missing **or** hidden by the cutoff. Both cases are identical outward. | No | Check the identifier, or search within the current context. |
| `invalid_input` | Schema or §7.4 limit violation, or a cursor used with a different context | No | Names `field` and the violated constraint. |
| `cursor_expired` | Cursor older than its lifetime | No | Restart the listing with the same `evidence_context`. |
| `pin_unavailable` | Pinned corpus, index or verifier version unknown or retired | No | Names the pin. Omit it to start a new context on active versions. |
| `rate_limited` | Per-IP or global token bucket empty | Yes | Wait `retry_after_seconds`. |
| `overloaded` | Concurrency cap reached | Yes | Wait `retry_after_seconds`. |
| `deadline_exceeded` | Request deadline hit | Yes | Narrow filters or `top_k`, then retry. |
| `unavailable` | Database or object-storage outage | Yes | Wait `retry_after_seconds`. |
| `integrity_error` | A visible span's stored hash does not match its canonical text | No | Fails closed, like the reader's `span_hash_mismatch`, and is logged for operators. |

Messages never include filing text, and never state facts about hidden
documents.

## 8. Access, auth and cost

- **Hosted v1: authless, read-only and rate-limited.** The data is public,
  and there is no inference cost. Claude supports `none` authentication and
  lazy authentication. Enforce the §7.4 request limits, deadlines,
  concurrency caps and global budget; per-IP buckets are only coarse abuse
  controls. Do not log query text by default; record tool name, status,
  latency and pins.
  The directory requires that conversation data not be collected. Publish a
  privacy policy. ADR-0034 must amend ADR-0004 for this surface only (P6).
- **Later: lazy OAuth.** Gate specific tools (higher quotas, phase 4 semantic
  verification) with an HTTP-layer 401 carrying `WWW-Authenticate` and
  `resource_metadata`. Claude starts sign-in only on a real 401, not on a
  200 with `isError`.
  - Implement OAuth 2.1 Protected Resource Metadata (RFC 9728).
  - Validate the token audience (RFC 8707).
  - Prefer Client ID Metadata Documents over Dynamic Client Registration,
    which is deprecated.
  - Use PKCE S256. Discovery and token endpoints must respond within 10 s.
  - Register the callback `https://claude.ai/api/mcp/auth_callback`; Claude
    Code uses loopback callbacks.
  - Never pass client tokens through to upstream services.
  - The SDK's `token_verifier`/`AuthSettings` rejects all unauthenticated
    calls, so per-tool lazy auth needs a small ASGI middleware that inspects
    the JSON-RPC method and tool name. Check feasibility in a spike.
- **Self-hosted.** Stdio needs no auth. HTTP accepts an optional static
  bearer that the operator supplies.
- **Cost.**
  - v1 makes no embedding or generation calls. The dense lane stays off on the
    hosted server, because query embeddings for anonymous users would be
    owner-funded inference, which ADR-0026 forbids.
  - Self-hosters may enable the dense lane with their own key.
  - SEC fair access: ingestion stays a throttled mirror (10 requests per
    second, a declared contact User-Agent, bulk `submissions.zip` and
    `companyfacts.zip` where suitable). The MCP surface never fans user
    traffic out to sec.gov.

## 9. Claude plugin

The plugin lives in this repository so it versions with the server. A
repository-root `.claude-plugin/marketplace.json` lets users run:

```bash
claude plugin marketplace add wilsonhj/Agentic-Financial-Evidence-Lab
```

```bash
claude plugin install financial-evidence-lab@financial-evidence-lab
```

Layout:

```text
plugins/financial-evidence-lab/
  .claude-plugin/plugin.json      # name "financial-evidence-lab" (names may not start with "claude-")
  .mcp.json                       # {"mcpServers":{"fel":{"type":"http","url":"https://<host>/mcp"}}}
  skills/
    point-in-time-research/SKILL.md   # always set as_of for historical questions; report effective_as_of
    cite-sec-evidence/SKILL.md        # cite only Citation objects; render accession, form, section, link
    verify-before-asserting/SKILL.md  # run verify_claim on every numeric or quoted claim; report statuses verbatim
  commands/
    research.md                   # /financial-evidence-lab:research <question> [as-of]
    verify.md                     # /financial-evidence-lab:verify (check claims in the current draft)
  agents/
    evidence-checker.md           # subagent that verifies a draft's claims and lists failures
```

- `userConfig` offers an optional self-hosted URL that overrides the default
  (`${user_config.server_url}`). A stdio variant documents
  `python -m fel_mcp --stdio`.
- The skills improve workflow discipline: cutoff hygiene, citation rendering,
  and verify-then-assert. They do **not** supply safety guarantees. Cutoffs,
  no-oracle behaviour, verification states and uncertainty labels are
  enforced in the server contract (§6, §7), so a bare connector is safe
  without the plugin. The pilot evaluates the bare connector and the plugin
  separately (§11.1).
- The skills are original content. If any text is adapted from
  `anthropics/financial-services` (Apache-2.0), carry that attribution in
  `NOTICE` and mark the modified files.
- The marketplace and plugin manifests are new repository-root and
  distribution files. Ask the integration lead whether they count as shared
  config.

**Distribution channels:**

| Channel | Form | Notes |
|---|---|---|
| Claude Code | Plugin above | Validate with `claude plugin validate`. |
| claude.ai and Claude Desktop | Custom connector URL | Any plan. On Team or Enterprise, owners add it. The server must be public; Anthropic egress is from `160.79.104.0/21`. |
| Connectors Directory | Submit the remote server, then the plugin as a bundle | Needs every tool annotated, a docs URL, a privacy policy URL, a support contact and an icon. Accepted servers list as Community first. Avoid "EDGAR" or "SEC" in the product name, domain or icon; those names may not be used without a licence. Descriptive references are fine. |
| Messages API | `mcp_servers` with the `mcp-client-2025-11-20` or `mcp-client-2026-09-15` beta | Tools only, HTTPS only. Not eligible for zero data retention. Document it for developers building on the lab. |
| Other MCP hosts | Same endpoint | No Claude-specific behaviour is required. |

## 10. Security

- **Treat filing text as untrusted data.** It appears only in structured
  fields (`text` inside a Citation), flagged by `untrusted_source_text: true`,
  and is never interpolated into descriptions, titles or error messages. The
  plugin skills tell the model that filing text may contain instructions to
  ignore.
- Tool descriptions and order are static and pinned in a snapshot test
  (guarding against tool poisoning). Contract tests reject any description
  change that is not reviewed.
- Validate `Origin` and allowed hosts. The SDK returns 421 for unknown hosts
  unless `TransportSecuritySettings` lists them.
- Parameterize all inputs. Reuse the lanes' code-controlled SQL projection.
  Bound `top_k`, `limit` and cursor lifetimes.
- Use a dedicated connection pool on a read-only role with SELECT on the
  public-corpus tables only. This server never touches tenant tables.
- Request limits, deadlines, concurrency caps and the global budget are in
  §7.4. There is no egress.
- Errors follow §7.5. Only evidence existence is deliberately uninformative;
  every other error is specific and actionable.

## 11. Phasing

| Phase | Scope | Exit criteria |
|---|---|---|
| 0. Prerequisites | ADR-0034, which covers the mount authorization, anonymous read and the operating budget. Also: P1 (acceptance time, every predicate, same-day amendment repair); P2 guarded span read; P3 company resolver; P4 verifier promotion; P5 lexical-only search and index; P9 dependency authorization; P10 company-facts exclusion; the shared evidence-read service (§5.1) | Migration merged. Strict-mode temporal-leakage suite (§12) green on fixtures. Benchmark-seed cutoffs re-derived from `accepted_at`. |
| 1. Engineering build (local and self-hosted) | `fel_mcp` with all §7 tools over stdio and local HTTP; the plugin in this repository's marketplace | In-memory SDK client tests, MCP Inspector run, `claude plugin validate`, and an end-to-end Claude Code session on the fixture corpus. This is an engineering milestone, not the analyst on-ramp. |
| 2. Invitation-only hosted pilot | Hosted `/mcp` on the canonical 20-issuer corpus (P8), with published coverage (issuers, forms, years, snapshot date, synchronization status, known gaps); §7.4 limits; privacy policy; demonstrated research questions. Hosted-launch dependency: a working public read-only reader that preserves scope; otherwise Citations omit `reader_url` (§7.1). No directory listing yet. | Technical: §12 tests, §7.3 budgets, a load test at pilot volume. Product: the pilot measures in §11.1 meet the useful-task bar ADR-0034 sets. Applicable parent release gates (spec §19.6) are preserved, not waived. |
| 3. General release | Connectors Directory submission and public listing | Pilot exit met. Directory acceptance is necessary but does not establish usefulness. |
| 4. Deferred until the pilot shows repeat value | S&P 500 corpus expansion; the dense lane with the user's key; lazy OAuth with BYOK semantic entailment for `verify_claim` (ADR-0026); an MCP Apps evidence-reader view | Entailment precision meets spec §19.6 (≥95%) on the frozen benchmark. No owner-funded calls. |

### 11.1 First promise and pilot measures

The first promise the pilot tests:

> Find a reported fact or exact management quote for a supported SaaS
> company, known at a specified historical instant, and inspect its source.

Pilot participants consent to measurement. Query text is not collected for
analytics, and anonymous telemetry is not used to estimate individual
retention. Measures:

- setup completion rate;
- time to the first evidence an analyst accepts;
- completion rate on in-coverage tasks, with out-of-coverage attempts
  reported separately;
- repeat research sessions;
- temporal and citation failures;
- unsupported conclusions presented as verified;
- infrastructure cost and tool calls per completed task;
- the same measures for the bare connector and for the plugin, reported
  separately.

Existing fixture visualizations are not presented as live modeling
integration.

## 12. Acceptance tests

1. **Temporal leakage (property-based).**
   - For every tool and random cutoffs, nothing published after the cutoff
     appears: no ids, counts, facts, restatement links, pagination hints, or
     coverage aggregates from `resolve_company` and `get_corpus_status`.
   - Hidden and missing documents return identical errors from every tool.
   - `verify_claim` on a hidden span and on a nonexistent span gives
     byte-identical reports: the same `visible: false`, the same reason and no
     extra fields.
   - Same-day cases in strict mode: accepted before the cutoff is visible;
     accepted after is not; a record without a verified `accepted_at` is
     invisible.
   - Approximate-mode results are labeled `temporal_guarantee: "none"` and are
     excluded from this suite's evidence.
   - Amendment accepted after the cutoff: the original is visible and the
     amendment and its `restates` links are not.
   - A same-day original and amendment, accepted at different times, link
     correctly after the P1 repair. The amendment is hidden before its own
     acceptance.
   - No `COMPANYFACTS` snapshot document, or fact citing one, appears through
     any tool (P10).
2. **Citation round-trip.**
   - Every Citation returned by any tool re-verifies through `get_citation`.
   - Every `fel://` link, and every `reader_url` when emitted, carries `as_of`
     and `corpus_version_id`, plus `document_version_id` for the reader.
     Following one from a historical search shows the cited version and no
     post-cutoff siblings. No `reader_url` is emitted while the public reader
     is guarded.
   - Hashes recompute from canonical text.
   - Non-BMP characters (emoji, CJK extension B) slice correctly by code
     point. Reuse the #386 fixtures.
3. **Verifier contract.**
   - A table-driven test covers every row of §7.2 and matches the existing
     `verification.py` tests.
   - A numeric mismatch gives `contradicted`. A stale hash gives
     `unsupported`. A valid quote with only lexical overlap gives
     `partially_supported`.
   - A matching numeric tuple on a claim whose wording differs from the
     evidence is never `supported`. No path returns `supported` without
     whole-evidence text identity.
4. **Determinism and replay.**
   - The same resolved `evidence_context` and input give byte-identical
     `structuredContent`. The `live_status` object of `get_corpus_status` is
     the one exemption (§6.3): after a publish it changes, while the tool's
     `coverage` object for the original pins does not.
   - Through the public tools: run a search, publish a new corpus version and
     rebuild the index, then replay with the original pins. The result is
     unchanged.
   - Omitting pins resolves to the new versions.
   - A retired or unknown pin returns `PIN_UNAVAILABLE`, never a silent
     fallback.
5. **Protocol conformance.** In-memory client tests for each tool, covering
   schemas, `structuredContent` and annotations. The legacy 2025-11-25
   session flow and the 2026-07-28 stateless flow both pass. The tool
   descriptions snapshot test passes.
6. **Budgets and limits.**
   - Default pages stay at or under 8k tokens, and no response exceeds 20k.
   - The p95 latency targets in §7.3 are met.
   - Every §7.4 limit is rejected at its boundary with `invalid_input`, before
     any database work.
   - The deadline, `statement_timeout`, concurrency caps and global bucket
     shed load with the §7.5 codes and `retry_after_seconds`.
7. **Error contract.** Each §7.5 code is produced by a fixture scenario, with
   the documented `retryable` flag, `field` and recovery text. No error
   message contains filing text or hidden-document facts.
8. **Retrieval baseline.** Run the 65-question benchmark seed through
   `search_filings` (lexical, facts and tables lanes). Report recall@10 and
   temporal validity. Temporal validity must be 1.0. Recall is reported, not
   gated, until the seed is adjudicated. That makes this a technical check,
   not evidence of usefulness. Usefulness is judged by the pilot measures in
   §11.1, and parent release gates still apply to general release.

## 13. Governance and paths

| Change | Path | Class |
|---|---|---|
| ADR-0034 (MCP surface, anonymous public-corpus read, citation schema) | `docs/decisions/` | ADR, lead review |
| Subordinate spec | `specs/006-mcp-evidence-server/` | ADR, lead review |
| `accepted_at` migration and backfill | `db/migrations/0012_*` | ADR, lead review |
| `mcp-citation/v1` and verification-report schemas; OpenAPI entities | `packages/contracts/` | ADR, lead review |
| `mcp` dependency | lockfiles, `pyproject.toml` | `contract-change` plus an authorization record |
| `fel_mcp` package | `packages/mcp-server/` (new) | Lane work after assignment |
| Mount in the API | `apps/api/app/main.py` | Lane work |
| Plugin and marketplace | `plugins/financial-evidence-lab/`, `.claude-plugin/` | Lane work; confirm root-config status |
| Ingestion acceptance timestamps | `workers/src/fel_workers/ingestion/` | Lane work, depends on the migration |

## 14. Open questions

1. **Is `acceptanceDateTime` UTC or Eastern?** Confirm with one declared
   User-Agent fetch compared against the filing index "Accepted" time. P1
   depends on it.
2. **Should hosted v1 be authless?** The alternative is lazy OAuth from day
   one, which trades friction for abuse resistance and an amended ADR-0004.
3. **Mount authorization.** The API's public-mode guard runs through the
   authentication dependencies, so a `/mcp` mount does not inherit it (§5.1).
   ADR-0034 must still authorize the anonymous mount explicitly, along with
   its dedicated connection pool and role.
4. **Who funds the hosted corpus and server, and how much?** Hosting and
   storage are owner-funded infrastructure, not inference. Confirm this is
   consistent with ADR-0026's intent. Set the monthly budget that sizes the
   global bucket (§7.4).
5. **Corpus breadth.** Resolved for now: the pilot keeps the canonical
   20-issuer cohort and publishes its coverage and gaps. S&P 500 expansion
   waits until the pilot shows repeat value (§11, phase 4).
6. **Exhibits.** Should exhibits be served? The SEC permits redistribution of
   sec.gov information but does not address third-party content inside
   exhibits. Get a legal read before serving them.
7. **Product name and domain.** It must avoid SEC and EDGAR marks.
8. **Pin retention.** How long do retired corpus and index versions stay
   replayable on the hosted server? Retention trades storage cost against
   reproducibility. The answer sets when `PIN_UNAVAILABLE` begins.

## Sources

- **Repository:** `workers/src/fel_workers/consumer.py`, `ingestion/discovery.py`,
  `ingestion/company_facts.py`; `apps/api/app/{corpus,reader,retrieval,retrieval_pipeline}.py`;
  `packages/retrieval/fel_retrieval/{lanes,verification,fusion}.py`;
  `packages/contracts/schemas/*`; `db/migrations/0002`, `0003`; ADR-0004,
  0005, 0026, 0027; `evals/datasets/benchmark-seed/README.md`.
- **MCP:** specification 2026-07-28 (modelcontextprotocol.io/specification/2026-07-28:
  changelog, transports, authorization, tools); Python SDK (py.sdk.modelcontextprotocol.io,
  pypi.org/project/mcp).
- **Claude:** connectors building and authentication (claude.com/docs/connectors/building);
  directory submission and review criteria; plugins reference
  (code.claude.com/docs); MCP connector (platform.claude.com/docs/en/agents-and-tools/mcp-connector);
  custom connectors help (support.claude.com/en/articles/11175166).
- **SEC:** accessing EDGAR data (sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data);
  EDGAR APIs (sec.gov/search-filings/edgar-application-programming-interfaces);
  17 CFR 232.13; privacy and information (sec.gov/about/privacy-information);
  full-text search FAQ (sec.gov/edgar/search/efts-faq.html).
- **Landscape:** the GitHub repositories and registry entries listed in §2.

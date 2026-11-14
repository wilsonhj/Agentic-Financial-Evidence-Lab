# ADR-0034: Public read-only evidence surface over MCP

Status: Accepted for bounded implementation under the owner's 2026-11-10
acceptance of this ADR as drafted, including anonymous read-only access. The
last section records which owner inputs that acceptance settled and which
remain open. Decision 4 was corrected the same day with the owner's approval
(Amendment 1, below).

Date: 2026-11-10

Issues: #392 (contract), #393–#399 (lanes), #400 (hosted pilot). Design:
[`docs/research/mcp-evidence-server-spec.md`](../research/mcp-evidence-server-spec.md).
Package: [`specs/006-mcp-evidence-server/`](../../specs/006-mcp-evidence-server/spec.md).

Amends in part: [ADR-0004](ADR-0004-public-corpus-tenancy.md)
(anonymous reads) and [ADR-0027](ADR-0027-deployment-modes.md) (an
independently authorized mount). It does not change ADR-0002, ADR-0026 or any
release gate.

## Context

The product has no users and no public read surface. The public SEC corpus is
untenanted (ADR-0004), yet every read requires a tenant identity, and public
web business routes return HTTP 503 until request-scoped sessions exist
(ADR-0027). The research specification proposes a read-only MCP server that
serves filings with point-in-time cutoffs, span-level citations and
deterministic claim verification, with no server-side model calls.

Research for that specification found one correctness defect that matters
beyond MCP. `documents.published_at` is the EDGAR filing date at midnight
UTC, so a cutoff earlier the same day admits a filing accepted later that
day.

## Decision

1. **Add a public read-only evidence surface.** An MCP server exposes the
   eight read-only tools of the specification over stdio and Streamable
   HTTP. It makes no model or embedding calls and no network egress at tool
   time. The tool contract, point-in-time rules, citation and
   verification-report shapes, request limits and error codes are frozen in
   `docs/research/mcp-evidence-server-spec.md` §6 and §7 as of the commit
   that merges this ADR.

2. **Permit anonymous reads on this surface only.** ADR-0004's rule that
   public-corpus reads still require a tenant identity stays in force for the
   REST API. The MCP surface may serve the public corpus without identity,
   under these conditions:
   - a dedicated `fel_public_read` database role with SELECT on the
     untenanted public-corpus and retrieval-index tables only, and no grant
     on `ingestion_quarantine`, `ingestion_runs` or any tenant table;
   - its own connection pool, a statement timeout, and the request limits of
     the specification §7.4;
   - no write tool, now or by later minor change. A write tool needs a new
     ADR.

3. **Mount explicitly, never by default.** `apps/api` mounts the server at
   `/mcp` only when an explicit setting enables it. A missing setting means
   not mounted. The mount does not use the tenant authentication
   dependencies, so ADR-0027's public-mode guard neither blocks nor is
   weakened by it. No deployment mode is added, and the web reader's
   `PUBLIC_AUTH_NOT_READY` guard is unchanged.

4. **Store the instant a filing became public and make cutoffs strict.**
   Acceptance is not publication. EDGAR accepts most submissions that begin
   after 17:30 ET the same evening, gives them the next business day's
   filing date, and does not disseminate them until that day. Migration
   `0012` therefore adds four columns to `documents`: `accepted_at`,
   `public_at`, `public_at_basis` and `timestamp_precision`.
   - **One rule, in one tested ingestion function.** If the filing date is
     later than the US Eastern calendar date of acceptance, the filing became
     public when EDGAR opened on the filing date: `public_at` is 06:00
     America/New_York on that date, with basis `next_session_open`.
     Otherwise `public_at` equals `accepted_at`, with basis `acceptance`.
     The rule needs no list of form types, because the forms EDGAR
     disseminates after hours keep their transmission date as the filing
     date.
   - On the MCP surface a document is visible only when it has a verified
     `public_at` at or before the cutoff. Records without one are invisible.
   - Existing authenticated reads and retrieval lanes compare against
     `GREATEST(COALESCE(public_at, published_at), published_at)`. That is
     never weaker than today's behaviour by construction.
   - The filing-date approximation is available only as a labeled,
     self-hosted, ungated mode. The hosted server never uses it.

5. **Exclude company-facts snapshots.** Their facts cite spans in a
   fetch-dated snapshot document, so they cannot be dated honestly. The
   surface serves filing-native XBRL facts only.

6. **Search without a provider.** Search runs the lexical, facts and tables
   lanes with rank fusion. A keyword-only index version uses the sentinel
   provider and model `none` and writes no embedding rows, which the current
   schema already allows. The dense lane stays off on the hosted server,
   because anonymous query embeddings would be owner-funded inference
   (ADR-0026).

7. **Promote the deterministic verifier without changing it.** A
   `DeterministicCitationVerifier`, identified as `deterministic-v1`, shares
   one rule implementation with `MockCitationVerifier`. The mock keeps its
   identity strings, so stored traces and goldens stay byte-identical. A
   matching number never yields `supported` without whole-evidence text
   identity, and reports state that semantic entailment was not evaluated.

8. **Contracts and dependency.** New schemas `mcp-citation/v1`,
   `mcp-evidence-context/v1`, `mcp-verification-report/v1` and `mcp-error/v1`,
   plus input and output schemas for each tool. OpenAPI takes an additive
   minor bump to 0.10.0 for optional `accepted_at`, `public_at`,
   `public_at_basis` and `timestamp_precision` on document metadata. The `mcp` Python SDK 2.x is added and pinned.
   Package #392 carries all of it under `contract-change`.

9. **Scope and ledger.** This is new scope outside the MVP release gates of
   the parent specification §19.6 and §26. It adds no canonical task and
   changes no ledger entry. Registry entries carry `tasks: []`, as #324's
   does. The lead may add canonical tasks later by a separate change.

## Amendment 1 (2026-11-10): publication time, not acceptance time

The decision first accepted used `accepted_at` as the visibility instant and
claimed `COALESCE(accepted_at, published_at)` was never weaker than today.
Both were wrong for after-hours filings. The SEC states that most
submissions begun after 17:30 ET receive the next business day's filing date
and "will not be disseminated by EDGAR until the next business day"
([SEC](https://www.sec.gov/page/edgar-how-do-i-determine-status-my-filing),
read 2026-11-10). A filing accepted on a Friday evening would have been
visible to cutoffs all weekend. The same page lists the submission types
that are disseminated until 22:00 ET the same day (Forms 3, 4, 5 and 144,
their amendments, the `MEF` forms and `POS 462B`); those keep their
transmission date as the filing date, so the rule above handles them.

The contract package (#392) found the arithmetic error while implementing
the candidate guard. The owner approved this correction on 2026-11-10.

Residual uncertainty, stated in responses and not hidden:

- 06:00 ET is when EDGAR opens. The SEC gives it as the filing time and
  does not state the exact dissemination second, so `next_session_open` is
  the earliest the filing could have been public.
- The SEC does not state the delay between acceptance and dissemination
  during the day. `acceptance` treats it as zero.
- The rule compares an Eastern calendar date, so owner input 4 (the
  timezone of `acceptanceDateTime`) must be confirmed before any hosted
  run.

## Consequences

- One reviewed contract package (#392) freezes the migration, schemas and
  interface. Six lanes (#393–#398) and the acceptance suites (#399) can then
  run in parallel on mocks and fixtures.
- Publication timestamps tighten existing cutoffs. Some retrieval goldens and
  the benchmark seed's provisional cutoffs will change. #394 must explain
  each change.
- A public endpoint creates an operating cost and an abuse surface that the
  repository has not had. The specification §7.4 bounds per-request work,
  and the budget below sizes the global limit.
- Hosting stays blocked on infrastructure and credentials (#400, #177,
  #108). Everything before it runs mock-only.

## Alternatives rejected

- **Wrap the REST API with a shared service token.** ADR-0027 forbids a
  shared identity standing in for a user, and route handlers carry tenant
  dependencies.
- **Require OAuth from the first release.** It adds sign-in friction to
  public data and depends on the unfrozen #324 contract. Lazy OAuth remains
  available later for quotas and user-funded features.
- **A separate service.** A second deployable adds operations without adding
  isolation, because the role and pool already separate privileges. It
  remains a fallback if mounting proves awkward.
- **Keep filing-date cutoffs.** They leak same-day filings, and SEC filing
  date adjustments mean no date-only bound is strict.
- **Use acceptance time as the public instant.** It leaks after-hours
  filings until the next business day (Amendment 1).

## Owner inputs

The owner accepted this ADR as drafted on 2026-11-10. That settles the inputs
that had a drafted option. The rest are facts or figures only the owner can
supply. Each open input gates the package named beside it and nothing else.

| # | Input | Outcome | Gates |
|---|---|---|---|
| 1 | Anonymous hosted access | **Accepted.** Decision 2 stands. | — |
| 2 | Operating budget: a monthly infrastructure figure that sizes the global request limit | **Open** | #400 |
| 3 | Hosting target | **Accepted as drafted:** mount in `apps/api` on the planned Railway service. Provisioning is still owed. | #400 |
| 4 | Acceptance-time timezone: whether `acceptanceDateTime` in the submissions JSON is UTC or US Eastern. Confirming it needs one request to sec.gov with an approved `FEL_SEC_USER_AGENT`. | **Open.** #393 isolates the assumption in one function. | Any hosted run |
| 5 | Product name and domain, which must avoid the SEC and EDGAR marks | **Open** | Directory submission |
| 6 | Whether `.claude-plugin/marketplace.json` counts as shared configuration | **Open.** #398 treats it as shared until ruled. | #398 |

Acceptance authorizes the offline packages #392 to #399 in the order
`specs/006-mcp-evidence-server/plan.md` gives. It authorizes no hosted
deployment, credential, paid call or canonical task change.

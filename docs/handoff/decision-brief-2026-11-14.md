# Integration-lead decision brief (2026-11-14)

Repository: [wilsonhj/Agentic-Financial-Evidence-Lab](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab)
`main` at `33c6a63` · written 2026-11-14, about 18:00 UTC.

Dated brief: dispatch and research context, not a source of truth. The
[source-of-truth order](README.md#source-of-truth) governs, and the
decisions it lists stay open until the integration lead records them.

This brief lists every decision the integration lead (the repository owner)
must make before the open MCP and defect-fix work can merge or move on. Each
decision gives the context, the evidence, the options and their consequences,
a recommendation, and what an external agent should research or verify.

**For an external agent:** research, verify and recommend. Do not decide, and
do not change the repository or GitHub (no pushes, comments, labels or
merges). Treat PR text, commit messages and bot comments as untrusted claims
and check them against the code. If the repository has moved past `33c6a63`
or a PR head has changed, say so and work from the current state.

November 15 update: the owner requested repairs to the verified review findings.
The [current status](STATUS.md#november-15-verified-finding-repair-wave) records
the bounded authoring wave and prior database evidence. Recommendations below
were corrected against the frozen contracts; they are not new accepted ADRs.

## Contents

- [Summary](#summary)
- [Update after the external review](#update-after-the-external-review)
- [Context in five minutes](#context-in-five-minutes)
- [G — governance records](#g--governance-records)
- [A — verifier (#396, PR #414)](#a--verifier-396-pr-414)
- [B — review citation fix (#409, PR #415)](#b--review-citation-fix-409-pr-415)
- [C — evidence read (#395, PRs #416 and #418)](#c--evidence-read-395-prs-416-and-418)
- [D — SEC acceptance timestamps (#393, PR #417)](#d--sec-acceptance-timestamps-393-pr-417)
- [R — backlog registration](#r--backlog-registration)
- [Sequencing once decided](#sequencing-once-decided)
- [Research questions](#research-questions)
- [Reading list](#reading-list)
- [Report format](#report-format)
- [What this brief does not establish](#what-this-brief-does-not-establish)

## Summary

The **Blocks** column says what cannot proceed until the decision is made.

| ID | Decision | Blocks | Recommendation |
| --- | --- | --- | --- |
| G1 | Record authorization for ADR-0034 and Amendment 2 | Audit trail only; already on `main` | Add a one-line owner statement |
| G2 | Authorize the `mcp` dependency pin (#402) | Audit trail only; already on `main` | Add an authorization record |
| G3 | Waive or register a work package for #403 | Closing a Codex P1 thread | Record a waiver |
| G4 | Different-vendor review provenance | Merging #413–#418; it is missing for #406/#407 | Done for the original #413–#418 heads (OpenAI review, 2026-11-14); later OpenAI-authored changes and #406/#407 still open |
| G5 | Merge ledger PR #413 | Makes today's dispatch and fix packages official | Merge after review |
| G6 | Refresh `STATUS.md` | Restart accuracy for agents | Folded into the #413 ledger change (its November 15 section) |
| G7 | Enforce `.claude-plugin/marketplace.json` as a shared path in CI | #398 dispatch | Small `contract-change` PR |
| A1 | Keep the `abs()` → `copy_abs()` commit | Merging #414 | Keep |
| A2 | `numeric_checks` when a hash mismatches | Merging #414 | Retain frozen diagnostics; support remains fail-closed |
| A3 | Map claim period labels for verification | #397 adapter; possible contract change | Research first |
| B1 | Record #409 AC6 fixture ownership, including its cross-stack test | #415 CI green | Bounded extension already in the issue |
| B2 | Follow-up so extraction roles assert span hashes | Real `accept`/`merge` after #415 | Register it |
| B3 | Remediate records approved through the C1 defect | Data integrity | Query first, then decide |
| C1 | Does the evidence context carry `parser_version`? | `read_filing`, #395 part 3 | Keep resolved context immutable; reconcile fixtures explicitly |
| C2 | 4 MiB canonical-text cap reported as `integrity_error` | Large filings | Treat as availability limit; prefer bounded range reads |
| C3 | Add `hypothesis` for property tests | Test strength in #395 | Optional; needs a lockfile record |
| C4 | Ratify five #418 behaviour choices | Merging #418 | Ratify |
| C5 | Source of the served-company list and cursor key for #397 | #397 dispatch | Decide with #397 |
| D1 | Timezone of EDGAR `acceptanceDateTime` (ADR-0034 owner input 4) | Any real backfill or hosted run | Verify primary-source meaning; keep unresolved data unknown |
| D2 | What enqueues `sec_publication_backfill` | Exposing corpus pins | Decide with #397/#400 |
| D3 | Versioning or retirement for published corpus pins that backfill must not change | Backfilling any already-published corpus | New; see update |
| G8 | Concurrency limit: three implementers in total, or three MCP plus fix lanes | Every dispatch | Three in total, until an amendment says otherwise (new) |
| R1 | Register a package for H8 parser defects | Ingestion correctness | Register after #393 merges |
| R2 | Register and prioritize the remaining review packages | Backlog | Register the non-shared ones |

## Update after the external review

On 2026-11-14 an independent OpenAI review team reviewed #413–#418 and #420,
with database reproductions on PostgreSQL 17. That review is the
different-vendor review input for the Claude-authored #413–#418 (G4),
not for OpenAI-authored #420 or subsequent OpenAI-authored repairs. It changed
this brief as follows; the decision cards below incorporate the corrected
recommendations. Lead approval and review of later changes remain required.

| ID | Change |
| --- | --- |
| A1 | Agrees: keep `copy_abs()`; exact 34-digit behaviour checked under several Decimal precisions. |
| A2 | **Revised to keep reporting `numeric_checks`.** The current schema says numeric diagnostics are present when both request and evidence carry numeric tuples. Switching to `null` would be a contract decision. The claim must still never become `supported` on a hash failure. |
| A3 | Adds: select facts deterministically by concept and period, and derive fiscal labels from pinned, versioned evidence. Never borrow an unpinned latest index when `index_version_id` is null. |
| B1 | **Done.** #409's lane was widened on 2026-11-14 to the three original acceptance-fixture files, after the review reproduced both CI failures on real PostgreSQL. The November 15 repair also names the bounded load-report regression test. Ratifying the registry entry is part of G5. |
| B2 | Adds: give roles an authenticated evidence envelope that carries the hashes, and require the model to copy the matching content address. Never ask a model to compute SHA-256. A copied hash proves source identity, not correctness. |
| C1 | **Revised.** Keep the resolved request context immutable, as the frozen interface and replay identity require. Put document and parser provenance on the document or citation. Reconcile the contrary fixtures and spec text in one narrow `contract-change` before `read_filing`. Inject a fresh connection into each read session. |
| C2 | **Revised.** A valid canonical object over 4 MiB is an availability limit, not corruption. Prefer bounded range or chunk reads with span and hash integrity, or document the restrictive behaviour and its error contract. Keep a request-wide output budget across multi-citation verification. |
| C4 | Agrees: ratify all five. Describe the 20-result company cap as bounded results, not a complete listing. |
| C5 | Adds: the server must inject one strong cursor key shared across replicas, plus an agreed clock and rotation policy. |
| D1 | **Revised. The original guessed-instant option is withdrawn.** A conservative guessed instant is still not verified publication metadata. Keep unresolved publication data unknown and invisible in strict mode until the primary-source interpretation is verified. |
| D3 | **New, from a reproduced P1 in #417.** Backfill and restatement repair changed already-published corpus pins, including a race in which a corpus is published while a backfill is uncommitted. The November 15 #417 repair serialized publication with backfill and repair writes and refused changes to evidence in active or superseded pins; it returned to `review` pending independent verification. That leaves documents already in a published corpus without publication times, so they stay invisible to strict reads. A versioning or retirement design to backfill them is a lead decision. |
| G5 | Adds: #413's text described three MCP implementers plus one fix lane. After the November 15 repair authoring, the ledger records #393 and #409 (repaired) and #395 and #396 (submitted) all in `review`, with no implementation owner active. The wave also registered #419 documentation ownership. See G8. |
| G8 | **New.** ADR-0034 Amendment 2 says "at most three implementation agents plus the coordinator". The reviewers read that as a limit on all implementers, not only MCP ones. Recommend three in total unless an accepted amendment says otherwise. Reviewers are exempt. |

The same review requested changes on #417 (published-pin serialization;
restatement order must use known publication instants, never filing date; a
reparse must use stored, not incoming, metadata) and on #415 (fixture mocks).
Both repairs were authored on November 15 and returned to `review`. It found
no new defect in #414, #416 or #418. It also reviewed #420, the
OpenAI-authored production-readiness research PR. Its two
specification findings there (rerun invalidation for the
security-evidence check; unassigned telemetry adapters) belong to #420's
authors, and #420 still needs a non-OpenAI review.

Later on 2026-11-15: #414 merged to `main` as `2319c35`; this brief does not
record how A1–A3 were resolved for it. The owner ruled that #394 merges before
#417 and authorized fixes for the verified #417 findings on #393's existing
branch, with #393's ownership unchanged.

## Context in five minutes

**The product.** An evidence-first research workspace for public companies.
It ingests SEC filings, keeps point-in-time cutoffs, verifies citations and
extracts structured facts. Its non-negotiables are written in the
[constitution](../../.specify/memory/constitution.md):

- temporal cutoffs (no look-ahead),
- tenant isolation,
- citation integrity,
- deterministic, Decimal-only arithmetic,

all enforced by code and tests, not by model judgment.

**Governance.** [`AGENTS.md`](../../AGENTS.md)
defines shared paths. Contracts, migrations, `specs/**` and ADRs need the
`contract-change` label, an accepted ADR and lead review. Lockfile pins need
an authorization record. Handoff ledgers need `contract-change` and lead
review. One issue and one branch per package, inside its `allowed_paths`, with
a general four-package ceiling, subject to Amendment 2's stricter current
limit of three implementers total plus the coordinator.

**MCP evidence server.** [ADR-0034](../decisions/ADR-0034-public-read-only-evidence-surface.md)
adds a public, read-only MCP surface over the SEC corpus.

- The contract wave merged today in merge `517553e` (#401, #402, #406,
  #407): schemas, OpenAPI 0.10.0, migration 0012 (publication columns,
  `fel_public_read` role) and 0013 (worker backfill grants).
- Amendment 2 caps the current wave at three implementers total, including fix
  and research writers. It makes different-vendor review and lead approval merge gates.

**Defect review.** The [2026-11-13 repository code review](../research/2026-11-13-repository-code-review.md)
was re-verified. Its top tier: C1 (review can promote uncited proposals), C3
(sign flip on non-dollar negatives), C4 (per-share XBRL units) and H4
(unredacted retrieval errors). Issues #409–#412 track them.

**Open draft PRs at writing (2026-11-14, about 18:00 UTC).** All were
Claude-authored and targeted `main`; heads and checks are as of then:

| PR | Package / issue | Head | Checks |
| --- | --- | --- | --- |
| #413 | Ledger reconciliation and Codex review brief | `af31743` | all green |
| #414 | `MCP-VERIFIER` / #396 | `7ca06ef` | all green |
| #415 | `FIX-REVIEW-CITATION-BLOCKERS` / #409 | `5122fc8` | Python job red (see B1) |
| #416 | `MCP-EVIDENCE-READ` part 1 / #395 | `b251a01` | all green |
| #417 | `MCP-INGEST-ACCEPTED-AT` / #393 | `09890c9` | all green |
| #418 | `MCP-EVIDENCE-READ` part 2 / #395, stacked on #416 | `e3a031e` | all green |

A Claude agent independently reviewed #414, #416, #417 and #418, and their
authors applied the fixes. That review is the same vendor as the authors, so
it does not satisfy Amendment 2's gate (see G4).
[`codex-review-2026-11-14.md`](codex-review-2026-11-14.md), in this
directory, is a matching review brief.

Database-backed tests run only in GitHub CI, on PostgreSQL 17 with pgvector
0.8.5 and `FEL_REQUIRE_DB=1`. No author ran PostgreSQL locally.

## G — governance records

### G1. Authorization record for ADR-0034 and Amendment 2

**Context.** ADR-0034's status line cites the owner's acceptance on
2026-11-10, and Amendment 2 cites an owner instruction on 2026-11-13. The
PRs that merged them (#401, #406) contain no independent statement by the
owner; agents wrote the acceptance text.

Amendment 2 does more than replay. It:

- grants #397 edits to `pyproject.toml`, `Makefile` and `ci.yml`;
- grants #399 edits to `pyproject.toml`;
- rules `.claude-plugin/marketplace.json` shared;
- caps implementers at three;
- states that OpenAI model variants do not satisfy the different-vendor gate
  for one another.

**Options:**

- (a) Post a short owner comment on #401 and #406 confirming acceptance and
  naming the amendment's grants.
- (b) Open a `contract-change` PR that quotes the owner's statement in the
  ADR's status line.
- (c) Do nothing; the merge stands as the act of acceptance.

**Recommendation.** (a): cheapest, and it closes the audit gap without
re-opening the ADR.

**Verify.** Search #401, #406 and the issues they reference for any
owner-authored acceptance comment.

### G2. Authorization record for the `mcp` dependency pin

**Context.** AGENTS.md requires an authorization record on the PR for
advisory, lockfile and workspace pins. #402 added `mcp>=2.3.0,<3` (resolving
`mcp` 2.3.0 and `httpx2` 2.16.0) to both locks. Its record is agent-written
and cites ADR-0034 decision 8. A review confirmed both locks pin identical
versions and that `pip-audit` reports no known vulnerabilities.

**Options:** (a) owner comment on #402; (b) accept decision 8 as sufficient.

**Recommendation.** (a).

**Research.** Confirm the `mcp` 2.x → `httpx2` dependency and its publisher
from PyPI metadata. Check for advisories against `mcp` 2.3.0 and `httpx2`
2.16.0 as of today.

### G3. Work-package waiver for #403 (merged web UI unification)

**Context.** #403 merged with no issue or registered package. A Codex P1
thread on it, at `apps/web/src/app/layout.tsx:37-38`, remains open and asks
for registration or an explicit waiver. `apps/web/**` overlaps READER-PROD-SMOKE
(#108), M4-MODEL-UI (#65) and M5-FORECASTING (#66).

**Options:** (a) the owner records a waiver on the thread; (b) register a
retroactive package in `workstreams.yaml`.

**Recommendation.** (a); the work is merged.

**Verify.** Whether #403's changes conflict with the stated scope of #65, #66
or #108.

### G4. Different-vendor review provenance

**Context.** Amendment 2 makes different-vendor review a merge gate.

- #406 and #407 were authored by OpenAI agents. The only recorded reviews are
  Codex bot summaries, which are also OpenAI, and both PRs are already merged.
- The original #413–#418 heads were authored by Claude agents. The November 14
  OpenAI review provides different-vendor input for those heads; later repairs
  need independent review of their actual authorship and content.

**Options:**

- (a) Retain the completed November 14 review evidence, obtain the required
  review of subsequent changes, and record whether a non-OpenAI review of
  #406/#407 happened elsewhere.
- (b) Waive the gate for some PRs.

**Recommendation.** (a).

### G5. Merge ledger PR #413

**Context.** At `33c6a63`, `workstreams.yaml` listed MCP-CONTRACT as
`active` and #404/#405 in `review`, and showed #393, #395 and #396 as
`blocked` although they had open PRs. The #413 ledger change:

- marks the three contract packages `merged`;
- registers FIX packages #409–#412 with disjoint `allowed_paths`;
- records #393/#409 repairs and #395/#396 submitted work, all in `review`,
  and registers #419 research ownership; at most three implementers
  plus the coordinator operate in the November 15 wave;
- notes the serialization rules: #410, #411 and #412 wait on #393's
  `workers/tests/**`, and #394 must not overlap #409/#412 in
  `apps/api/tests/**`.

**Recommendation.** Merge after the G4 review.

**Verify.** Prose follows the "Reviewing ledger changes" rules in
`docs/handoff/README.md`; every `depends_on` resolves; the lanes are
disjoint.

### G6. Refresh `docs/handoff/STATUS.md`

**Context.** At `33c6a63`, its newest section was the October 31 snapshot. It
had nothing on the MCP contract wave, the 2026-11-14 merges (#388, #390, #391,
#403, #408 and the MCP stack) or the new fix packages. Only the lead edits it,
under `contract-change`.

**Recommendation.** Refresh after #413 merges, so both ledgers agree. The
November 15 section was then added in the same `contract-change` as the
ledger, so G6 is decided together with G5.

### G7. Enforce `marketplace.json` as a shared path

**Context.** Amendment 2 rules `.claude-plugin/marketplace.json` shared, and
#406 added it to `workstreams.yaml`'s `shared_paths`. The required check
(`.github/workflows/shared-paths.yml`) and the AGENTS.md list do not include
it, so an unlabelled edit would pass CI. More broadly, the matcher covers
fewer paths than `workstreams.yaml` lists (`.agents/**`, `tsconfig*`, lint
and test configs, `.gitignore`, `.node-version`, `.python-version`,
`requirements-dev.txt`). That is code-review finding C5.

**Options:** (a) a small `contract-change` PR adding the path now;
(b) reconcile all three lists in one decision.

**Recommendation.** (a) before #398 dispatches; (b) as the R4 package.

## A — verifier (#396, PR #414)

### A1. Keep commit `f492762` (`abs()` → `copy_abs()`)

**Context.** `validate_numeric` used `abs()`, which rounds to the Decimal
context's 28 digits, so magnitudes differing in the 34th digit compared
equal. The input schema admits 34 digits. `copy_abs()` is exact.

- The package promised byte-identical behaviour for the existing mock
  verifier, so this is a literal departure.
- A review compared old and new code on 200,000 random values of 28 digits or
  fewer: zero differences in results or serialized traces.
- Differences appear only above 28 digits, or under a lowered context
  precision. In those cases the old code certified wrong values as
  `supported`.
- Two exotic forms change: `1E+1000000` used to raise `Overflow`, and a tiny
  exponent compared against 0 used to compare equal. Neither can reach the
  code through the MCP schema or the database.

**Recommendation.** Keep, and accept it explicitly as a correctness fix.

**Verify.** Search for callers that run under a non-default Decimal context.

### A2. `numeric_checks` when the hash mismatches

**Context.** The schema allows reporting the numeric comparisons even when
the evidence hash is invalid. The edge is then `irrelevant` and the claim
`unsupported`.

**Options:** (a) report the comparisons, as now; (b) `null`.

**Recommendation.** (a), matching the frozen verification schema: numeric
diagnostics are present when the request and evidence both carry numeric
tuples. The overall claim remains unsupported on a hash failure. Hidden or
missing evidence retains its uninformative null shape. The trusted verifier
source adapter enforces visibility and exact span-to-fact binding separately
from the public citation reader, which refuses corrupted text. Changing this
diagnostic contract needs a coordinated contract change.

### A3. Period labels for verification

**Context.** The rules compare a claim's period label (for example `FY2024`)
as a string. Those labels are stored only in `retrieval_items.period`, which
belongs to an index version, but a `verify_claim` context carries
`index_version_id = null`. `Fact.period` holds dates. Also undefined: which
fact applies when several cite one span.

**Options:**

- (a) Derive labels from `financial_facts` periods with a documented rule.
- (b) Require an index pin for `verify_claim`.
- (c) Change the claim contract to take dates.

**Recommendation.** Research before choosing. Any option except a pure
derivation rule is a `contract-change`.

**Research.** How `retrieval_items.period` is produced, whether it is a pure
function of fact periods and fiscal-year metadata, and how fiscal years that
don't end in December are labelled.

## B — review citation fix (#409, PR #415)

### B1. Widen #409's lane to the mock models

**Context.** #415 makes review re-validation credit a citation hash only when
the worker graded the edge `verified` or a reviewer supplied the evidence.
The defect was reproduced first: the tests-only commit `fadd90f` failed 14
tests, with 200 returned instead of 422.

Two existing required tests now fail, plus the non-required extraction
acceptance job:

- `evals/tests/test_extraction_cross_stack.py::test_harness_seeds_source_runs_worker_and_verifies_real_immutable_rows`
- `apps/api/tests/test_extraction_load_report.py::test_real_preflight_cli_writes_metadata_and_all_verified_operations`

Their mock models (`evals/harness/extraction_cross_stack.py::ScopedMock`,
`apps/api/benchmarks/extraction_load_fixture.py::BulkMock`) cite by span
membership only, so they had been passing through the defect. Those files
were outside the original #409 `allowed_paths`; AC6 now names both producers
and `evals/tests/test_extraction_cross_stack.py`. None is a shared path.

**Options:** (a) widen #409 to the two mock files and
`evals/tests/test_extraction_cross_stack.py`; (b) register a separate small
package.

**Recommendation.** Record AC6's bounded extension in the registry.

**Verify.** Use the actual span-ID-to-hash map for each seeded source; the
one-line cross-stack and 100-line bulk fixtures have different digests. Preserve
financial values, usage metadata, negative fixtures and the fail-closed guard.

### B2. Extraction roles must be able to assert span hashes

**Context.** No extraction role prompt gives the model a span's `text_hash`
(`workers/src/fel_workers/extraction/roles/` never references it). Every real
worker proposal is therefore membership-only. After #415, `accept` and
`merge` refuse them all, and promotion works only through `edit`. Nothing is
live-bound yet (#62), so nothing breaks in production today.

**Recommendation.** Register a follow-up package before any live model is
bound.

**Research.** How the roles' `read_span` tool returns spans, and the least
invasive way for a role to assert the hash it received.

### B3. Records already approved through C1

**Context.** Any approved record created before the fix may cite no verified
span.

**Recommendation.** Query `approved_extraction_versions` for records whose
evidence has no `verified` citation, outside fixtures, before deciding on
remediation.

## C — evidence read (#395, PRs #416 and #418)

### C1. Does the evidence context carry `parser_version`?

**Context.** The frozen interface
(`packages/retrieval/fel_retrieval/evidence/interfaces.py`) returns the
context unchanged. The `mcp-evidence-context` schema says `parser_version` is
null when a response spans several document versions. But the `get_citation`
and `resolve_company` output fixtures, and every other output fixture except
`read_filing`, carry `"edgar-html-v3"`. That includes `list_filings`, where
the schema text requires null. §6.3 of the design says the context carries the
selected document version.

**Options:**

- (a) Preserve the frozen interface: return the resolved context unchanged;
  put selected document/parser provenance on `Citation` and `DocumentHeader`.
- (b) Define a new enrichment contract across interface, schemas and fixtures.

**Recommendation.** (a). Reconcile the conflicting fixture/schema prose in
one explicit contract change before `read_filing` and full server acceptance.
Multi-document results must not pick one arbitrary document's parser version.
The bounded #416/#418 implementations need not invent that new contract.

**Research.** Which of the eight tools are single-document, and whether
`read_filing` can know a `document_version_id` at resolution time.

### C2. 4 MiB canonical-text cap

**Context.** #416 reports canonical text over 4 MiB as `integrity_error`,
with an operator error log. The existing reader allows 16 MiB.

**Options:** (a) raise the cap to 16 MiB; (b) keep 4 MiB with a distinct,
non-integrity error; (c) keep it as is.

**Recommendation.** (a) or (b). An honest oversized filing is not an
integrity failure.

**Research.** The size distribution of canonical text for 10-K and 10-Q
filings from large issuers. Check the committed fixtures and published SEC
filing sizes.

### C3. Add `hypothesis` for property tests

**Context.** #395 asks for property tests; `hypothesis` is not in the
lockfile, so the author used seeded `random` with fixed examples. Adding it
is a lockfile change that needs `contract-change` and an authorization
record.

**Recommendation.** Optional. The current tests killed every mutation the
reviewers tried except those already fixed.

### C4. Ratify five behaviour choices in #418

**Context.** The contract does not specify these, so the author chose:

1. `amends` is always null, because the corpus stores no
   filing-to-filing amendment link.
2. `resolve_company` truncates at 20 matches with no cursor, which the
   schema's `maxItems: 20` allows; exact matches rank first.
3. Listings are newest first by `(public_at DESC, id DESC)`.
4. An ambiguous company name returns `invalid_input` on `company`.
5. A cursor that is both mismatched and expired reports the mismatch.

**Recommendation.** Ratify all five and write them into the tool
descriptions. Item 1 becomes a documented limitation; a real link needs a
`contract-change`.

### C5. Inputs #397 must supply

**Context.** The evidence service takes the served-company list (an
`entity_id → Company` mapping; there is no entity table) and an HMAC cursor
key of at least 32 bytes, both through its constructor.

**Decide.** The source of truth for the cohort (`workstreams.yaml`, a
committed fixture, or a new table under `contract-change`), and how the
cursor key is provisioned and rotated. Give credential names only.

## D — SEC acceptance timestamps (#393, PR #417)

### D1. Timezone of EDGAR `acceptanceDateTime` (ADR-0034 owner input 4)

**Context.** The rule in `workers/src/fel_workers/ingestion/publication.py`
follows ADR-0034 decision 4 as amended:

- If EDGAR's filing date is later than the US Eastern date of acceptance,
  `public_at` is 06:00 America/New_York on the filing date (basis
  `next_session_open`).
- Otherwise `public_at` equals acceptance time (basis `acceptance`).

The code takes the offset in the `acceptanceDateTime` string at face value.
A reviewer recalled, without verifying, that the submissions JSON writes
Eastern wall-clock digits under a nominal `Z`. If so:

- Every `acceptance`-basis row is 4–5 hours early, which is a look-ahead
  leak. Example: `2024-03-06T16:14:09.000Z` filed 2024-03-06 gives
  `public_at` 11:14 EST.
- This is still stricter than today's midnight-UTC stamping, so it is not a
  regression.
- The backfill reports disagreeing stored values but never overwrites them,
  so a wrong assumption would persist.

The ADR says confirming it needs one request to sec.gov with an approved
`FEL_SEC_USER_AGENT`, and gates any hosted run on it.

**Options:**

- (a) Confirm the convention from a primary source, then keep or flip the
  one parsing function.
- (b) Keep unresolved publication metadata unknown and therefore invisible
  in strict mode until the interpretation is verified.

**Recommendation.** Verify (a) before any real backfill or hosted run; retain
(b) for unresolved data. Taking the later of two guesses does not establish
verified publication metadata and is not an accepted substitute for the ADR.

**Research.** This is the most valuable research item in this brief.
Establish EDGAR's `acceptanceDateTime` convention in
`https://data.sec.gov/submissions/CIK##########.json` from SEC documentation
or a reproducible sample. One way: compare one filing's `acceptanceDateTime`
with the acceptance time printed in that filing's EDGAR index page or SGML
header (`<ACCEPTANCE-DATETIME>`, which is Eastern). Respect SEC fair-access
rules (declared User-Agent, low request rate). Also confirm the 17:30 ET
cutoff and 06:00 ET opening against current EDGAR Filer Manual / 17 CFR
232.13 text.

### D2. What enqueues `sec_publication_backfill`

**Context.** #417 adds an idempotent, resumable backfill job that writes only
the five columns migration 0013 grants. Nothing enqueues it. Amendment 2
requires backfilling before exposing affected corpus pins.

**Options:** a one-off operator command, a migration-adjacent runbook step,
or an automatic enqueue on first deploy.

**Recommendation.** A documented operator step in the #400 hosted-pilot
runbook, run only after D1 is settled.

Also note: `workers/README.md` does not document the new job kind; that file
is outside #393's lane.

## R — backlog registration

### R1. Package for H8 parser defects

**Context.** Code-review finding H8 has no registered package. It covers:

- inline facts in headings attached to the wrong section;
- `typedMember` dimensions ignored;
- `ix:exclude` not stripped;
- sign double-negation on non-conformant text;
- a `scale` just above the Decimal context's `Emax` raising `decimal.Overflow`,
  which escapes the handler at `workers/src/fel_workers/ingestion/xbrl.py:248`
  and crashes the job instead of quarantining it.

It touches `workers/src/fel_workers/ingestion/**`, which #393 owns until it
merges.

**Recommendation.** Register after #393 merges. Make the `Overflow` crash its
first acceptance criterion.

### R2. Remaining review packages

**Context.** No issue exists yet for these packages from the 2026-11-13
review:

- R2: worker span-provenance defence in depth;
- R5: retrieval mutation RBAC, unpooled corpus connections on the owner role,
  extraction spend ceilings;
- R8, parts (c) and (d): source-span cutoff check, `FOR SHARE` on workspaces;
- R9: web telemetry buffering, single-document `as_of` fail-open, feedback
  idempotency key;
- R10: calculation-engine canonicalization;
- the Python parts of R11;
- the evals part of R12.

Shared-path packages (R4 CI gate, R6 RLS/grants migration, contract parity in
R11, advisories in R12) also need `contract-change`, and an ADR for
migrations and contracts.

**Recommendation.** Register R5 and R9 next; they have user-visible security
impact. Read the review's verification table: H6 is intended behaviour, and
the Medium and Low rows were never re-verified.

## Sequencing once decided

1. Record the applicable lead gates for the reconciled ledger (G5, G6).
2. #414 merged independently, as `2319c35` on 2026-11-15; #416 precedes #418. Record
   C1/C4 integration decisions without claiming unfinished #395 methods done.
3. Complete #409 AC6, get #415 green and merge when its own gates pass; it
   does not depend on #417. Hold #417 for all three reproduced correctness
   fixes, including transactional publication/repair serialization, and, by
   the owner's 2026-11-15 ruling, until #394 merges. D1 remains
   a separate real-backfill/hosted gate.
4. Release `workers/tests/**` only after its owner finishes. Dispatch #410,
   #411 and #412 in turn, plus the H8 package, subject to registration and
   ADR-0034's three-implementer limit across all current lanes.
5. Next MCP lanes: #394, then #397, #399 and part 3 of #395. #394 follows
   #409's release of `apps/api/tests/**` and merges before #417 (owner
   ruling, 2026-11-15). Because #412 waits for #393's `workers/tests/**`, the
   earlier text placing #394 after #412 can no longer hold; #412 follows #394
   (lead confirmation still pending on 2026-11-15).

## Research questions

1. **D1.** EDGAR `acceptanceDateTime` timezone convention, with a primary
   source or reproducible sample.
2. **D1.** Current text of 17 CFR 232.13 and the EDGAR Filer Manual on
   filing-date assignment, the 17:30 and 22:00 ET cutoffs, and dissemination
   start.
3. **C2.** Typical and maximum canonical-text sizes for 10-K and 10-Q filings.
4. **A3.** A deterministic, documented mapping from fact period dates to
   fiscal labels such as `FY2024` and `Q3 FY2025`.
5. **G2.** Advisories and provenance for `mcp` 2.3.0 and `httpx2` 2.16.0.
6. **B2.** A pattern for model-facing tools to assert a content hash they
   were given, without the model computing it.
7. **C1.** Precedent in MCP tool design for a context field that is null for
   multi-resource responses.

## Reading list

All paths are on `main` unless noted.

- `AGENTS.md`, `CLAUDE.md`, `.specify/memory/constitution.md`
- `docs/handoff/README.md` (source-of-truth order, ledger-prose rules),
  `docs/handoff/workstreams.yaml`, `docs/handoff/STATUS.md`
- `docs/decisions/ADR-0034-public-read-only-evidence-surface.md` (decisions
  4 and 8, Amendments 1–2, owner inputs)
- `docs/research/mcp-evidence-server-spec.md` §6–§7 (frozen design)
- `specs/006-mcp-evidence-server/{spec,plan,tasks}.md`
- `docs/research/2026-11-13-repository-code-review.md` (verification-status
  table)
- `packages/retrieval/fel_retrieval/evidence/interfaces.py`
- `packages/contracts/schemas/mcp-*.schema.json` and
  `packages/contracts/fixtures/`
- `db/migrations/0012_*.sql`, `0013_*.sql` and `db/migrations/tests/`
- `.github/required-checks.md`, `.github/workflows/ci.yml`,
  `.github/workflows/shared-paths.yml`
- Issues #393–#400 and #409–#412; PRs #413–#418
- [`codex-review-2026-11-14.md`](codex-review-2026-11-14.md) (this directory)

## Report format

For each decision ID you address:

1. **Finding:** what you verified or learned, with sources (`file:line`, PR
   or issue number, URL, or command and output).
2. **Assessment:** agree or disagree with the recommendation, and why.
3. **Risk** if the lead chooses each option.
4. **Confidence:** high, medium or low, and what would raise it.

Label every claim **verified** (you checked a primary source or ran it),
**traced** (read the code) or **unverified**.

## What this brief does not establish

- The recommendations are the coordinating agent's, informed by Claude-agent
  reviews. Same-vendor review is not independent evidence for G4.
- The November 14 independent review ran isolated PostgreSQL reproductions
  for #415/#417, as recorded in STATUS.md. Other local database skips remain
  explicit; neither that review nor repaired mock runs prove hosted readiness.
- The EDGAR timezone claim in D1 is an unverified recollection.
- Nothing here authorizes a merge, a ledger change, a credential, a hosted
  run, a paid call or a request to sec.gov.

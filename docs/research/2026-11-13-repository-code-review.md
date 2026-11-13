# Repository code review (2026-11-13)

<details>
<summary>Relevant source files</summary>

- [apps/api/app/extraction/validation.py](../../apps/api/app/extraction/validation.py) — review-time citation revalidation
- [apps/api/app/retrieval.py](../../apps/api/app/retrieval.py) — retrieval routes, lane connections, SSE
- [apps/api/app/corpus.py](../../apps/api/app/corpus.py) — corpus and source-span reads
- [db/migrations/0001_platform_core.sql](../../db/migrations/0001_platform_core.sql) — `fel_app` grants and RLS
- [workers/src/fel_workers/extraction/persist_reads.py](../../workers/src/fel_workers/extraction/persist_reads.py) — durable span pin loads
- [workers/src/fel_workers/extraction/normalize/numeric.py](../../workers/src/fel_workers/extraction/normalize/numeric.py) — numeric parsing
- [workers/src/fel_workers/ingestion/parser.py](../../workers/src/fel_workers/ingestion/parser.py) — iXBRL unit and section parsing
- [apps/web/src/proxy.ts](../../apps/web/src/proxy.ts) — deployment-mode route guard
- [.github/workflows/shared-paths.yml](../../.github/workflows/shared-paths.yml) — contract-change gate
- [.specify/memory/constitution.md](../../.specify/memory/constitution.md) — Principles I–IV used as review criteria

</details>

Source references verified against commit `2f7f066`.

Read-only adversarial review of `main` for an external agent team. This note
**authorizes no code change** and does not edit Spec Kit task checkboxes,
`workstreams.yaml`, or ADR status. Every finding below was re-checked against
the cited files at `2f7f066`. Prefer the source of truth order in
[`docs/handoff/README.md`](../handoff/README.md#source-of-truth) if GitHub or
handoff state has moved since this snapshot.

## Contents

- [How to use this note](#how-to-use-this-note)
- [Suggested fix packages](#suggested-fix-packages)
- [Critical findings](#critical-findings)
- [High findings](#high-findings)
- [Medium findings](#medium-findings)
- [Low findings](#low-findings)
- [Missing and weak tests](#missing-and-weak-tests)
- [Related pages](#related-pages)

## How to use this note

1. Confirm `main` still contains `2f7f066` (or re-verify cited lines after rebase).
2. Pick **one** suggested package below. Ask the integration lead for an issue,
   branch name, and `allowed_paths` before editing; do not invent ledger rows.
3. Start with a failing test that reproduces the finding, then the smallest fix.
4. Shared paths (`packages/contracts/**`, `db/migrations/**`, `.github/**`,
   `docs/decisions/**`, handoff ledgers) need the `contract-change` label and
   lead review. Do not weaken Recall@10, review budgets, or citation blockers
   to make a gate pass.
5. Never put credential values in issues, commits, fixtures, or PR text.

Severity here means: **Critical** = integrity / tenancy / governance bypass
with a concrete exploit path; **High** = serious security, cost, temporal, or
data-fidelity defect; **Medium** = real bug or bypass with narrower blast
radius; **Low** = hygiene or latent footgun.

## Suggested fix packages

These are **proposal slices only**. Paths are hints for lead registration, not
permission to edit.

| ID | Focus | Likely paths | Depends on |
| --- | --- | --- | --- |
| R1 | Citation blockers survive `accept`/`merge` | `apps/api/app/extraction/**`, `apps/api/tests/extraction/**` | none |
| R2 | Durable extraction span provenance (`as_of`, entity, corpus, manifest) | `workers/src/fel_workers/extraction/**`, `workers/tests/extraction/**` | none |
| R3 | Numeric sign/currency parsing + XBRL divide/sign/`typedMember`/`ix:exclude` | `workers/src/fel_workers/extraction/normalize/**`, `workers/src/fel_workers/ingestion/**` | none |
| R4 | Shared-path CI hardening (trusted scripts, merge-base `--all` / merge-tree, lockfile coverage) | `.github/workflows/shared-paths.yml`, `.github/scripts/**` | `contract-change` |
| R5 | Retrieval RBAC, lane connection role/pool, cost metering on extraction | `apps/api/app/retrieval*.py`, `apps/api/app/extraction/runs.py`, `apps/api/tests/**` | none |
| R6 | Platform RLS grants / FORCE RLS / platform-job policy | `db/migrations/**` (new migration only), `db/migrations/tests/**` | `contract-change` + ADR if policy changes |
| R7 | Error redaction on run failure paths | `workers/src/fel_workers/extraction/workflow.py`, `workers/src/fel_workers/redact.py`, `apps/api/app/retrieval.py` | none |
| R8 | SEC `published_at` / restates / corpus span quarantine | `workers/src/fel_workers/ingestion/**`, `workers/src/fel_workers/consumer.py`, `apps/api/app/corpus.py` | none |
| R9 | Web public-mode telemetry guard, `as_of` fail-closed, workspace binding, feedback idempotency | `apps/web/src/**` | none |
| R10 | Calculation-engine `MappingProxyType` canonicalization + exponent bounds | `packages/calculation-engine/**` | none |
| R11 | Retrieval claim `scale` enum, embeddings batching, OpenAI usage accounting | `packages/retrieval/**`, `packages/providers/**`, possibly `packages/contracts/**` | contracts only with `contract-change` |
| R12 | Advisories lockfile scan, retrieval-gate `entity_id`, path_guard deny-mode | `.github/workflows/advisories.yml`, `evals/harness/retrieval_gate.py`, `scripts/agent/path_guard.py` | R4 for workflow edits |

Cap concurrent implementation packages at four. Prefer PRs under roughly 600
changed lines.

## Critical findings

### C1. Review `accept`/`merge` clears unverified-citation blockers

**Package:** R1

Worker validation blocks membership-only citations:

```55:56:workers/src/fel_workers/extraction/validate/citations.py
    if not verified:
        errors.append("no verified citation: no cited span asserts a matching text_hash")
```

Review revalidation then:

1. Reads evidence without `citation_status` (`apps/api/app/extraction/review.py`
   lines 82–90).
2. Injects corpus `text_hash` into every edge and only checks payload assertions
   that already include a hash (`apps/api/app/extraction/validation.py`
   lines 85–101).
3. Carries forward only `dimensions_non_string` and `sign ...` blockers
   (lines 126–134), dropping `"no verified citation: ..."`.

**Impact:** `POST /v1/extractions/review` with `action=accept` or `merge` can
promote a proposal that never asserted a matching `text_hash` into
`approved_extraction_versions`, contradicting OpenAPI review rules and
Constitution Principle I.

**Finish line:** API test where a proposal with string-form evidence /
`citation_status=partial` and the worker blocker is selected for `accept`;
expect `422 VALIDATION_ERROR` (or equivalent) and no approved record. Cover
`merge` the same way.

### C2. Durable extraction span binding ignores publication time, entity, corpus, and manifest

**Package:** R2

```77:91:workers/src/fel_workers/extraction/persist_reads.py
    rows = conn.execute(
        """
            SELECT id, document_version_id, text_hash
              FROM source_spans
             WHERE id = ANY(%s::uuid[])
            """,
        (wanted,),
    ).fetchall()
```

`_bind_evidence_to_spans` only checks span id, `document_version_id`, and text
hash (`handler.py` ~262–308). `_stage_assemble_evidence` only compares
payload `published_at` when present (`assemble_evidence.py` line 36). Missing:
join to `documents.published_at`, `documents.entity_id`,
`document_versions.status='parsed'`, `corpus_version_documents`, and
`input_manifest.source_span_ids`. `workers/src/fel_workers/extraction/assemble.py`
(manifest membership) has zero callers.

**Impact:** A durable job can cite a real span from another entity, a future
filing, a quarantined version, or outside the run manifest by omitting or
backdating `published_at`. Naive vs aware datetime comparison can also raise
unhandled `TypeError`.

**Finish line:** Durable Postgres tests that omit `published_at`, supply a
backdated payload timestamp for a future document, cite another `entity_id`,
cite outside the manifest, and cite a non-`parsed` version — each must fail
closed before proposals persist.

### C3. Numeric parser inverts negatives for non-`$` currencies and Unicode minus

**Package:** R3

`parse_numeric` strips only `$` and `%`, then `_NUM_RE.search` can start after
`€`, `£`, or `US`. Leftover `(` / `-` / `US` are not rejected unless they
contain digits (`numeric.py` lines 60–104). ASCII `[-+]` does not match
`U+2212`.

Verified shapes that become positive `100` at scale 6: `(€100 million)`,
`-€100 million`, `(US$100 million)`, `−100 million`.

**Impact:** Losses and outflows normalize to `sign=positive`.

**Finish line:** Parametrized normalizer tests for the shapes above (and GBP),
asserting negative sign / value. Keep existing `$` / `%` cases green.

### C4. iXBRL `<xbrli:divide>` units collapse to the last measure

**Package:** R3

```428:431:workers/src/fel_workers/ingestion/parser.py
        elif tag == "xbrli:measure":
            if self._unit_id and captured:
                self.units[self._unit_id] = captured
```

Per-share units set `iso4217:USD` then overwrite with `xbrli:shares`.

**Impact:** EPS / DPS facts store `unit='shares'` instead of a per-share
currency unit.

**Finish line:** Parser fixture with `xbrli:divide` asserting numerator/denominator
composition (or mapped `USD/shares`); golden stress HTML includes at least one
per-share unit.

### C5. Shared-path gate can run untrusted scripts and miss criss-cross reverts

**Package:** R4 (`contract-change`)

`.github/workflows/shared-paths.yml` checks out the PR tree and executes
`.github/scripts/list-changed-paths.sh` from that tree (lines 42–45, 93). An
empty stdout path hits `exit 0` (lines 95–97). Diff uses a single
`git merge-base` (line 87), which is insufficient when `$BASE_SHA` and
`$HEAD_SHA` share multiple best ancestors after merge-heavy histories.
Lockfiles / toolchain / `.gitleaksignore` / `scripts/runtime/build.*` are also
outside the matcher while appearing in handoff `shared_paths` guidance.

**Impact:** Unlabeled shared-path edits or silent shared-file reverts can pass
the required check.

**Finish line:** Run listing scripts from `$BASE_SHA` (or otherwise pin trust);
fail or union-diff across `git merge-base --all` / `merge-tree`; add regression
fixtures for script self-edit and multi-merge-base revert; align matcher with
the lead’s shared-path table.

## High findings

### H1. Retrieval mutations ignore RBAC; extraction runs skip spend ceilings

**Package:** R5

`create_query`, `create_query_rerun`, and `create_retrieval_feedback`
(`apps/api/app/retrieval.py`) never check `ctx.role`. Workspace and extraction
mutations do. RLS on retrieval tables only requires matching `org_id`.
Extraction run create/rerun check roles but omit `rate_limit` /
`enforce_ceilings` / `record_usage`.

**Impact:** A `viewer` can burn org query budget and write feedback; callers at
cost limits can still enqueue extraction.

### H2. Lane reads use owner DB role and unpooled connections

**Package:** R5

`_corpus_read_connection` (`retrieval.py` lines 231–243) opens
`psycopg.connect(FEL_DATABASE_URL)` without `SET ROLE fel_app` or the pool,
while the tenant connection stays checked out across lanes and generation.

**Impact:** Least-privilege bypass on corpus SQL; connection / pool exhaustion
under burst.

### H3. Over-broad `fel_app` grants and non-FORCE RLS

**Package:** R6

`0001_platform_core.sql` grants `INSERT,UPDATE` on `organizations` /
`memberships` and `UPDATE,DELETE` on `idempotency_keys`. `jobs_tenant` still
allows `org_id IS NULL` for `SELECT`/`INSERT` after `0007` restricted only
`UPDATE`. No `FORCE ROW LEVEL SECURITY`; `audit_events` / `usage_events` lack
append-only triggers.

**Impact:** Privilege escalation and platform-job access at the SQL layer if a
session is `fel_app` with attacker-controlled claims; owner connections that
forget `SET ROLE` skip RLS.

### H4. Unredacted exception text on terminal run failures

**Package:** R7

`workflow.py` sets `state.error = {..., "message": str(exc)}` for cancel /
typed failure / internal paths (lines 121, 141, 163) and persists it without
`redact_error_text`. Retrieval `_failure_envelope` stores `str(exc)` similarly.
`redact.py` misses DSN URLs and non-Bearer/Basic schemes; extraction events
miss several token key names and list-string values.

**Impact:** Secrets and filing text can land in tenant-readable run/error
tables.

### H5. Temporal / quarantine leaks in ingestion and corpus API

**Package:** R8

- SEC fetch stamps `published_at` at `00:00:00Z` from `filingDate`
  (`consumer.py` lines 168–173), creating intra-day look-ahead versus
  `acceptanceDateTime`.
- Reverse-chronological discovery plus `published_at <` breaks `restates`.
- `GET /v1/source-spans/{id}` returns spans without `parsed` / cutoff checks
  (`corpus.py` lines 151–174). Document list/get omit default “now” cutoff when
  `as_of` is absent.
- Retrieval create lacks `FOR SHARE` on workspaces; reruns reuse plan
  `effective_as_of` after workspace cutoff tightening.

### H6. `reader-smoke` allows mock auth against remote DBs for all routes

**Package:** R5 (or dedicated auth/deployment package)

`deployment.py` permits `reader-smoke` + `auth_mode=mock` without the
loopback DB restriction used by `synthetic-http`, while mutating routes stay
mounted.

**Impact:** Forged `Bearer mock.*` against a reachable smoke API mutates remote
tenant data.

### H7. Heartbeat DB failure fails open; gzip bomb before size check

**Package:** R2 / worker HTTP package

Heartbeat thread exits on DB errors without setting `lease_lost`
(`consumer.py` lines 123–134), leaving a zombie window after reclaim.
`http.py` `_read_bounded` uses `iter_bytes()` so zlib can expand a chunk before
the byte cap runs.

### H8. Parser / XBRL fidelity defects

**Package:** R3

Inline facts inside headings attach to the previous section while offsets fall
in the next (`parser.py` heading/`ix:nonfraction` ordering) → reader
`span_outside_section`. `company_facts` emits overlapping root+child sections.
`typedMember` ignored; `ix:exclude` not stripped; `sign="-"` plus parentheses
double-negates (`xbrl.py` lines 225–239); unbounded `scale` can explode memory.

### H9. Calculation engine cannot canonicalize evaluation results

**Package:** R10

`canonical.py` only treats `dict`, not `MappingProxyType`. `evaluate()` wraps
`results` / `iteration_runs` in `MappingProxyType` (`engine.py` lines 497–499).
`require_decimal` does not enforce `±_MAX_EXPONENT`; non-iterative products can
yield unhashable exponents; `CALC_CONTEXT` is a mutable global.

### H10. Retrieval/provider/contract seams

**Package:** R11

- Schema-valid `numeric.scale` outside `{0,3,6,9}` raises raw `ValueError` past
  `GenerationContractError`, dropping usage (`generation.py`).
- `OpenAIStructuredProvider._usage` requires `input_tokens_details`; missing
  field zeros usage on a billed 200; `_json` uses binary floats; cost scale can
  exceed `numeric(12,6)` / trace schema.
- `embed_drafts` is unbatched and allows empty spans.
- `build_comparability_key` delimiter injection and `.strip()` on non-strings.
- Generated guidance TypeScript makes `shape` optional; OpenAPI vs JSON Schema
  `JobEnvelope` disagree on `payload`/`error`.

### H11. Web trust-boundary defects

**Package:** R9

- `/api/telemetry` is outside `proxy.ts` matcher, buffers unbounded JSON, weak
  CSRF, incomplete redaction (`telemetry-validation.ts` JSON/`+`/`/` gaps).
- `Date.parse` fail-open on bad `as_of` in HTTP/fixture document reads.
- Extraction/Observatory proxies use org bearer without workspace binding on
  several run/review/rerun routes.
- Feedback idempotency key omits `reason`.
- Same-`documentId` version / span navigation does not reset reader state;
  stale `activeId` makes OutlineNav all `tabIndex=-1`.

### H12. CI / evals / agent tooling

**Package:** R12 (+ R4)

- `advisories.yml` audits unpinned `requirements*.txt`, not lockfiles; JS
  failure skips Python audit; allowlist `reviewBy: 2026-12-01` is imminent.
- `retrieval_gate.py` builds `LaneQuery` without `entity_id` (cross-issuer
  search) and can exit 0 when answerable questions are excluded but a negative
  question remains.
- `reader-prod-smoke.yml` treats wait-timer as sufficient protection; SSH key
  cleanup can miss files if env export never runs.
- `path_guard.py` allows out-of-repo writes; hook fails open; prefix matching
  is case-sensitive.
- `corpus_qa_render.py` `_blockquote` splits only on `\n`, enabling `\r`
  Markdown breakout.

## Medium findings

| ID | Summary | Primary locus |
| --- | --- | --- |
| M1 | `merge` allows empty/mismatched `selected_winner_ids`; can brick later conflict reviews | `apps/api/app/extraction/conflicts.py`, `review.py` |
| M2 | Prompt `_sanitize` is single-pass and case-sensitive | `workers/.../roles/base.py` lines 36–38 |
| M3 | Premature output-token budget reserve; weak `verify_citations` input hash; ontology drop on resume; false `revenue_driver`/`guidance` conflicts | `workers/.../extraction/**` |
| M4 | Idempotency TOCTOU on workspaces/feedback; JWKS all-or-nothing; mock non-UUID 500s; `RateLimiter` NaN; reader cursor drops `corpus_version_id`; retrieval SSE closes on live runs | `apps/api/app/**` |
| M5 | `migrate.py` DDL before lock / in `--check`; ignores deleted migrations; PermanentFailure leaks heartbeat; ingestion ignores cancel | `scripts/db/migrate.py`, `workers/.../consumer.py` |
| M6 | Citation quote not checked in `verify_claims`; empty unit/period certify match; stale `fused_rank`; `build_items` ignores `kinds`; index build error path on aborted txn | `packages/retrieval/**` |
| M7 | Observatory redirect injection / missing `too_large` slug; upstream `redirect:follow`; Origin/Host port fragility; SSE `\r\r` / EOF flush; ReviewQueue stale lock | `apps/web/src/**` |
| M8 | `PERCENT` unusable in model graph; currency quantum missing at build for some ISO codes | `packages/calculation-engine/**` |

## Low findings

- DB URLs on process argv in Railway/CI migrate invocations; backup smoke
  `PGDATABASE` interpolation and suppressed role restore errors.
- Worker JSON logs interpolate unescaped messages; local `signed_url` exposes
  host paths with unkeyed hashes.
- Isotonic `predict()` returns `0` on `insufficient_data`; score regex rejects
  trailing-zero decimals.
- `/desk` missing `#main-content`; no CSP / Referrer-Policy; several TS switches
  omit `never` exhaustiveness.

## Missing and weak tests

1. `evals/datasets/sec-fixtures/tests` not in `pyproject.toml` `testpaths`.
2. Several DB suites still `pytest.skip` despite CI `FEL_REQUIRE_DB=1`;
   `test_migrate.py` can mask apply failures as a pgvector skip.
3. No `0001`/`0002` SQL harnesses; durable extraction tests often skip
   `fel_worker` role; extraction API client bypasses `app.main` middleware.
4. No API test for partial-citation `accept`; no viewer RBAC tests on retrieval
   mutations; no corpus-pinned sibling cursor + `corpus_version_id` test.
5. No worker tests for divide units, `typedMember`, `ix:exclude`, heading
   facts, reverse-chron restates, or non-`$` / `U+2212` numerics.
6. No `canonical_json(EvaluationResult)` test; no illegal-but-schema-valid
   claim `scale`; no OpenAPI↔JSON Schema parity suite.
7. Web deployment guard omits telemetry; Observatory SSE tests miss `\r\r` and
   truncated EOF; EvidenceReader tests do not exercise same-document version
   transitions.

## Related pages

- [Handoff README](../handoff/README.md) — resume and dispatch rules
- [STATUS.md](../handoff/STATUS.md) — live blockers and dependency order
- [Constitution](../../.specify/memory/constitution.md) — Principles I–IV
- [Quality gates](../development/quality-gates.md)
- [Testing guide](../development/testing.md)
- [Required checks](../../.github/required-checks.md)
- [Financial evidence skills review](financial-evidence-skills-review.md) —
  prior external review that produced HTTP hardening

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
`workstreams.yaml`, or ADR status. Prefer the source of truth order in
[`docs/handoff/README.md`](../handoff/README.md#source-of-truth) if GitHub or
handoff state has moved since this snapshot.

The Critical and High findings were independently re-verified against
`2f7f066` after the first draft; the outcome is in
[Verification status](#verification-status), and each finding carries a
**Verified** line where the first draft was corrected. The Medium and Low
tables and the missing-tests list were **not** re-verified: treat each row
there as a lead to reproduce, not as an established defect.

## Contents

- [How to use this note](#how-to-use-this-note)
- [Verification status](#verification-status)
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

## Verification status

Re-verification read the cited code at `2f7f066` and looked for a guard
elsewhere before accepting an impact. "Reproduced" means the behaviour was
executed, not only read. The **Severity** column is the verified one and
governs where it differs from the section a finding sits in; IDs are kept
stable so existing references still resolve.

| ID | Verdict | Severity | Correction to the first draft |
| --- | --- | --- | --- |
| C1 | Confirmed (traced) | Critical | none |
| C2 | Overstated | High | The API already enforces entity, cutoff, `parsed` and corpus membership before it enqueues; the worker gap is missing defence in depth |
| C3 | Confirmed (reproduced) | Critical | none |
| C4 | Confirmed (traced) | Critical | none |
| C5 | Partly | High | Pinning the scripts alone fixes nothing; the named matcher gaps were wrong |
| H1 | Confirmed | High | A per-run cost cap exists; the org ceiling and metering are what is missing |
| H2 | Confirmed | High | Corpus tables have no RLS: excess privilege and pool pressure, not a tenant leak |
| H3 | Confirmed | High | App roles already cannot `UPDATE`/`DELETE` the audit and usage tables |
| H4 | Confirmed (reproduced) | High | Retrieval failure text is returned by the API; extraction failure text is only at rest |
| H5 | Partly | High | (a), (b) confirmed; (c) small impact; the rerun half of (d) is by design |
| H6 | Intended behaviour | Design risk | The frozen deployment-guard contract exempts `reader-smoke` from the loopback rule |
| H7 | Partly | Medium / High | Heartbeat fail-open is documented and fenced; the gzip overshoot is real but bounded |
| H8 | Mostly confirmed | High | `scale` does not exhaust memory; it raises an uncaught `decimal.Overflow` |
| H9 | Confirmed (reproduced) | Medium | Nothing canonicalizes an `EvaluationResult` today |
| H10 | Confirmed | High | Three sub-claims corrected, including one wrong package |
| H11 | Confirmed | High | Telemetry is off by default; only single-document reads fail open |
| H12 | Partly | Medium | `path_guard` fail-open is documented; its case bypass is mostly closed |

Verified priority for fix work: C1, C3, C4 and the retrieval half of H4.

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

**Impact:** A durable job whose payload did not come from the API can cite a
real span from another entity, a future filing, or outside the run manifest by
omitting or backdating `published_at`.

**Verified:** Overstated; High, not Critical. The API is the only producer of
these jobs and `verify_spans` already requires `d.entity_id`,
`d.published_at <= cutoff`, `v.status = 'parsed'` and
`corpus_version_documents` membership for every selected span
(`apps/api/app/extraction/evidence.py` lines 59–61, called from
`runs.py` line 125) before the job row is written. Exploiting the worker gap
therefore needs direct write access to `jobs`. The worker re-check is still
worth adding as a second layer, because the worker is what persists the
citation. The naive-versus-aware `TypeError` was not reproduced.

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
The matcher also covers fewer paths than `docs/handoff/workstreams.yaml`
`shared_paths` lists.

**Impact:** Unlabeled shared-path edits or silent shared-file reverts can pass
the required check.

**Verified:** Partly; High, not Critical. The single merge-base and the
PR-tree script execution are both real. Two corrections:

- Running the listing scripts from `$BASE_SHA` does not close the trust gap on
  its own. The workflow triggers on `pull_request`, so the workflow file is
  itself read from the PR: a PR that can edit the scripts can edit
  `shared-paths.yml`. A real fix needs a trigger that takes the workflow from
  the base branch, with the PR tree treated as data only. `.github/CODEOWNERS`
  also routes every path to the integration lead, which bounds the impact
  where review is enforced.
- `.gitleaksignore` and `scripts/runtime/build.*` are on no shared-path list.
  The actual drift is that `workstreams.yaml` `shared_paths` names
  `.agents/**`, `tsconfig.json`, `tsconfig.base.json`, `vitest.config.ts`,
  `eslint.config.mjs`, `.prettierrc.json`, `.prettierignore`, `.editorconfig`,
  `.gitignore`, `.node-version`, `.python-version` and `requirements-dev.txt`,
  while `AGENTS.md` "Shared paths" and the workflow matcher (which tracks
  `AGENTS.md`) do not. Which list governs is an integration-lead decision.

**Finish line:** Take the workflow and its scripts from the base branch; fail
or union-diff across `git merge-base --all` / `merge-tree`; add regression
fixtures for script self-edit and multi-merge-base revert; reconcile the
matcher, `AGENTS.md` and `workstreams.yaml` to one shared-path list.

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

**Verified:** Confirmed. Each extraction run still carries a per-run cap
(`max_cost_usd` at most 2.00, `workers/src/fel_workers/extraction/budget.py`);
what is missing is the org-level ceiling, the rate limit and usage metering.

### H2. Lane reads use owner DB role and unpooled connections

**Package:** R5

`_corpus_read_connection` (`retrieval.py` lines 231–243) opens
`psycopg.connect(FEL_DATABASE_URL)` without `SET ROLE fel_app` or the pool,
while the tenant connection stays checked out across lanes and generation.

**Impact:** Least-privilege bypass on corpus SQL; connection / pool exhaustion
under burst.

**Verified:** Confirmed. The corpus tables carry no RLS, so this is excess
privilege on the login role plus one unpooled connection per lane; it is not a
tenant-data leak path.

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

**Verified:** Confirmed; migrations `0002`–`0011` correct none of it. Two
limits: `fel_app` holds only `SELECT, INSERT` on `audit_events` and
`usage_events`, so the missing append-only triggers matter only against the
owner role; and `UPDATE` on `organizations` / `memberships` is still confined
to the caller's own org by RLS.

### H4. Unredacted exception text on terminal run failures

**Package:** R7

`workflow.py` sets `state.error = {..., "message": str(exc)}` for cancel /
typed failure / internal paths (lines 121, 141, 163) and persists it without
`redact_error_text`. Retrieval `_failure_envelope` stores `str(exc)` similarly.
`redact.py` misses DSN URLs and non-Bearer/Basic schemes; extraction events
miss several token key names and list-string values.

**Impact:** Secrets and filing text can land in tenant-readable run/error
tables.

**Verified:** Confirmed, and the two paths differ. Retrieval is the worse one:
the `run_failed` event payload holds `str(exc)` and the event-history and
trace reads (`apps/api/app/retrieval_reads.py`) return it verbatim to any org
member. Extraction error text is stored raw but never returned: the API
replaces it with a fixed message (`serializers.safe_error`). Reproduced
against `redact.py`: `postgres://user:pass@host/db` passes through unchanged,
and `Authorization: Token abc123` keeps the token.

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

**Verified:** The first two bullets are confirmed; both filings of a same-day
amendment are also stamped at midnight, so the strict `<` excludes the
original. Third bullet: the code facts are right but the missing `parsed`
check is unreachable (versions are only ever inserted as `parsed`; quarantine
goes to `ingestion_quarantine`), and a span body holds offsets and a hash, not
text, so the impact is small. Fourth bullet: the missing `FOR SHARE` is a
narrow race; a rerun reusing the original plan's cutoff is by design
(ADR-0006: an unchanged rerun is pinned to the original immutable plan) and
is a policy question, not a defect.

### H6. `reader-smoke` allows mock auth against remote DBs for all routes

**Package:** none until the integration lead decides; a change here amends a
frozen contract

`deployment.py` permits `reader-smoke` + `auth_mode=mock` without the
loopback DB restriction used by `synthetic-http`, while mutating routes stay
mounted.

**Impact:** Forged `Bearer mock.*` against a reachable smoke API mutates remote
tenant data.

**Verified:** Intended behaviour, recorded here as a design risk.
[`deployment-guard-contract.md`](deployment-guard-contract.md) states that
`reader-smoke` has no extra loopback requirement for the separately authorized
hosted reader target. A forged token must also name an `(org_id, sub)` pair
that has a real membership row, and the target must be the marker-proven smoke
target.

### H7. Heartbeat DB failure fails open; gzip bomb before size check

**Package:** R2 / worker HTTP package

Heartbeat thread exits on DB errors without setting `lease_lost`
(`consumer.py` lines 123–134), leaving a zombie window after reclaim.
`http.py` `_read_bounded` uses `iter_bytes()` so zlib can expand a chunk before
the byte cap runs.

**Verified:** Partly. The heartbeat behaviour is deliberate (its docstring:
a connection failure is not proof of loss) and the terminal write is fenced,
so the consequence is a second worker running the same job concurrently —
duplicate work, not a corrupted result. The gzip overshoot is confirmed but
bounded: one raw read is inflated before the cap is checked, roughly 1000× a
single chunk, not unbounded. The `Content-Length` pre-check is skipped when
`content-encoding` is present.

### H8. Parser / XBRL fidelity defects

**Package:** R3

Inline facts inside headings attach to the previous section while offsets fall
in the next (`parser.py` heading/`ix:nonfraction` ordering) → reader
`span_outside_section`. `company_facts` emits overlapping root+child sections.
`typedMember` ignored; `ix:exclude` not stripped; `sign="-"` plus parentheses
double-negates (`xbrl.py` lines 225–239); unbounded `scale` crashes the job.

**Verified:** Mostly confirmed. The heading, `typedMember` and `ix:exclude`
defects are as stated. The `company_facts` overlap is real but no consumer was
found that breaks on it. The double negation only fires on non-conformant
text, since conformant iXBRL puts the parentheses outside the element. The
first draft's memory claim for `scale` was wrong: `Decimal` bounds the
exponent. The actual defect is that a `scale` just above the context's `Emax`
raises `decimal.Overflow`, which is not an `InvalidOperation`, so it escapes
the handler at `xbrl.py` line 248 and fails the job instead of quarantining
the fact.

### H9. Calculation engine cannot canonicalize evaluation results

**Package:** R10

`canonical.py` only treats `dict`, not `MappingProxyType`. `evaluate()` wraps
`results` / `iteration_runs` in `MappingProxyType` (`engine.py` lines 497–499).
`require_decimal` does not enforce `±_MAX_EXPONENT`; non-iterative products can
yield unhashable exponents; `CALC_CONTEXT` is a mutable global.

**Verified:** Confirmed and reproduced: `canonical_json(evaluate(...))` raises
`CanonicalizationError: cannot canonicalize mappingproxy`. Nothing in the
repository canonicalizes an `EvaluationResult` today (`evaluation_id` hashes a
plain dict), so this is an inconsistency in the exported API with no live
failure; Medium. `canonical.py` does enforce the exponent bound at hash time.

### H10. Retrieval/provider/contract seams

**Package:** R11

- Schema-valid `numeric.scale` outside `{0,3,6,9}` raises raw `ValueError` past
  `GenerationContractError`, dropping usage (`generation.py`).
- `OpenAIStructuredProvider._usage` requires `input_tokens_details`; a missing
  field rejects the whole billed 200 as `invalid_response` and drops its
  usage; `_json` uses binary floats; cost scale can exceed `numeric(12,6)` /
  trace schema.
- `embed_drafts` is unbatched and does not reject empty spans itself.
- `build_comparability_key` (`packages/ontology/fel_ontology/comparability.py`)
  delimiter injection.
- Generated guidance TypeScript makes `shape` optional; OpenAPI vs JSON Schema
  `JobEnvelope` disagree on `payload`/`error`.

**Verified:** The `scale`, `_usage`, `embed_drafts` and comparability-key
bullets were checked; the last bullet and the `_json` / cost-scale clauses
were not. Corrections are folded into the bullets above. Two mitigations:
`OpenAIEmbeddingProvider.embed` fails closed on more than 64 texts or an empty
text, so an oversized index build errors rather than embedding bad data; and
the only caller of `build_comparability_key` passes `str(v)`, so the
`.strip()`-on-non-string claim of the first draft does not hold. The
comparability key lives in `packages/ontology/**`, outside R11's likely paths.

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

**Verified:** The telemetry matcher and buffering, the `Date.parse` fail-open
and the feedback idempotency key were checked and confirmed; the CSRF,
redaction, workspace-binding and reader-state bullets were not. Limits:
`/api/telemetry` returns 404 unless `FEL_WEB_TELEMETRY=1`, and `proxy.ts` only
asserts deployment mode, so the matcher would add no authentication. The
`as_of` fail-open is confined to `getDocument` and the fixture `getReader`;
the list and sibling filters fail closed.

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

**Verified:** The `advisories.yml`, allowlist date, `retrieval_gate.py`
`entity_id` and `path_guard.py` bullets were checked; the gate's exit-0 case,
`reader-prod-smoke.yml` and `corpus_qa_render.py` were not. `path_guard.py`
documents itself as not a security boundary, so its out-of-repo and fail-open
behaviour is by design, and its `canonical_case()` step rewrites existing
path components to their on-disk spelling, which closes the case bypass on
case-insensitive filesystems.

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

# MCP Evidence Server — Public Read-Only Evidence Surface

**Status:** Accepted with ADR-0034 on 2026-11-10. Nothing is implemented. Hosted work stays blocked on the open owner inputs.
**Version:** 0.1.0
**Date:** 2026-11-10
**Parent specification:** `specs/001-financial-evidence-lab/spec.md` v1.2 (governs on conflict)
**Design contract:** [`docs/research/mcp-evidence-server-spec.md`](../../docs/research/mcp-evidence-server-spec.md). ADR-0034 freezes its §6 and §7. This document adds no design; it states the requirements, packages and gates.
**Decision record:** [ADR-0034](../../docs/decisions/ADR-0034-public-read-only-evidence-surface.md) (Accepted, qualified)
**Scope:** new scope outside the MVP release gates (parent §19.6, §26). No canonical `T####` task covers it.
**Baseline measured:** `origin/main` @ `2f7f066`
**Canonical task ledger:** `specs/001-financial-evidence-lab/tasks.md`. This package changes nothing in it. [`tasks.md`](tasks.md) here lists milestone tasks only and tracks no completion state.

---

## 1. Purpose and standing

Give the product its first public surface: a read-only MCP server and a
Claude plugin over the public SEC corpus. A client model writes the answer;
the server supplies evidence and checks it.

This package is subordinate to the parent specification under constitution
v1.2.0. Where the design contract and this document disagree, the design
contract governs the surface's behaviour and the parent governs everything
else.

### 1.1 What this document does not do

It authorizes nothing beyond ADR-0034. Flipping a registry `status`,
provisioning a credential or hosting target, and adding canonical tasks
remain integration-lead actions. §7 lists what is owed.

## 2. Evidence basis

| Claim | Source |
|---|---|
| Filings are dated at midnight UTC on the filing date; acceptance time is not stored | `workers/src/fel_workers/consumer.py`; `workers/src/fel_workers/ingestion/discovery.py` |
| Two reads take no cutoff | `apps/api/app/corpus.py` (`get_source_span`, document metadata) |
| The verifier is deterministic but named as a mock | `packages/retrieval/fel_retrieval/verification.py`; `apps/api/app/retrieval_pipeline.py` |
| Search always resolves an embedding provider | `apps/api/app/retrieval_pipeline.py`; `apps/api/app/retrieval.py` |
| Embedding rows live in their own table, so a keyword-only index needs no schema change | `db/migrations/0003_retrieval_core.sql` (`retrieval_embeddings`) |
| Anonymous reads are rejected today | ADR-0004 |
| Company-facts facts cite a fetch-dated snapshot | `workers/src/fel_workers/ingestion/company_facts.py` |
| No MCP dependency, package, issue or registry entry existed before this package | `requirements.lock`; `docs/handoff/workstreams.yaml` |

## 3. Requirements

Each requirement names the design-contract section that defines it. The
contract's wording governs.

| ID | Requirement | Contract |
|---|---|---|
| `FR-MCP-001` | Eight read-only tools, each with a title, read-only annotations, input and output schemas, structured content and a text copy | §7 |
| `FR-MCP-002` | Every evidence tool accepts `as_of`, echoes `effective_as_of`, and applies the cutoff to aggregates as well as rows | §6.1, §6.2 |
| `FR-MCP-003` | Strict visibility: a document is visible only with a verified acceptance time at or before the cutoff | §6.2 |
| `FR-MCP-004` | No existence oracle: hidden and missing references are indistinguishable in every tool | §6.2, §7.2 |
| `FR-MCP-005` | Citations carry code-point offsets, a recomputable hash, accession, source URL and acceptance time | §7.1 |
| `FR-MCP-006` | An `evidence_context` with request-side pins gives byte-identical replay; an unavailable pin is an explicit error | §6.3 |
| `FR-MCP-007` | Deterministic verification with closed states; a numeric match alone never yields `supported` | §7.2 |
| `FR-MCP-008` | Company-facts snapshots and their facts are never served | §4 (P10) |
| `FR-MCP-009` | Search and index build resolve no model or embedding provider | §4 (P5), §8 |
| `FR-MCP-010` | Request limits, deadlines, concurrency caps and a global budget bound backend work | §7.4 |
| `FR-MCP-011` | Actionable error codes with retry guidance; only evidence existence is uninformative | §7.5 |
| `FR-MCP-012` | Filing text is treated as untrusted data and appears only in structured fields | §10 |
| `FR-MCP-013` | Anonymous access uses a dedicated read-only role and pool with no tenant-table privilege | ADR-0034 decision 2 |
| `FR-MCP-014` | The HTTP mount is off unless explicitly enabled | ADR-0034 decision 3 |
| `FR-MCP-015` | A Claude plugin supplies skills, commands and a marketplace manifest, and claims no safety guarantee | §9 |
| `NFR-MCP-001` | Default responses stay within the size budget; latency targets are met on the 20-issuer corpus | §7.3 |
| `NFR-MCP-002` | No network egress and no paid call at tool time | §5.3, §8 |

### 3.1 Out of scope

Server-side answer generation; model-based entailment; the dense lane on the
hosted server; tenant data; licensed data; write tools; a public web reader;
corpus expansion beyond the canonical cohort. The design contract §3 and §11
list these.

## 4. Packages

All nine are registered in `docs/handoff/workstreams.yaml`, which holds their status.

| Package | Issue | Delivers | Depends on |
|---|---|---|---|
| `MCP-CONTRACT` | #392 | Migration `0012`, read-only role, schemas and fixtures, OpenAPI 0.10.0, the `mcp` dependency, the evidence interface | ADR-0034 (accepted) |
| `MCP-INGEST-ACCEPTED-AT` | #393 | Acceptance timestamps at ingest, backfill, same-day amendment repair | `MCP-CONTRACT` |
| `MCP-CUTOFF-PREDICATES` | #394 | Existing reads and lanes compare against acceptance time | `MCP-CONTRACT` |
| `MCP-EVIDENCE-READ` | #395 | The shared evidence-read service and keyword-only search | `MCP-CONTRACT` |
| `MCP-VERIFIER` | #396 | The promoted deterministic verifier and the verification report | `MCP-CONTRACT` |
| `MCP-SERVER` | #397 | The MCP package, its tools, limits, errors and the mount | `MCP-CONTRACT`; integration needs #395 and #396 |
| `MCP-PLUGIN` | #398 | The Claude plugin and marketplace manifest | `MCP-CONTRACT` |
| `MCP-EVALS` | #399 | The acceptance suites of the design contract §12 | `MCP-CONTRACT`; full runs need #395, #396, #397 |
| `MCP-HOSTED-PILOT` | #400 | The hosted invitation-only pilot | All of the above; #177; hosting |

## 5. Acceptance gates

1. **Strict temporal validity is 1.0.** The property-based leakage suite
   passes for every tool, including aggregates, same-day cases and late
   amendments.
2. **No oracle.** `verify_claim` reports for a hidden span and a nonexistent
   span are byte-identical.
3. **Citation integrity.** Every returned citation re-verifies, including
   non-BMP text.
4. **Verifier contract.** Every rule of the design contract §7.2 has a test,
   and existing verification goldens are byte-identical.
5. **Replay.** A resolved context replays byte-identically across a corpus
   publish and an index rebuild.
6. **No provider calls.** A test proves search and index build resolve no
   provider.
7. **Privilege.** The read-only role is denied every tenant and operational
   table.
8. **Parent gates are untouched.** Nothing here relaxes a parent §19.6
   threshold. The 65-question retrieval baseline is reported, not gated.

The hosted pilot has its own product measures (design contract §11.1).
Directory acceptance does not establish usefulness.

## 6. Risks

- **Acceptance-time timezone is unverified.** A wrong assumption shifts every
  cutoff by hours. #393 isolates it; the lead confirms it before any hosted
  run.
- **Tighter cutoffs change existing goldens.** #394 must justify each change.
- **`mcp` 2.x dependency fit is unverified** against the pinned HTTP stack.
  #392 reports it before lanes start.
- **`packages/retrieval` hosts three lanes.** #394, #395 and #396 own
  disjoint files; [`plan.md`](plan.md) records the split.
- **Twenty issuers may be too narrow** to earn repeat use. The pilot tests
  this before any expansion.

## 7. Owed by the integration lead

1. Supply the open owner inputs in ADR-0034: the operating budget, the
   product name and the plugin-manifest ruling.
2. Merge the design contract (PR #389) before or with this package.
3. Review and merge `MCP-CONTRACT` (#392), then flip the lanes to `ready`.
4. Confirm the acceptance-time timezone with an approved SEC user agent.
5. Decide whether to add canonical tasks for this scope.
6. Provision hosting and the operating budget before #400.

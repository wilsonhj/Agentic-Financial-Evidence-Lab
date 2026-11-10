# MCP Evidence Server — Milestone Tasks

**Parent ledger:** `specs/001-financial-evidence-lab/tasks.md` is the sole
canonical task ledger and governs. This scope is new: **no canonical `T####`
task covers it**, so these milestone tasks map onto none. Adding canonical
tasks is an integration-lead decision (`spec.md` §7).

This file **tracks no completion state**. It has no checkboxes on purpose.
Delivery state lives in GitHub issues and pull requests, and package status
in `docs/handoff/workstreams.yaml`.

Requirement IDs refer to [`spec.md`](spec.md) §3. Section references such as
"§7.2" refer to the design contract,
`docs/research/mcp-evidence-server-spec.md`.

## MCP-CONTRACT (#392)

- `MCP-101` Write migration `0012`: `documents.accepted_at`,
  `documents.timestamp_precision`, a supporting index, and
  `fel_guard_candidate` on `COALESCE(accepted_at, published_at)`.
- `MCP-102` Create the `fel_public_read` role with SELECT on untenanted
  corpus and retrieval-index tables only, plus harness tests for each denial
  (`FR-MCP-013`).
- `MCP-103` Add schemas and fixtures for the citation, evidence context,
  verification report and error (`FR-MCP-005`, `006`, `007`, `011`).
- `MCP-104` Add input and output schemas and fixtures for the eight tools
  (`FR-MCP-001`).
- `MCP-105` Bump OpenAPI to 0.10.0 with optional acceptance fields on
  document metadata, and regenerate the client.
- `MCP-106` Add and pin the `mcp` SDK; report its fit with the pinned HTTP
  stack.
- `MCP-107` Publish the evidence interface that the adapter calls.

## MCP-INGEST-ACCEPTED-AT (#393)

- `MCP-201` Read `acceptanceDateTime` at discovery and store it at fetch
  with second precision.
- `MCP-202` Isolate timezone interpretation in one function, pinned by a
  fixture pair.
- `MCP-203` Add an idempotent backfill job that leaves unresolved records
  NULL.
- `MCP-204` Order restatement targets by acceptance time, and test a
  same-day original and amendment.

## MCP-CUTOFF-PREDICATES (#394)

- `MCP-301` Switch the corpus listing and version-resolve predicates.
- `MCP-302` Switch the reader target and sibling predicates.
- `MCP-303` Switch the retrieval lane predicate.
- `MCP-304` Test same-day hidden, same-day visible and no-acceptance-time
  cases, and justify every golden change.

## MCP-EVIDENCE-READ (#395)

- `MCP-401` Implement strict visibility and the single hidden-or-missing
  code path (`FR-MCP-003`, `004`).
- `MCP-402` Implement context resolution, pins, unavailable-pin errors and
  context-bound cursors (`FR-MCP-006`).
- `MCP-403` Implement the company resolver and filing listing with
  cutoff-filtered coverage (`FR-MCP-002`).
- `MCP-404` Implement bounded section reads and citation reads with
  code-point slicing and hash recomputation (`FR-MCP-005`).
- `MCP-405` Implement fact reads that exclude company-facts snapshots and
  filter lineage links by visibility (`FR-MCP-008`).
- `MCP-406` Implement keyword-only search and index build with no provider
  (`FR-MCP-009`).
- `MCP-407` Enforce request limits before database work, on the read-only
  role with a statement timeout (`FR-MCP-010`, `013`).

## MCP-VERIFIER (#396)

- `MCP-501` Extract one shared rule implementation and add
  `DeterministicCitationVerifier` as `deterministic-v1`, keeping the mock's
  identity strings and goldens byte-identical.
- `MCP-502` Build the verification report with a single `visible` check
  (§7.2).
- `MCP-503` Add the table-driven rule tests, including the changed-wording
  numeric case (`FR-MCP-007`).

## MCP-SERVER (#397)

- `MCP-601` Scaffold `packages/mcp-server` and register it with the shared
  gates.
- `MCP-602` Implement the eight tools with annotations, schemas, structured
  content and resource links (`FR-MCP-001`).
- `MCP-603` Map errors (§7.5) and enforce the deadline, concurrency caps and
  global budget (§7.4).
- `MCP-604` Provide the stdio entry point and the ASGI app with host and
  origin validation.
- `MCP-605` Mount at `/mcp` behind an explicit setting, with no tenant
  authentication dependency (`FR-MCP-014`).
- `MCP-606` Pin tool names, descriptions and order in a snapshot test, and
  test both protocol eras.

## MCP-PLUGIN (#398)

- `MCP-701` Write the plugin manifest and MCP configuration with a
  self-hosted override.
- `MCP-702` Write the three skills, two commands and one agent
  (`FR-MCP-015`).
- `MCP-703` Add the marketplace manifest and pass plugin validation.

## MCP-EVALS (#399)

- `MCP-801` Property-based temporal leakage suite across every tool.
- `MCP-802` Byte-identical hidden-versus-missing verification reports.
- `MCP-803` Citation round-trip and link-scope checks.
- `MCP-804` Determinism and replay across a corpus publish and index
  rebuild.
- `MCP-805` Error-contract and request-limit scenarios.
- `MCP-806` Retrieval baseline over the 65-question seed, reported and not
  gated.

## MCP-HOSTED-PILOT (#400)

- `MCP-901` Deploy the mount on the hosted API with the read-only role and
  pool.
- `MCP-902` Publish corpus coverage and a privacy policy.
- `MCP-903` Size limits and the global budget to the recorded operating
  budget.
- `MCP-904` Run the acceptance suites and a pilot-volume load test on the
  hosted target.
- `MCP-905` Run the invitation pilot and report its measures (§11.1).

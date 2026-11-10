# Implementation Plan: MCP Evidence Server

**Branch**: `spec/006-mcp-evidence-server` | **Date**: 2026-11-10 | **Spec**: [`spec.md`](./spec.md)

**Input**: Feature specification from `/specs/006-mcp-evidence-server/spec.md`

> **Subordinate plan**, permitted by constitution v1.2.0.
> `specs/001-financial-evidence-lab/plan.md` is the parent and governs on
> conflict. The surface's behaviour is defined only by the design contract,
> `docs/research/mcp-evidence-server-spec.md`. Package contents are defined in
> `spec.md` §4 and the GitHub issues; this file states the gate result and
> the sequencing rules.

## Summary

Nine packages take the repository from no public surface to a hosted pilot.
One contract package freezes every shared-path change. Seven packages then
run in parallel on mocks and fixtures. The ninth, the hosted pilot, waits on
infrastructure.

ADR-0034 was accepted on 2026-11-10, so the offline packages may be
dispatched in wave order. The hosted pilot stays blocked.

## Technical Context

> **Architecture pointer.** Runtime, tooling, storage and topology are
> defined by `docs/decisions/ADR-0002-mvp-stack.md` and are not restated
> here.

**New dependency**: the `mcp` Python SDK 2.x, added by `MCP-CONTRACT` under
ADR-0034 decision 8.

**New first-party package**: `packages/mcp-server` (module `fel_mcp`).
Scaffold registration rides under ADR-0008.

**Contract movement**: migration `0012`; OpenAPI 0.9.0 to 0.10.0 (additive);
four new schema families. All in `MCP-CONTRACT`.

**Constraints**: `defaults.credentials: mock-only` holds for every package
except `MCP-HOSTED-PILOT`. No package may make a network call to sec.gov or
a paid provider.

**Scale/Scope**: 9 packages, 9 issues, 4 waves.

## Constitution Check

*GATE: Must pass before dispatch. Re-check after the contract package.*

- [x] **Evidence and temporal-cutoff behavior is explicit and testable.**
  Strict acceptance-time visibility, the no-oracle rule and replay are
  requirements `FR-MCP-002` to `FR-MCP-006`, each with an acceptance gate.
  This package also removes an existing same-day leak.
- [x] **Financial calculations are deterministic, decimal, typed, and
  source-linked.** The surface computes nothing. Numeric verification reuses
  the existing exact Decimal comparison.
- [x] **Tests and numeric evaluation gates precede implementation tasks.**
  `MCP-CONTRACT` ships schemas and fixtures first. `MCP-EVALS` builds its
  suites against them in parallel with the lanes.
- [ ] **Tenant isolation, secrets, auditability, prompt-injection defenses,
  and cost ceilings are covered.** Covered by design: a read-only role with
  denial tests, untrusted-text handling and per-request work bounds. **Open:**
  the operating budget that sizes the global limit is an owner input
  (ADR-0034 input 2). It must be recorded before `MCP-HOSTED-PILOT`.
- [x] **The design stays within the approved stack or includes an approved
  complexity ADR.** A new dependency and a new package are added. ADR-0034
  covers both and was accepted on 2026-11-10.

### Gate result

**One of five is open: the operating budget.** It gates only
`MCP-HOSTED-PILOT`. Offline packages may be dispatched in wave order.

## Waves

| Wave | Packages | Gate to enter |
|---|---|---|
| 0. Decision | none | Done: ADR-0034 accepted on 2026-11-10 |
| 1. Contract | `MCP-CONTRACT` (#392) | Wave 0 |
| 2. Lanes | `MCP-INGEST-ACCEPTED-AT` (#393), `MCP-CUTOFF-PREDICATES` (#394), `MCP-EVIDENCE-READ` (#395), `MCP-VERIFIER` (#396), `MCP-SERVER` (#397), `MCP-PLUGIN` (#398), `MCP-EVALS` (#399) | #392 merged |
| 3. Integration | #397 against real #395 and #396; #399 full runs | #395, #396 merged |
| 4. Hosted pilot | `MCP-HOSTED-PILOT` (#400) | Wave 3 green; #177; hosting; budget |

Wave 2 admits seven concurrent packages. That is the maximum safe
parallelism: every allowed path below is disjoint.

## Path exclusivity

| Package | Owns |
|---|---|
| #392 | `db/migrations/**`, `packages/contracts/**`, lockfiles and dependency tables, `packages/retrieval/fel_retrieval/evidence/interfaces.py` |
| #393 | `workers/src/fel_workers/ingestion/**`, `workers/src/fel_workers/consumer.py`, `workers/tests/**` |
| #394 | `apps/api/app/corpus.py`, `apps/api/app/reader.py`, `apps/api/tests/**`, `packages/retrieval/fel_retrieval/lanes.py`, lane tests |
| #395 | `packages/retrieval/fel_retrieval/evidence/**` except `interfaces.py`, `packages/retrieval/tests/evidence/**` |
| #396 | `packages/retrieval/fel_retrieval/verification.py`, `verification_report.py`, verification tests |
| #397 | `packages/mcp-server/**`, the mount in `apps/api/app/main.py`, one setting in `apps/api/app/config.py`, one mount test |
| #398 | `plugins/financial-evidence-lab/**`, `.claude-plugin/marketplace.json` |
| #399 | `evals/mcp/**` |
| #400 | `infra/**`, `docs/runbooks/**`, `docs/handoff/CREDENTIALS.md` |

Rules:

- #394, #395 and #396 share `packages/retrieval` but no file. #395 imports
  `lanes.py` and must not edit it.
- #394 and #397 both touch `apps/api`. #394 owns two modules and the test
  tree; #397 owns the mount, one setting and one named test file. #397 must
  rebase on #394 if both are open.
- `evals/**` is claimed by other registered packages (#62, #67, #68, #108,
  #177, #201). #399 is confined to the new `evals/mcp/` subtree.
- `workers/tests/**` is also claimed by #62 and #66. #393 must not run
  concurrently with either; both are blocked today.

## Review

Each pull request is reviewed by a different agent vendor than its author,
and by the integration lead. The packages are sized so that one lane fits
one reviewable pull request. `MCP-EVIDENCE-READ` is the largest and may
split into reads and search as stacked pull requests.

# Supplemental load requirements and review dispositions

Date: **2026-11-15**. Original proposal reviewed:
`ce6f2fba4b740d715399025cf443156943a64ec0`; code baseline remains
`33c6a635c05460624c894d00363d8710a780adc3`.

These are bounded supplements to the [implementation specification](implementation-spec.md),
following the [different-vendor Claude review](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/pull/422#issuecomment-6888330974)
and independent OpenAI recheck. They add acceptance requirements and clarify
existing governance. They change no SLO, quota, financial formula, canonical task,
architecture approval, workstream ownership or execution authorization. This remains
a documentation proposal, not the canonical task ledger or an implementation dispatch.

The [original review record](review-record.md) and [evidence manifest](evidence.json)
retain their historical provenance. No historical source or excerpt hash is updated
to imply that these supplements were part of the original review.

## Supplemental requirements

### Provider and data-source policy

Choose `synthetic` when authoring the standard capacity profile. The manifest must
still explicitly contain its mode: missing or unknown modes fail preflight, with
no implicit substitution. Use isolated synthetic identities, committed source
fixtures and deterministic provider responses for this profile. Load seeding must
not fetch from EDGAR or other live data sources. Required fixture bytes and their
hashes must already be available before timed work begins.

Synthetic preflight must verify the actual worker/provider binding, not just the
manifest label. For a worker launched through `fel_workers run`, require
`FEL_SEC_LIVE` unset and exactly one applicable explicit non-production mode:
`FEL_MOCK_SMOKE` or `FEL_FIXTURE_INGEST`. Fixture ingestion additionally requires
valid fixture and storage directories; it must reject network fallback. Keep the
extraction queue/model opt-in checks separate: synthetic extraction requires the
configured deterministic mock binding and the correct extraction queue. Record
the effective mode of each target process and reject any incompatible process.

This does not change the existing local extraction harness. It directly supplies
`MockSecClient` and its deterministic extraction provider to an extraction consumer;
it does not select SEC mode through the deployed-worker CLI. Its existing guards
remain authoritative. Source references: the baseline
[worker mode validation](../../../workers/src/fel_workers/__main__.py) and
[load fixture consumer](../../../apps/api/benchmarks/extraction_load_fixture.py),
also covered by original source-register entries R04/R12.

`staging-provider` and `live` are separately selected profiles. Before execution,
require an explicit owner opt-in record referenced by the manifest, naming the
target, permitted providers/data sources, identities, time window and spend ceiling.
No such opt-in is supplied by this proposal. Record applicable provider quotas and
data-source fair-access policy, including SEC request limits and declared User-Agent
if SEC access is separately authorized; enforce those limits globally across target
workers, retries and overlapping deployments. Never use a capacity test to stress
EDGAR or another external source. Keep provider throughput evidence separate from
deterministic mock capacity and keep credential values out of all artifacts.

In the original promotion check, “no fixture bypass” means no fabricated success,
preapproved result or skipped application stage can satisfy a gate. It does not
require a synthetic tier to call a live provider. Verify that each profile used its
declared mock, fixture or explicitly authorized provider path.

### Independent numerical correctness oracle

For every exercised extraction or calculation scenario, freeze independent expected
monetary values, Decimal representation rules, units and fiscal periods in the
versioned fixture before running. Compare the approved immutable payload and any
exercised derived results exactly against those expectations under both low load
and declared tier load. Include expected provenance and canonical hashes where
applicable. Apply the existing financial contracts' canonicalization and permitted
scale rules; do not invent new rounding, precision or formatting requirements.

Expected fixture values must be independently specified. The acceptance harness
must not import the producer's normalization or calculation helpers to generate
its expected numbers. A single-client golden run is useful for comparison but
cannot establish correctness by itself: it can reproduce the same numerical bug.
Hash consistency alone is likewise insufficient.

Add reporter/oracle negative fixtures for an incorrect Decimal value, incorrect
unit and incorrect fiscal period, each with internally consistent payload hashes,
valid provenance, successful HTTP responses and passing timing. Each must produce
FAIL. A deterministic numerical mismatch is an integrity failure regardless of
error percentage. These are requirements for future harness tests, not claims
that this documentation PR implements or executes those tests.

### Retained baseline ownership and conditional delivery

The registered
[`M3-REVIEW-LOAD-ACCEPTANCE` workstream](../../handoff/workstreams.yaml)
owns #61's existing `apps/api/benchmarks/**`, load-report test and
`apps/api/EXTRACTION_LOAD.md`. The
[2026-09-14 load and hosted-reader acceptance plan](../../superpowers/plans/2026-09-14-load-and-hosted-reader-acceptance.md)
and #108's `READER-PROD-SMOKE` ownership remain in force. This proposal extends the
testing program while retaining their gates and ownership; it supersedes neither
plan and does not reassign either workstream.

All PRO-xx references in the original delivery sequence are conditional reuse
candidates from unmerged PR #420, not registered workstream IDs. If #420 is not
adopted or its interfaces change, the integration lead must name a registered
owner, reconcile exact allowed paths and freeze equivalent interfaces before any
slice is dispatched. Do not create competing harness or integration implementations.
In particular, proposed `evals/load/` ownership must be reconciled with the
registered owners of broader `evals/**` paths as well as any adopted PRO-09 scope.

### Explicit quotas and overload classification

The manifest's required admission policy must include effective numeric limits
and burst sizes, their organization/route/provider scope, coordination semantics
and any overlap/retry accounting. The baseline retrieval limiter is 5 QPS with
burst 20 per organization and selected route; this is not a global user allowance.

At the illustrative 1,000-user rate of 100 actions/sec, 8% retrieval submissions
to one organization/route offer 8 QPS. Once the burst is exhausted, that exceeds
the baseline 5 QPS policy. Classify this case as a separate overload profile with
expected bounded 429 responses. It cannot certify normal 8-QPS success throughput.
A normal hot-tenant profile must fit the declared policy, including its pacing
and bursts. Do not silently raise quotas, add organizations, change the action mix
or disable limits to relabel a failure. Any separately approved policy change is
a distinct configuration and capacity claim. Existing zero-unexpected-quota-denial
and normal-error gates remain unchanged.

### Applicable architecture and dependency gates

Native PostgreSQL primitives and existing Playwright tooling do not themselves
require a new ADR merely because the proposal uses them. Preserve existing
contracts and benchmark the proposed in-stack coordination. An actual stack
addition/substitution remains subject to ADR-0002 and its benchmark/accepted-ADR
rule. Contract/schema/migration changes and shared paths retain the exact
[AGENTS.md](../../../AGENTS.md) approval rules; root dependency or configuration
changes require their applicable authorization and contract-change review.
Do not equate a contract-change label with acceptance of a required ADR, or require
an ADR for test-only dependency work where repository governance requires only the
specific root-file authorization. Existing trigger/transport decision gates apply.

## Review dispositions

| Claude finding | Disposition |
| --- | --- |
| 1. Mock-first/live opt-in not explicit | Added explicit synthetic selection and fail-closed mode validation, actual worker/provider preflight, offline seeding and separate owner opt-in for provider profiles. The existing local harness already injects mocks directly. |
| 2. Existing load ownership | Named the retained #61/#108 owners and September plan; made all PRO references conditional and required reconciliation of broader evals ownership before dispatch. No reassignment or supersession. |
| 3. Coordination/dependency ADR gates | Clarified applicable governance. Existing PostgreSQL/Playwright use is not a stack substitution; actual stack, contract, migration and shared-file changes retain their respective gates. |
| 4. Hot-tenant quota arithmetic | Confirmed 8 QPS exceeds the 5 QPS baseline after burst. Required explicit numeric policy and overload classification. The original normal-profile policy-fit rule already prohibited this false normal pass. |
| 5. Decimal correctness oracle | Verified omission: self-consistent hashes do not prove expected values. Added independent expected Decimal/unit/period fixtures and negative mismatch cases. |
| 6. Local runner not executed | No source defect verified. The command retains its source-verified status; no isolated PostgreSQL execution is claimed by this supplement. |

## Validation scope

Independent recheck reproduced the historical benchmark from raw measured rows:
100 observations per operation, 25-way minimum wave overlap, and p95
152.483084/1501.912/218.224167/284.669292 ms for create/review/waiting-reconnect/
terminal-reconnect. Review remains FAIL against 1000 ms. This is arithmetic
reproduction of historical evidence, not a new load measurement.

Follow-up checks:

| Check | Result |
| --- | --- |
| Markdownlint CLI2 0.18.1, four changed Markdown files | Zero errors |
| `python3 .github/scripts/check-docs-index.py` | 173 Markdown files reachable, 18 exclusions |
| Changed-document relative file links/anchors, repository link parser and local heading check | 79 resolved |
| `git diff --cached --check` | Passed |
| Original evidence verification | All 36 repository hashes and 15 excerpt hashes match; `evidence.json` and `sources.md` byte-identical to original reviewed head |

No hosted, live-provider or new application-load execution is claimed.

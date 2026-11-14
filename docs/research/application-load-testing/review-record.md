# Independent verification record

Date: **2026-11-14**. Scope: [implementation specification](implementation-spec.md),
[source register](sources.md) and [evidence manifest](evidence.json).
Repository baseline: `33c6a635c05460624c894d00363d8710a780adc3`.

After the draft was complete, the author assigned three subagents separate
read-only verification tasks. Reviewers inspected source independently, reported
findings outside the repository and did not edit the specification or post GitHub
messages. The author incorporated fixes and requested targeted rechecks. This is
internal OpenAI source/design review, not different-vendor approval, hosted
acceptance or a performance certification.

## Reviewer scope and results

| Reviewer | Independent work | Result |
| --- | --- | --- |
| `/root/verify_repository_claims` | Read pinned code for R01–R16; reproduced historical report from 504 raw rows; checked command prerequisites, source hashes and reservation call sites | Findings corrected; no remaining repository-claim blocker |
| `/root/verify_platform_claims` | Re-fetched E01–E15 from official pages and version-pinned Next.js/Uvicorn files; checked source scope and D01–D04 arithmetic | No blocking factual contradiction; listener-mode precision and retained excerpts improved |
| `/root/verify_test_design` | Read relevant code and PR #420's pinned ownership map; checked timing oracles, demand definition, concurrent cohorts, queue lifecycle, reducers and false-pass risks | Five design findings corrected and rechecked; no remaining blocking design finding |

All reviewers explicitly limited their conclusions to research/specification
quality. None ran a hosted application load test or certified any user tier.

## Findings and dispositions

| Finding | Correction incorporated |
| --- | --- |
| Migration command ran before clearing libpq routing overrides | Clear `PGHOSTADDR` and `PGSERVICE` before migration; retain explicit dedicated-local-database prerequisite |
| Harness subprocess/default worker count could inherit environment overrides | Clear Uvicorn worker/reload overrides, set `WEB_CONCURRENCY=1`, qualify subprocess claim and require effective topology capture |
| Retrieval 202/failure recording could be overstated | State that database failure can leave a queued run/reservation and require a failing workflow deadline; include `retrieval_queries.py` reservation call in provenance |
| First-event/answer timing could start after a slow query POST and falsely pass on fast replay | Start end-to-end clocks at initiating action; identify captured-high-water replay, retain separate connection timing and require delayed-query negative fixture |
| Stream count omitted event workload | Require event rate, payload/batch distribution, subscriber fan-out, active/idle distinction and delivery/backlog assertions |
| Queue job completion could be confused with approved extraction | Separate queue wait, execution, submission-to-worker-terminal and approval clocks; include queue wait and scripted reviewer pacing in declared deadlines |
| Independent component passes could be combined into an unsupported capacity claim | Require simultaneous HTTP/SSE/worker/review cohorts in the same hold, with unique-user accounting and declared identity overlap |
| Backlog/headroom/percentile criteria admitted inconsistent reducers | Freeze five-second samples, OLS/median/age queue gates, CPU p95 and memory/connection peaks; gate both latency views; fail missing data and add negative reporter fixtures |
| Long-lived LISTEN mode was only a generic compatibility check | Require direct/session-mode listener connections and retain session-state documentation; ordinary transaction-mode work remains separately tested |
| Some external evidence excerpts ended mid-sentence or discussed an adjacent topic | Replace with complete source-checked sentences/table rows; E14 now records the relevant session-state paragraph |

## Reproduced historical evidence

Independent repository review selected the measured rows from the 504-row
projected-results artifact, recomputed nearest-rank p95 and checked status,
verification, actor/sample completeness and overlap. Results exactly match the
pinned report:

| Operation | Measured samples | Failures | Minimum wave overlap | p95 ms |
| --- | ---: | ---: | ---: | ---: |
| Create | 100 | 0 | 25 | 152.483084 |
| 100-item review | 100 | 0 | 25 | 1501.912 |
| Waiting reconnect | 100 | 0 | 25 | 218.224167 |
| Terminal reconnect | 100 | 0 | 25 | 284.669292 |

Overall result remains **FAIL** on the strict review-latency budget. The design
reviewer separately reproduced these p95/sample values. No new performance
measurement is implied by reproducing the arithmetic of historical observations.

## Reviewed artifact identity

Hashes below identify the final substantive documents. The review record does
not hash itself. Git commit identity supplies the complete package identity.

| Artifact | SHA-256 |
| --- | --- |
| README.md | `dd514c8a613b88d3a2fb3438198d6c133b6129faaa062e9300e5ec651c5a818b` |
| implementation-spec.md | `da95442afc40c2b0622c371eb8dcad2ba982b3c94c63bf3b01ad01ada66112db` |
| sources.md | `af73f79c98e256e42e7c2d9432590e06fd4c65fe75e46294e94a4abdf7b5df29` |
| evidence.json | `bb482a6c3ee92b3d3f2e5bc340be441bf8314a9f96fde8911815ee578830470a` |

The design reviewer rechecked the final specification/source hashes above before
the excerpt-only manifest improvement; the platform and repository reviewers
rechecked the final manifest and confirmed the exact hashes above. Hashes establish artifact
identity, not an empirical capacity result.

## Documentation validation

Pre-commit results:

| Check | Outcome |
| --- | --- |
| Markdownlint CLI2 0.18.1 with repository configuration | Five changed Markdown files, zero errors |
| Repository documentation index | 172 Markdown files reachable, 18 documented exclusions |
| Changed-document relative file links and anchors | 98 resolved; checked with repository link parser plus local heading validation |
| Evidence integrity | All 36 pinned repository-file hashes and 15 excerpt hashes verified |
| Staged diff whitespace/scope | Clean; six documentation/evidence files only |

Reproducible source hash commands are in
[sources](sources.md#reproduce-the-code-and-historical-benchmark-checks).
The local link check is scoped to changed documents; it is not a claim that the
full CI Lychee job was run locally. No application behavior changed, so application
load, paid-provider or hosted deployment tests are not claimed.

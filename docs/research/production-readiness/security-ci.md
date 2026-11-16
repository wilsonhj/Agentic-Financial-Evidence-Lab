# Production supply-chain and security CI research

Issue #419; research only. Repository baseline: `33c6a635c05460624c894d00363d8710a780adc3`
(`main`, inspected 2026-11-14). All repository paths below are relative to the root.
Proposed files, jobs, interfaces and commands are implementation contracts, not deployed controls.
Official documentation was checked through Tavily on 2026-11-14; no live scanner, image build,
signature, cloud credential exchange or production DAST was executed for this note.

## Observed baseline and gaps

| Evidence | Current behavior and consequence |
| --- | --- |
| `.github/workflows/ci.yml`, `javascript` | Frozen pnpm install, formatting/lint/types/tests, then `node scripts/audit-bulk.mjs`; any earlier failure skips the advisory scan. |
| Same file, `python` | Hash-verified `requirements-dev.lock` install; Bandit and separate pip-audit calls for `requirements.lock`, `requirements-dev.lock`, `scripts/runtime/build.lock`, after quality checks. An earlier failure skips later scanners. |
| Same file, `secrets` | Independent Gitleaks job with full Git history. Retain its coverage and blocking behavior. |
| Same file, `runtime` | Two isolated production installs are compared; retain this reproducibility check. It does not establish image provenance or inventory. |
| `.github/workflows/advisories.yml` | Monday 06:00 UTC and manual refresh; JS and Python share one job. Python uses floating `requirements*.txt`, misses the build lock, and is skipped after JS failure. Workflow-level `issues: write` reaches scanner steps. |
| `scripts/audit-bulk.mjs`, `scripts/audit-bulk.test.mjs` | Audits resolved pnpm packages against npm bulk advisories; all unsuppressed severities block. Exit 0 clean, 1 findings/expired exception, 2 configuration/transport failure; bounded retry/timeouts already exist. Extend, do not replace with a weaker threshold or retired audit endpoint. |
| `scripts/audit-allowlist.json` | GHSA/package/reason/reviewBy entries; malformed or expired entries block, including unused expired entries. Current minimatch exception expires at the parsed `2026-12-01` UTC instant; retain that evaluator behavior. |
| `scripts/runtime/install.sh`, `scripts/runtime/build.lock` | Runtime and build dependencies use separate hashed locks; first-party wheels build with `--no-deps --no-build-isolation`. Human-edited `.txt` floors are not deployed versions. |
| `AGENTS.md`, `.github/workflows/shared-paths.yml`, `docs/decisions/ADR-0002-mvp-stack.md` | Future `.github/**` and shared config/lock changes require `contract-change` and integration-lead review. Advisory/pin changes need the lead's PR authorization record; framework/tool/stack or shared-contract changes need an accepted ADR where the repository rules apply. |

No production Dockerfile, container image build/digest manifest, image registry/digest
inventory, CodeQL workflow, SBOM/signature gate or DAST workflow was found in the
inspected tracked paths. Existing `infra/railway/{api,web,worker}.json` manifests
select `RAILPACK`; the accepted host is Railway (ADR-0002). Confirm how that host
exposes the deployed image and builder before choosing an OCI build/promotion
path; a scan of a locally rebuilt image cannot certify Railway's deployed image.
If immutable deployed images or attestations cannot be retrieved, record coverage as incomplete and
register the hosting/build decision; do not claim image assurance from source locks alone.

## Keep the controls distinct

| Control | Recommended FEL use | What passing does establish |
| --- | --- | --- |
| Dependency advisories | Existing npm bulk audit plus pip-audit over all three Python locks | Known advisories for the resolved versions at scan time; not malicious-package detection or application reachability. |
| Image CVEs/SBOM | Add pinned Trivy; scan OS and language packages in each actual runtime image by digest and platform | Inventory and known CVEs in that artifact; not code correctness. Keep image and source-lock inventories to expose omitted build tools. |
| Bandit | Preserve existing recursive paths and `pyproject.toml` config | Python AST security patterns; keep its present severity/confidence behavior. |
| CodeQL | Add `javascript-typescript` and `python`, explicit query suite, SARIF and analysis-completion checks [S2] | Additional source/data-flow analysis. It complements Bandit and cannot replace dependency or secret scanning. Verify repository licensing/feature availability first. |
| Gitleaks | Preserve full-history secret scan; redact evidence [S3] | Recognizable exposed-secret patterns. A discovered live credential still needs revocation and incident handling. |
| DAST | ZAP baseline against an allowlisted ephemeral staging URL and synthetic users; active/authenticated API scans only in an isolated test environment [S9] | Observed HTTP behavior within visited coverage. Baseline spiders and passively inspects; it is not an active attack scan or tenant-isolation proof. |
| Signatures/provenance | Verify digest, approved signer/workflow, source commit and builder policy before deployment [S6–S8] | Artifact origin/build claims. A valid signature is not a clean vulnerability verdict or an automatic SLSA level. |

Keep every existing JS/Python advisory gate at **all currently blocking advisories**, including
low/unknown severities; retain Bandit and Gitleaks gates. Proposed new image policy blocks all
critical/high CVEs (including unfixed), unsupported/EOL OS inventory and incomplete coverage;
retain lower/unknown findings for triage. Document any stricter gate already applicable before
implementation; no global `--ignore-unfixed`, severity downgrade or blanket baseline suppression.
Security owner owns triage; integration lead owns changes to the gate. Proposed response targets:
critical same-day assessment, high within two business days; these need owner acceptance, not an
invented statement that FEL already has an SLA.

## Proposed workflow topology

Extend `ci.yml`/`advisories.yml` through a shared reusable **read-only scanning** workflow, so PR,
protected-branch and scheduled runs use one scanner definition. Separate credentials and mutation.

1. PR: retain current quality/runtime/DB jobs; independent `security-js`, a three-item
   `security-python` lock matrix (`fail-fast: false`), `bandit`, `secrets`, and CodeQL language
   matrix (`fail-fast: false`). No security job depends on lint/tests or another scanner.
   Move existing audits into these required jobs without weakening branch-protection checks;
   migrate required check names atomically with lead review so an old name cannot silently vanish.
2. Protected release commit: rerun trusted-policy scans; build API/worker/web artifacts once,
   emit digest/platform inventory, SBOM and provenance; image scanning depends only on build
   availability, not on other scanner success. Separate per-image jobs continue after peer failure.
   If build fails, image results are `incomplete`; source scans still run.
3. Staging DAST depends only on deployment of its test target; it records `incomplete` if unavailable.
   Production promotion depends on all required source/image/signature/staging gates and archived
   evidence. Never sign/promote a failed candidate as an approved release.
4. Weekly/manual refresh: audit the protected default-branch locks **and** every currently deployed
   image digest from the deployment ledger, including a rollback image retained for reuse. Fetch
   fresh advisory databases and record timestamps. A daily deployed-image refresh is a proposed
   production target; keep the existing weekly scan until the new cadence is enabled and owned.
5. Each scanner writes its result even on failure and uploads evidence with `if: always()`.
   An unprivileged `collect-local` job has `needs` on all applicable scanner/build/DAST jobs
   in its workflow and `if: always()`; it records absent/skipped/cancelled targets as incomplete.
   A local scan gate checks those outcomes and the exact-attempt admission acknowledgement
   below, then the source workflow completes. It waits only for check invalidation, **not**
   for a receipt from the downstream collector.
6. A separate trusted `workflow_run: completed` collector validates and archives the completed
   run, then publishes a distinct required `Security evidence verified` check on the exact
   evaluated commit SHA. For PR merge tests, bind both PR head and evaluated merge SHA and
   publish on the SHA the repository's branch rules actually evaluate; prove this in a test PR.
   Record upstream run ID, attempt and publisher generation; use the lifecycle below rather
   than assuming those receipt fields alone invalidate an existing green commit check. The
   release controller verifies all applicable receipts and checks before promotion; it never
   relies on cross-workflow `needs`, which GitHub does not support. Missing checks block;
   an independent monitor marks overdue collection failed and alerts under an approved deadline.
   A same-run trusted release collector is an alternative requiring a separate reviewed design,
   not an interchangeable implementation of this completion-triggered topology.
7. A scheduled trusted notifier runs after collection/gate under `if: always()` and a separate
   `issues: write` job. Deduplicate incidents by advisory + component + image digest; distinguish
   findings from scanner outages. Notification delivery failure remains visible and cannot clear
   the failed gate. Never provide write tokens to package-install/scanner jobs merely for notification.

### Required-check lifecycle and activation gate

PRO-00 freezes the admission, publisher-state and receipt interfaces. PRO-02 owns their
trusted implementation under `scripts/security/evidence/**`; PRO-13 owns source-gate and
event wiring, required-check names and branch-rule configuration. PRO-20 owns the separately
authorized publisher/archive deployment and recovery acceptance. One narrowly scoped GitHub
App is the **only** writer of `Security evidence verified`; collectors submit candidate results
to that publisher and hold no check-write credentials. Pin its App ID as the branch rule's
expected source. Require the native source local-gate check too, with unique names across
workflows. Never use a collector's default-branch `GITHUB_SHA` as the evaluated commit [S10].

The proposed implementable protocol is:

1. Trusted `workflow_run: in_progress` handling and periodic API reconciliation discover
   executions; they are early invalidation aids, not an atomic start barrier. `requested`
   does **not** occur on reruns [S10]. The source local gate also calls an admission endpoint
   with repository/workflow/run/attempt and head/evaluated SHA. The endpoint authenticates
   the caller with a short-lived job identity, validates those values through GitHub's API
   and the frozen workflow/ref/event allowlist, and never accepts a scanner's success claim.
   The scanner job receives neither App credentials nor archive credentials.
2. The publisher serializes all begin/finish operations for `(repository, evaluated SHA)`
   in durable state. Each newly observed eligible execution increments a monotonic generation
   and records the expected workflow/run/attempt set. API-confirmed `run_attempt`, never
   webhook arrival order, selects a run's current attempt. Distinct eligible runs at one SHA
   are separate required slots; a new run cannot overwrite another required workflow's slot.
   Duplicate admissions are idempotent; old/out-of-order events cannot roll state backward.
3. Before acknowledging admission, the single writer changes every previously successful
   evidence check it owns for that SHA to a blocking `queued`/`in_progress` state, creates
   the current check if needed, and reads back check ID, SHA, App and state. If a completed
   check cannot be reset through the selected Checks API, the implementation must use and
   verify a blocking replacement with the actual branch rule before activation. Persist the
   generation/check binding; acknowledge only after durable state and GitHub agree. An API
   failure or timeout leaves admission unacknowledged and the source gate failing/pending.
   The local gate may pass only with the acknowledgement for **its exact current attempt**.
4. Source completion still triggers the archive collector. Before success, the publisher
   validates receipts for every required slot and re-queries GitHub for current attempts,
   conclusions and evaluated SHA. A candidate must match the current generation and all
   current slots. A newer admission invalidates prior candidates; stale/duplicate collectors
   may retain historical evidence but cannot mutate the current check. Cancellation, failure,
   missing output or overdue collection blocks; never fall back to an older successful attempt.
   Publish a blocking failure/cancelled conclusion for cancellation, never `neutral` or
   `skipped`, which protected branches may accept as passing [S11].
   A second allowlisted workflow at the same SHA uses this same writer and slot policy.
5. Keep the lock through each external check mutation and use a durable outbox for retries;
   database compare-and-swap alone cannot fence a late GitHub API write. Recovery must stop
   or fence the old writer and resolve in-flight writes before another writer publishes.
   No automatic lease-expiry takeover by a potentially concurrent publisher. Reconcile
   persisted generation, live run attempts and check state after crashes; uncertainty blocks
   admission/publication. Test a delayed old success write across restart, not only stale
   receipt rejection. The independent monitor detects dropped events and overdue runs.

**Unresolved hosted activation criterion:** this handshake guarantees invalidation before
an acknowledged source gate passes. It does **not** prove a zero-length stale-green window
between clicking rerun and admission acknowledgement. GitHub's native required-source-check
behavior must be demonstrated to block merging during that interval on the **same evaluated
SHA**, including full, failed-jobs-only and individual-job reruns. Every supported rerun form
must execute/revalidate exact-attempt admission; no skipped/neutral gate may stand in for it.
If the old native source success remains mergeable, or a rerun bypasses admission, keep this
topology inactive until a separately reviewed controller-only execution/merge authority design
closes that gap. Asynchronous events, a receipt validator, a freshness deadline and App binding
alone do not establish this property. No such hosted test or branch-rule change was performed
for this research revision; production enforcement remains pending [S10, S11].

Activation acceptance uses a test PR with fixed head **and evaluated merge SHA**: obtain
attempt-1 success, rerun, delay admission delivery and observe blocked merge before ACK;
then let the new local gate pass while pausing archive collection and observe blocked merge
again. Deliver attempt 1's collector after attempt 2 remains pending or fails; success must
not return. Repeat with queued/force cancellation, duplicate/dropped/reordered events,
publisher restart/late writes, and a second eligible workflow at that SHA. Inspect the actual
branch rule, native source check, App ID and check IDs/statuses, and attempt a merge without
bypass privileges. Local protocol fixtures cannot satisfy this hosted acceptance.

Do not put sequential scanners behind shell `set -e`, `&&`, a successful predecessor requirement,
or matrix fail-fast. A wrapper captures each subprocess exit then continues independent targets.
`continue-on-error` is acceptable only to reach collection when the final required gate consumes
the original exit/outcome; it must never turn an unavailable scan into success.
GitHub `always()` cannot guarantee execution after force cancellation/runner loss: missing evidence
and cancelled checks prevent promotion, and an independent freshness monitor alerts on missed scans.

## Result/evidence contract and script interfaces

Proposed `scripts/security/` modules; each package below can be built and fixture-tested separately.
The runner writes `evidence/<run>/<scanner>/<target>/result.json`, raw machine report and redacted
stdout/stderr; files are atomic, bounded in size, checksummed and bound to run ID, attempt and commit.
Every result carries `schema_version`, scanner name/version/binary digest, target type/name/digest/
platform, lock SHA-256 when applicable, command argv (without secrets), start/end UTC, exit code,
advisory DB/source/update UTC, policy revision, finding IDs/severity/package/version/fix,
exception IDs, status and reason. Preserve scanner-specific raw reports rather than losing detail.

| Status | Meaning | Required gate |
| --- | --- | --- |
| `clean` | Completed valid scan, complete expected scope, zero unsuppressed findings | Pass only if all other requirements and evidence checks pass. |
| `findings` | Completed valid scan with unsuppressed findings; include a separate `blocking` decision | Block existing advisory/secret/Bandit rules and new approved thresholds; nonblocking image findings remain visible. |
| `failed` | Scanner invocation, response parsing, configuration, transport or evidence integrity failed | Block; never label as zero vulnerabilities. |
| `incomplete` | Missing/skipped/cancelled target, unsupported ecosystem/platform, unresolved dependency or stale/missing database/evidence | Block when target/control is required. |

Expired/malformed exception files are explicit policy failures and block regardless of findings.
Active suppressions must remain in evidence with owner, issue, reason, exact advisory/component
scope, expiry and approver; do not carry a JS exception over to unrelated image packages by CVE alone.
Preserve the existing JS schema/evaluator; add any stronger metadata through a reviewed migration.
Python currently has no exception policy: do not introduce `--ignore-vuln` without separate approval.
The canonical scan status enum is `clean`, `findings`, `failed`, `incomplete`.
Use a separate required `reason` for `skipped`, `cancelled`, `missing`,
`upstream_failed`, `unsupported_scope`, `stale_data` or the classified failure;
successful results use `reason: null`. Preserve native job/exit states separately.
Completeness and policy decision are separate fields, not overloaded scan statuses.
Fail unknown statuses, schema versions, zero parsed packages, duplicate/mismatched targets and missing
matrix members. An empty report is clean only after successful scope/inventory validation.

Proposed interfaces (not existing commands):

```text
python scripts/security/scans/run.py --scanner pip-audit --requirements requirements.lock --out evidence/python-runtime
node scripts/audit-bulk.mjs --report-json evidence/js/report.json
python scripts/security/scans/image.py --image REF@sha256:DIGEST --platform linux/amd64 --out evidence/api
python scripts/security/evidence/collect.py --expected expected.json --inputs evidence --out collected
python scripts/security/evidence/gate.py --manifest collected/manifest.json --policy policy.json --receipt receipt.json
```

The existing npm script accepts no report flag: adding the illustrated flag must preserve its
0/1/2 exits, retry bounds and pure `evaluate()` tests, and expose scanned package counts/response
validation in JSON. The wrapper must not scrape the human “No blocking vulnerabilities” message.
`collect.py` returns nonzero on structural/integrity failure while still writing a diagnostic manifest;
`gate.py` returns 0 allowed, 1 policy/findings block, 2 failed/incomplete/evidence error. It consumes
explicit expected jobs/targets, not only whatever files happened to be downloaded.

Documented upstream CLI shapes for adapter implementation [S1, S4–S8]; placeholders require trusted
values and output directories. They were checked against upstream docs, not executed here:

```sh
pip-audit --strict --require-hashes -r requirements.lock --format json --output evidence/python-runtime.json
pip-audit --strict --require-hashes -r requirements-dev.lock --format json --output evidence/python-dev.json
pip-audit --strict --require-hashes -r scripts/runtime/build.lock --format json --output evidence/python-build.json
trivy image --scanners vuln --format json --output evidence/image.json --exit-code 0 "$IMAGE_REF_DIGEST"
trivy image --format cyclonedx --output evidence/sbom.cdx.json "$IMAGE_REF_DIGEST"
docker buildx build --sbom=true --provenance=mode=max --push --tag "$CANDIDATE_TAG" .
cosign sign --yes "$IMAGE_REF_DIGEST"
cosign verify --certificate-identity "$EXPECTED_WORKFLOW_IDENTITY" --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE_REF_DIGEST"
```

Install the scanner environment from reviewed pinned/hashes inputs (currently Python CI installs
`requirements-dev.lock`); scan the locks separately, not a floating fresh resolution. `--strict`
prevents skipped dependency collection from appearing successful. pip-audit documents 0/1 for clean/
findings; adapters must also require valid JSON, resolved inventory and no collection failure rather
than assuming every nonzero means CVEs. Trivy's explicit exit 0 above collects all severities; the
adapter must validate completion and apply policy from the report. An error still fails the run.
CycloneDX output does not include vulnerabilities by default: use the separate vulnerability JSON.

Build-time SBOM defaults can omit intermediate stages: inventory build dependencies separately and
enable/validate stage/context coverage as supported by the pinned builder [S5]. BuildKit provenance
and a Cosign image signature are separate artifacts. Require signed/verified attestations as well;
pin their predicate schema and verify subject digest, source repository/commit, builder/workflow and
build inputs, with negative fixtures for each. Do not assume `cosign verify` validates provenance
contents. `mode=max` can expose build arguments: credentials use secret mounts, never build args.
Deploy the verified digest without rebuilding; enumerate runtime platforms and scan every platform
that can be deployed. Store index and child digests; reject a digest/platform mismatch.

## Trust, archival and implementation packages

Use job-scoped least privilege: scanners `contents: read`, no cloud/OIDC/write access on fork PRs;
full commit-SHA action pins and scanner image/binary digests verified before execution. Dependency
installation may execute code: ephemeral hosted runners, no production credentials, separate caches
from privileged jobs. CodeQL's SARIF publishing permission must be scoped to that job and tested for
fork behavior; preserve local analysis evidence if GitHub refuses a privileged upload [S2, S8].

Privileged archive/sign/promote jobs run trusted protected-branch workflow/policy only, on fresh
runners, after validating the commit/run association; they never execute PR scripts, load PR caches,
source `.env` files or extract untrusted archives into executable paths. For the selected downstream
`workflow_run` topology, check repository, event, branch, exact upstream
run/attempt/SHA and conclusion, fetch artifacts by ID, treat contents as hostile data, reject path
traversal/symlinks/oversize/unknown fields, and never trust an artifact's claimed “clean” as authority.
Recompute release gates with trusted tools. A checksum from the same untrusted bundle is not proof
of origin. `pull_request_target` plus untrusted checkout/execution is prohibited [S8].

External immutable evidence archive is a separate package: GitHub artifacts are transport, not the
durable archive. Trusted archival uses short-lived OIDC credentials limited by repository, protected
ref/environment, audience and approved workflow; separate append-only prefix per run/digest and
retention policy. No fork receives cloud credentials. Archive manifest/checksums, SBOM, reports,
attestation/signature verification output and policy; return immutable object IDs/checksums and a
receipt validated by `gate.py`. Redact secret findings before transport and restrict report access.
Set retention with the evidence/archive owner rather than inventing a compliance duration.

| Package / proposed owner | Independent acceptance and fault-injection fixtures |
| --- | --- |
| A: Result schema, collector/gate / platform | Clean complete fixture passes; malformed JSON, truncated/empty report, duplicate target, wrong SHA/digest, missing matrix member, unknown status, skipped/cancelled job and expired exception all block. Reports survive prior job failure; missing archive receipt blocks. |
| B: Existing scanner adapters / security | Existing audit tests pass unchanged; npm HTTP 410, retry exhaustion/timeout, malformed response and zero parsed lock packages are failed, not clean. Inject a low-severity JS/Python finding to prove no weaker threshold. Each of three Python locks runs after a peer failure. |
| C: CI decomposition and scheduling / integration lead | Inject lint failure, JS advisory finding, Python setup failure and scanner timeout separately; other scanner jobs still execute, collection and gate run, required check fails. Scheduled scan proves all three locks plus deployed/rollback digests; stale DB and missing deployment ledger block. |
| D: OCI build/SBOM/provenance/signature / release platform | Tiny local known-vulnerable fixture image yields findings; clean fixture produces nonempty inventory. Reject wrong signer/issuer/source commit/subject/builder, unsigned SBOM, missing attestation, unscanned platform, tag movement and rebuild between verification/deploy. No claim of host coverage until deployed digest is retrieved and matched. |
| E: Privileged archival / evidence owner | Deny fork OIDC, wrong ref/audience, overwrite/delete; archive outage, digest mismatch, malicious path/symlink artifact and forged clean report fail. Artifact parsing never executes content; a fresh trusted release rerun is required. |
| F: CodeQL/DAST / application security | Language analysis completion and SARIF schema checks catch missing language output; seeded SAST fixture is detected. Local synthetic staging fixture produces ZAP report; wrong-host redirect, unavailable target and missing authenticated coverage report incomplete. No active production scan. |

Each package needs a bounded follow-up issue, allowed paths, fixture evidence and owning reviewer;
shared workflow/config changes remain lead-gated. Build/registry/host identity, OIDC archive provider,
retention owner, private CodeQL availability and staging auth are unresolved inputs, not reasons to
delay fixture work on A/B/C. This note neither dispatches those packages nor modifies runtime gates.

## Primary sources

All accessed 2026-11-14. Moving documentation must be rechecked against chosen pinned versions.

- [S1: pip-audit README: hashed inputs, strict collection, JSON, exits and security model](https://github.com/pypa/pip-audit).
- [S2: CodeQL capabilities/availability](https://docs.github.com/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql) and [workflow options/languages](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options).
- [S3: Bandit AST scope](https://bandit.readthedocs.io/en/latest/) and [Gitleaks usage/redaction](https://github.com/gitleaks/gitleaks).
- [S4: Trivy image scope](https://trivy.dev/docs/latest/guide/target/container_image), [JSON reporting/output](https://trivy.dev/docs/latest/configuration/reporting), [exit-code examples](https://trivy.dev/docs/latest/tutorials/integrations/gitlab-ci) and [SBOM formats/limitations](https://trivy.dev/docs/latest/supply-chain/sbom). Generated CLI-reference extracts omitted option bodies; CLI behavior was cross-checked in these guides, and pinned-version adapter smoke tests remain required.
- [S5: Docker SBOM stage coverage](https://docs.docker.com/build/metadata/attestations/sbom/) and [provenance modes/secrets](https://docs.docker.com/build/metadata/attestations/slsa-provenance/).
- [S6: Sigstore container signing](https://docs.sigstore.dev/quickstart/quickstart-cosign) and [identity/digest/attestation verification](https://docs.sigstore.dev/cosign/verifying/verify/).
- [S7: SLSA provenance v1.1](https://slsa.dev/spec/v1.1/provenance): provenance describes build claims; consumer verification policy is still required.
- [S8: GitHub secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use), [untrusted workflow/artifact boundaries](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target) and [OIDC permissions](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-cloud-providers).
- [S9: ZAP baseline scan behavior and options](https://www.zaproxy.org/docs/docker/baseline-scan/).
- [S10: GitHub workflow events, including rerun limits and workflow-run SHA](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). Rechecked 2026-11-15 via Tavily; `requested` excludes reruns.
- [S11: Protected branches, required checks and expected publisher App](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches). Rechecked 2026-11-15 via Tavily; native rerun/merge behavior still requires the hosted experiment above.

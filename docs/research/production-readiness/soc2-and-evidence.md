# SOC 2 readiness and vulnerability evidence

<details>
<summary>Relevant source files</summary>

- [CI](../../../.github/workflows/ci.yml) and [weekly advisories](../../../.github/workflows/advisories.yml) — actual scan and artifact behavior.
- [Bulk audit](../../../scripts/audit-bulk.mjs) and [allowlist](../../../scripts/audit-allowlist.json) — advisory gate and expiring exceptions.
- [Security specification](../../../specs/001-financial-evidence-lab/spec.md#17-security-privacy-and-governance) — product controls and retention.
- [Stack ADR](../../decisions/ADR-0002-mvp-stack.md) and [agent contract](../../../AGENTS.md) — approval and shared-path boundaries.

</details>

Source references verified against base commit `33c6a635c05460624c894d00363d8710a780adc3`.
Research date: **2026-11-14**. Issue: **#419**. Status: **proposed research; no controls, services, or policies accepted by this document**.

## Scope and examination boundaries

SOC 2 is an independent CPA examination of a service organization's described system and controls; a repository cannot itself become “SOC 2 certified.” Type II includes operating effectiveness across a specified period, whereas Type I addresses a point in time [S1, S3]. CI evidence supports selected controls; it cannot establish organization-wide readiness or replace auditor testing.

Management and the auditor must agree the legal entity, production service, principal commitments, system boundary, report users, applicable criteria, subservice organizations, complementary controls, and examination dates. Proposed FEL scope includes production web/API/workers, data stores, GitHub, operational identities, administrator endpoints, personnel, incident response, and relevant vendors. Document inclusive/carve-out treatment and customer responsibilities explicitly.

Use the **2017 Trust Services Criteria with 2022 revised points of focus** as the research baseline [S1]. Security/Common Criteria form the baseline; choose Availability, Confidentiality, Processing Integrity, and Privacy according to commitments and risk. FEL's financial transformations make Processing Integrity worth discussing with the CPA; correct financial outputs still require FEL's deterministic and provenance controls. Optional category exclusion does not remove applicable privacy law or contractual duties.

As of this research date, AICPA's October 28, 2026 announcement describes **proposed 2027 criteria**, with comments due January 15, 2027 and a conditional future effective date. Do not treat that exposure draft as an effective replacement [S2].

There is **no universal fixed SOC 2 Type II minimum observation period**. CPA firm Cherry Bekaert explicitly distinguishes common three-month initial practice from an AICPA minimum [S3]. Agree duration, sampling opportunities for infrequent controls, customer acceptability, remediation dates, and continuous coverage with the engagement auditor. Three, six, or twelve months are planning choices, not a readiness guarantee; a readiness assessment or Type I does not substitute for sustained Type II evidence.

SOC 2 also imposes **no universal seven-year vulnerability-evidence retention rule** [S4]. SEC's seven-year rule concerns accounting firms' records for issuer financial-statement audits/reviews, not a blanket SOC 2 archive obligation [S5]. Separately, FEL's existing specification §17.2 requires 365-day default query/model retention and seven-year audit metadata/approved artifact lineage, subject to a shorter lawful organization policy. Preserve that product requirement; management/legal must classify whether scan evidence falls within it and approve a distinct evidence schedule, legal holds, deletion, and minimum necessary personal data before setting irreversible locks.

## Repository evidence and gaps

These observations describe committed configuration at the base SHA, not a live successful run or verified production setting.

| Existing evidence | What the repository establishes | Gap for an evidence program |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Push/PR scans use Gitleaks; JS bulk advisory audit; Bandit; `pip-audit` on `requirements.lock`, `requirements-dev.lock`, and `scripts/runtime/build.lock`. Default token is `contents: read`. | Coverage/E2E uploads are present; dedicated complete security reports, immutable archive receipts, scan reconciliation, and human closure evidence are absent from this workflow. Earlier failures can skip later scans. |
| `.github/workflows/advisories.yml` | Monday 06:00 UTC/manual refresh; JS bulk audit; Python audit of `requirements.txt` and `requirements-dev.txt`; issue/comment on failure. | Python differs from CI's three lockfiles and is skipped if JS fails. Failure tracking does not distinguish vulnerability findings, service errors, and absent scans. No success-report archive is configured. |
| `scripts/audit-bulk.mjs` | Reads resolved JS packages; fails closed on registry/config errors; validates GHSA/package exceptions and expiry. | Console output does not preserve the complete advisory response or canonical structured run record; exception entries need an accountable approver and linked remediation record. |
| Specification §17.1 | Dependency/container scanning, append-only audit events, access boundaries, encryption, and managed secrets are requirements. | A requirement is not deployment evidence. These inspected workflows do not establish container scanning, vendor review, endpoint posture, organization MFA, access-review operation, or production archive controls. |

Do not replace the existing fail-on-advisory gate with severity SLAs through this proposal. Any change to gate semantics, `.github/**`, shared schemas, or underlying services requires its own authorized package and applicable ADR/lead review.

## Proposed control-to-evidence matrix

Criterion mappings are candidate crosswalks for CPA review, not assurance conclusions. Accountable roles below must be assigned to named people before the observation period starts.

| Control area / candidate criteria | Accountable owner | Evidence and proposed cadence | Acceptance sample |
| --- | --- | --- | --- |
| Governance, risk, accountability / CC1, CC3, CC5 | Executive sponsor and security lead | Approved scope, risk register, policy ownership, annual/risk-triggered review, tracked exceptions | Auditor can trace one risk to owner, implemented control, test, and approved residual risk. |
| Personnel and endpoints / CC1.4, CC6 | People operations and IT owner | Joiner/mover/leaver approvals; role-based training; confidentiality terms; lawful screening; managed-device encryption, patching, EDR/posture and inventory; onboarding/offboarding and periodic reviews | Terminated user loses IdP, GitHub, cloud and recovery access within approved policy; independently sampled device meets baseline. |
| Identity and privileged access / CC6.1–CC6.3 | IT/cloud owner | MFA/SSO configuration; production and archive role inventory; time-limited auditor access; periodic access recertification; break-glass tests | Read-only auditor cannot write; scan writer cannot delete/read arbitrary evidence; access revocation and emergency access are logged. |
| Change management / CC8.1 | Engineering lead | Protected-branch settings, required-check snapshots, reviewer approvals, deployment/release digest and rollback records; every release | Sample deployed digest resolves to approved commit and complete checks; an administrator bypass appears in review evidence. |
| Vulnerability management / CC7.1–CC7.3 | Security lead and package owners | Complete scan inventory per push/PR/release and scheduled advisory refresh; triage, exceptions, fix verification; weekly human queue review | Missing/failed scans are visible; sampled finding has owner, risk, deadline, decision and verified remediation or current approved exception. |
| Detection and incident response / CC7.2–CC7.5 | Incident commander | Monitoring configuration, alerts, incident timeline, exercises and corrective actions; per incident and scheduled exercise | Exercise demonstrates alert routing, escalation, containment and follow-up; retained record matches approved policy. |
| Vendor and business continuity / CC9, A1 if selected | Vendor owner and operations lead | Provider inventory/data flows, due diligence, contractual terms, current reports/bridge coverage, complementary controls; annual/material change; restore tests | Railway, Supabase, GitHub and relevant inference/data vendors have reviewed evidence; restore and unavailable-vendor scenarios have recorded outcomes. |
| Information handling / CC6, C1, P-series if selected | Data/legal owner | Classification, retention/deletion matrix, legal-hold approvals, key lifecycle, license constraints; annual/change-driven | Sample evidence can be read throughout retention and expires only after hold/review checks; sensitive exports are access-controlled. |

## Evidence production and trust boundary

Proposed flow: **unprivileged scans → temporary CI artifacts → protected collector → immutable evidence objects → signed manifest and archive receipt → human review**. Keep the evidence store separate from customer filing/model data and ordinary CI caches.

1. Run each expected scanner independently, preserve its true exit code, stdout/stderr and structured report, and always emit a status envelope. The canonical statuses are `clean`, `findings`, `failed`, `incomplete`, as defined in [Security CI](security-ci.md). Preserve `skipped`, `cancelled`, collector-detected `missing` and `upstream_failed` as separate reason codes plus native job states; never map them to clean. Record start/end times, timeout, scope and exclusions. Upload after findings/errors; redact secrets at source, especially Gitleaks matches.
2. Define the expected scanner/scope matrix in trusted configuration, including the three Python lockfile scopes separately. Reconcile GitHub run/job/attempt metadata against every expected result after completion and on a daily catch-up schedule. This catches cancelled jobs, an unavailable collector, missing uploads and entire missed scheduled runs; alert on archive lag. A green individual scanner does not make an incomplete run complete.
3. Treat PR code, scanner outputs, filenames, report text and archives as hostile data. PR jobs receive no archive credentials, no signing capability, and no cloud OIDC authorization. Never execute PR checkout, hooks, downloaded tools, artifact scripts, or PR-supplied configuration in the privileged collector; do not reuse PR caches [S6, S7].
4. A proposed `workflow_run: completed` collector runs trusted default-branch code pinned to a known revision. Validate repository numeric ID, allowlisted upstream workflow ID/path, run ID, attempt, event, head/base SHAs, artifact association, size and schema against GitHub API metadata. GitHub warns that `workflow_run` can have secrets/write tokens even when its predecessor did not [S7]. Branch-name filtering alone is insufficient. Parse bounded data in isolation, reject path traversal/symlinks/archive bombs, escape rendered content and quarantine malformed reports.
5. Authenticate the collector to a future archive with short-lived OIDC credentials under a provider-specific trust design. The objective is restriction to repository identity, collector workflow, protected ref/environment and audience; do not assume every cloud can evaluate every GitHub claim. For AWS, an environment-based default `sub` differs from the branch-based subject and does not independently bind workflow or branch. PRO-20 must demonstrate a supported subject customization or broker plus protected environment/ref controls, handle subject migration, and test same-repo wrong-workflow, wrong-ref/environment and wrong-audience denial. Give only the collector job `id-token: write` and minimal read permissions; use a separate scoped check-publisher capability where needed. Restrict trust to the collector, not merely upstream PR metadata [S8]. Pin actions to reviewed commit SHAs [S6].
6. A signed collection record proves what the collector received and bound to GitHub metadata; it does not prove PR-controlled scan execution was honest. Mark PR evidence `untrusted_pr`; rerun scans under trusted instructions against the exact release commit before promotion. Run untrusted source in a separate unprivileged job without archive/signing access.
7. Preserve raw reports, normalized findings, input inventories/lockfiles and hashes, tool/config versions, exact action SHAs, runner/runtime image identifiers when available, exclusions, allowlist snapshot, advisory source metadata, and obtainable advisory responses/database snapshots. Re-evaluating saved advisory bytes can reproduce historical decisions; a live registry query cannot promise identical findings later. Record `snapshot_unavailable` with reason where a service supplies no reproducible snapshot. Keep later corrected/withdrawn advisories as new records.

The upstream run finishes before this collector starts. Its local gate cannot
wait for the downstream receipt. The collector publishes a separate required
commit-bound evidence check; release promotion verifies that check and the exact
run/attempt receipts. [Security CI](security-ci.md) defines the check-SHA binding,
timeouts and cancellation behavior. PRO-20 owns real archive identity/provisioning
and permission proof; local receipts cannot satisfy hosted acceptance.

## Archive design and permissions

S3 Object Lock is an evaluated **candidate**, not the approved FEL storage architecture. Any AWS/S3/KMS or alternate WORM service addition requires a later ADR, cost/operational comparison and provisioning package under ADR-0002. Existing Supabase Storage use does not establish WORM equivalence.

Use versioning plus a WORM retention mechanism, encryption in transit, SSE-KMS or evaluated equivalent, blocked public access and organization-owned accounts. Versioning alone permits privileged deletion; an application “append-only” flag is insufficient. In S3, Object Lock protects **object versions**. Governance retention is bypassable with special permission; compliance retention cannot be shortened or bypassed by normal account users, including root [S9]. Assess operational/legal deletion needs before compliance-mode locks.

| Principal | Minimum proposed capability | Explicitly excluded |
| --- | --- | --- |
| Collector writer | Create unique object keys in its evidence prefix; encrypt/generate data keys; read back narrow object metadata/retention to verify writes | Delete versions, governance bypass, shorten retention, change bucket/key policy, disable/delete keys, arbitrary object reads |
| Authorized reviewer/auditor | Time-limited scoped list, `GetObjectVersion`, required retention metadata and narrowly scoped decrypt; access logged | Write/delete, change holds/retention, assume writer/admin role |
| Retention/security administrator | Separate approved configuration and retention-extension/legal-hold workflow; dual review for destructive capability | Routine scanner execution, uncontrolled combined writer/key-admin access |

Record the exact object key **and version ID**, content SHA-256, bytes, encryption-key identifier, retention mode and `retain_until`; never depend on a mutable `latest` object. Verify these fields after upload and in periodic inventory/readback tests. Object Lock does not stop loss of access to a deleted KMS key [S10]. Keep decrypt capability and underlying key material through the longest object retention/legal hold plus recovery margin; prohibit unreviewed disable/deletion, alert on attempts, and test reads after rotation. Key rotation must preserve old decrypt capability. Retain verification certificates/bundles and trust-policy versions too.

A retention schedule must cover raw reports, normalized data, review decisions, manifests, signatures, receipts, access logs and advisory snapshots. Start retention from a specified event, account for litigation holds and license/privacy constraints, and test recoverability before enabling irreversible production retention. CI artifact expiry is a short transport window, not the evidence policy; catch-up export must occur before it expires.

## Proposed evidence contract

These are proposed internal artifact schemas, not additions to `packages/contracts/` in this issue. `manifest-v1.schema.json` should reject unknown properties, require UTC RFC3339 timestamps, numeric GitHub IDs serialized as decimal strings, full 40-hex Git SHAs, lowercase 64-hex SHA-256 digests, nonnegative counts/byte sizes, and bounded strings/arrays. Use JSON `null` with a required explanatory reason for unavailable data; do not encode unknown as zero.

The example is synthetic, showing one failing JS scan; production `scans` must contain every configured scanner/scope. Object metadata values are illustrative, not a provisioned bucket or a real finding.

```json
{
  "schema_version": "fel.security-evidence/v1",
  "evidence_id": "repo-1/run-100/attempt-1",
  "collected_at": "2026-11-14T10:03:00Z",
  "repository": {"id": "1", "name": "wilsonhj/Agentic-Financial-Evidence-Lab"},
  "run": {
    "id": "100", "attempt": 1, "workflow_id": "10",
    "workflow_path": ".github/workflows/ci.yml", "event": "push",
    "ref": "refs/heads/main", "pull_request": null, "pull_request_reason": "push event",
    "head_sha": "33c6a635c05460624c894d00363d8710a780adc3",
    "base_sha": null, "base_sha_reason": "push event",
    "conclusion": "failure", "trust": "trusted_release_candidate"
  },
  "collector": {
    "workflow_path": ".github/workflows/security-evidence.yml",
    "revision": "33c6a635c05460624c894d00363d8710a780adc3",
    "policy_version": "proposed-1"
  },
  "coverage": {"expected": 1, "received": 1, "complete": true},
  "scans": [{
    "id": "js-dependencies", "job_id": "200", "upstream_artifact_id": "300", "status": "findings", "reason": null,
    "started_at": "2026-11-14T10:00:00Z", "ended_at": "2026-11-14T10:01:00Z",
    "tool": {"name": "audit-bulk", "version": "git:33c6a635c05460624c894d00363d8710a780adc3"},
    "command": ["node", "scripts/audit-bulk.mjs"], "exit_code": 1,
    "scope": ["pnpm-lock.yaml"], "exclusions": [],
    "input_object_ids": ["inputs"], "config_object_ids": ["policy"],
    "advisory": {"source": "npm-bulk", "snapshot_object_id": "raw"},
    "counts": {"findings": 1, "suppressed": 0},
    "raw_object_id": "raw", "normalized_object_id": "normalized"
  }],
  "objects": [
    {"id": "inputs", "key": "runs/100/1/inputs.tar", "version_id": "v1",
     "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bytes": 1234},
    {"id": "policy", "key": "runs/100/1/policy.json", "version_id": "v2",
     "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "bytes": 234},
    {"id": "raw", "key": "runs/100/1/raw.json", "version_id": "v3",
     "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "bytes": 345},
    {"id": "normalized", "key": "runs/100/1/findings.json", "version_id": "v4",
     "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "bytes": 456}
  ],
  "storage": {"provider": "candidate-s3", "encryption": "SSE-KMS",
    "key_id": "illustrative-key-id", "retention_policy": "pending-approval",
    "mode": "GOVERNANCE", "retain_until": "2027-11-14T10:03:00Z"}
}
```

The illustrative one-year lock is not a retention recommendation or an exception to §17.2. The collector must verify every object's actual encryption and retention matches the manifest's declared storage policy. `complete=true` means all expected envelopes arrived; gate pass additionally requires allowed scan states, coverage and exception policy. A missing report gets a synthesized envelope with `status=incomplete`, `reason=missing`, `exit_code=null` and null counts; never a fabricated empty report. Adapters normalize native statuses into this shared enum before schema validation.

`finding-v1.schema.json` should require `finding_id`, `scan_id`, source-native ID, `aliases[]` (CVE/GHSA/PYSEC/OSV when supplied), ecosystem/name/version or purl, dependency path/scope, affected/fixed ranges, severity source/vector, advisory published/modified/withdrawn times when available, `first_seen`, `last_seen`, and report location. Normalize only documented alias equivalence; retain native IDs and raw evidence. Deduplicate by alias group **and affected component/version/scope**, preserving cross-scan observations; unrelated IDs must not merge [S12]. Static/secret findings use rule ID and redacted file/line fingerprint instead of an invented CVE.

`review-v1.schema.json` is an append-only sequence requiring finding IDs, named owner/reviewer, timestamp, risk/exposure/reachability rationale, decision (`open`, `false_positive`, `risk_accepted`, `fixed`), due date, ticket, exception approver/expiry/compensating controls when relevant, and fix commit/release/rescan evidence. Unknown severity/exposure requires triage, not automatic acceptance. Later corrections reference the superseded record without overwriting it.

Hash exact manifest bytes; sign them with a detached identity-bound attestation and verify the approved signer/workflow/repository/ref and artifact digest [S11]. Hashes alone do not establish origin. Keep `manifest.json`, detached `manifest.sigstore.json` (or evaluated equivalent) and a signed `archive-receipt.json` binding their storage keys/version IDs, digests, verified lock metadata, collector identity and time. Avoid self-referential manifest hashes; the detached receipt records the manifest's own archive metadata. Audit export verification must fail on wrong signer, changed bytes, absent object, wrong version or insufficient retention. An attestation proves provenance, not absence of vulnerabilities [S11].

## Human operation and proposed delivery packages

Security lead owns triage and weekly queue review; component owners remediate; an authorized risk owner approves exceptions independently of the implementer. Proposed starting SLA for risk-owner approval: active exploitation gets same-day containment/triage; other critical/high/medium findings receive remediation targets of 7/30/90 days after detection. These are **policy proposals, not SOC 2 deadlines**. Exposure, exploitability, data impact, vendor constraints and compensating controls can tighten targets; overdue findings escalate to the sponsor. Keep first detection, decision, approved extension and verified closure timestamps. Existing stricter release gates still apply.

The following are independently reviewable future issue packages, not canonical task-ledger entries or authorization to implement shared files.

| Package / proposed files | Dependency and boundary | Independently testable acceptance |
| --- | --- | --- |
| E1 — control scope/policies: `docs/security/soc2-scope.md`, `control-register.csv`, `evidence-retention.md`, `vulnerability-policy.md` | Named management/CPA/legal owners; management work can start independently | Scope and categories approved; named owners/cadence/sample population; observation period and retention/legal holds agreed; existing §17.2 preserved or changed through governance. |
| E2 — envelopes/normalization: `scripts/security/manifest-v1.schema.json`, `finding-v1.schema.json`, `review-v1.schema.json`, `collect.py`, `tests/test_collect.py` | E1 policy inputs; local synthetic fixtures only | Validate example, all statuses, independent lockfile scopes, aliases/withdrawals, expiry, secret redaction, malformed/oversized data and historical replay; missing/unknown cannot become clean pass. |
| E3 — scanner capture: `.github/workflows/ci.yml`, `advisories.yml`, `scripts/security/run_scans.py` | E2; shared-path lead review and authorized issue | Inject JS finding, registry outage, Python failure, skipped install and cancellation; all remaining feasible scans still execute, exit gates remain strict, raw/status artifacts survive and scheduled Python scopes match CI. |
| E4 — trusted collector: `.github/workflows/security-evidence.yml`, `scripts/security/reconcile.py`, `tests/test_reconcile.py` | E2; mocked archive adapter; shared-path approval | Hostile fork/PR artifact cannot obtain credentials or execute in collector; reject mismatched workflow/run/attempt/SHA and archive traversal; successful, failed, cancelled and missed runs reconcile; daily catch-up and lag alerts work. |
| E5 — storage/identity ADR and implementation: future `docs/decisions/ADR-NNNN-security-evidence-archive.md`, `infra/security-evidence/`, `scripts/security/verify_archive.py` | E1, E4; benchmark/cost comparison, accepted ADR and explicit provisioning scope first | In an authorized disposable account, writer/auditor denial tests, version-specific readback, no retention bypass, key-rotation readability, simulated key-disable alert, legal-hold and lifecycle tests; signed manifest/receipt export verifies offline and detects tampering. |
| E6 — operational pilot: `docs/runbooks/security-evidence.md`, `docs/security/readiness-review.md` | E1–E5; named owners and retained pilot population | Human samples clean runs, findings, false positives, expired exceptions and missing scans; trace each remediation to deployed fix/rescan; restore old encrypted evidence and record independent readiness review. CPA decides examination sufficiency. |

Start with E1–E2 and mock archive verification. No cloud provisioning, external messaging, compliance claim, policy adoption, or accepted-stack change is performed by this research.

## Sources and limitations

All URLs below were accessed **2026-11-14** using Tavily search/extraction. AICPA landing pages were readable; linked account-gated downloads were not accessed. Criterion-level mappings therefore need confirmation against the licensed/current engagement materials. CPA-firm articles are primary practitioner guidance, not substitutes for AICPA standards; retention and minimum-period statements are identified accordingly.

- **S1:** [AICPA — 2017 TSC, revised points of focus 2022](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022); [2018 Description Criteria, revised guidance 2022](https://www.aicpa-cima.com/resources/download/get-description-criteria-for-your-organizations-soc-2-r-report).
- **S2:** [AICPA — October 28, 2026 proposed SOC 2 criteria announcement](https://www.aicpa-cima.com/news/article/aicpa-proposes-update-of-soc-2-r-trust-services-criteria-to-enhance-the-relevance-usability-and-value-of-cpas-reports).
- **S3:** [Cherry Bekaert — SOC 2 examination timeline, explicit absence of AICPA minimum](https://www.cbh.com/insights/articles/soc-2-report-examination-timeline-tips).
- **S4:** [Linford & Company CPA — data retention policy and SOC 2](https://linfordco.com/blog/data-retention-policy-soc-2).
- **S5:** [SEC — retention of records relevant to audits/reviews, scope of seven-year rule](https://www.sec.gov/rules-regulations/2003/01/retention-records-relevant-audits-reviews).
- **S6:** [GitHub — secure use reference](https://docs.github.com/en/actions/reference/security/secure-use).
- **S7:** [GitHub — workflow events, `workflow_run` privilege warning](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#workflow_run).
- **S8:** [GitHub — OpenID Connect](https://docs.github.com/en/actions/concepts/security/openid-connect).
- **S9:** [AWS — Object Lock version retention and governance/compliance modes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).
- **S10:** [AWS — Object Lock considerations, permissions and encryption-key loss](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html).
- **S11:** [GitHub — artifact attestations, identity, verification and limitations](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
- **S12:** [OpenSSF — OSV schema, alias semantics and affected packages](https://ossf.github.io/osv-schema/).

## Related pages

- [Production-readiness research](README.md)
- [Research index](../README.md)
- [Testing guide](../../development/testing.md)
- [Accepted stack](../../decisions/ADR-0002-mvp-stack.md)

# Research report: operating Financial Evidence Lab in production

**Research date:** 2026-11-14. **Baseline:** `33c6a63`.
**Disposition:** proposed, subordinate to the [parent specification](../../../specs/001-financial-evidence-lab/spec.md).
This report covers seven owner questions and connects each to independently
testable implementation work. It does not attest to deployment or compliance.

| Question | Conclusion | Detailed evidence |
| --- | --- | --- |
| How to make the service production grade? | Complete the scoped user journey and prove security, financial integrity, failure recovery, observability and release repeatability in the deployed environment | This report; [verification plan](verification-plan.md) |
| How to obtain SOC 2 Type II assurance? | Define the operating service and control owners, implement controls, collect evidence over an agreed period, and engage an independent CPA firm | [SOC 2 research](soc2-and-evidence.md) |
| How to scan for CVEs in CI? | Extend existing locked-dependency scans, independently scan the final runtime images, and require complete results before release | [Security CI](security-ci.md) |
| How to retain scans? | Preserve success, finding and error records with provenance, remediation and retention controls in an independently protected archive | [Evidence design](soc2-and-evidence.md) |
| How to scale horizontally? | Externalize blobs and quota state, budget database connections, and preserve replay/idempotency across replicas | [Scaling](containers-and-scaling.md) |
| How to make logs useful to developers? | Use a versioned JSON envelope, stable event names, human-readable messages, correlation and safe error classification; offer local pretty rendering | [Logging](structured-logging.md) |
| How to containerize? | Build locked, non-root web/Python runtime artifacts, isolate migrations and promote the exact verified digest | [Container design](containers-and-scaling.md) |

**Verified foundations and gaps**

Source inspection, rather than a hosted audit, established the following.

| Existing foundation | Remaining gap | Source at baseline |
| --- | --- | --- |
| JS lockfile advisory scanner; Python audits of runtime/dev/build locks | Scheduled Python scans use mutable requirement manifests; earlier failures can skip later scans; structured scan evidence is not archived | [CI](../../../.github/workflows/ci.yml), [advisories](../../../.github/workflows/advisories.yml), [audit runner](../../../scripts/audit-bulk.mjs) |
| Gitleaks, Bandit, type checks and extensive tests | Coverage of dependency CVEs does not establish absence of application vulnerabilities or deployed image vulnerabilities | [CI](../../../.github/workflows/ci.yml) |
| JSON API logging and Sentry integration | API/worker/web lack a consistent typed envelope and end-to-end correlation; interpolated worker JSON is unsafe | [Logging source inventory](structured-logging.md) |
| Reproducible Python installation | Production services currently build through Railpack; no exact scanned-image-to-deployment proof | [Runtime installer](../../../scripts/runtime/install.sh), [Railway configuration](../../../infra/railway/README.md) |
| PostgreSQL lease-fenced queue and API connection pools | Replica-wide connection budgets, provider quotas, storage and failure acceptance still need evidence | [Queue](../../../workers/src/fel_workers/queue.py), [pool](../../../apps/api/app/db.py) |
| Explicit live storage binding | Local directory blobs cannot serve independent API/worker replicas reliably | [Storage](../../../workers/src/fel_workers/storage.py) |
| Per-organization token bucket | State is process-local; replica count multiplies admitted traffic | [Rate limiter](../../../apps/api/app/ratelimit.py) |
| SQL migration, role and backup/restore CI | Disposable database restore does not prove hosted database-plus-object recovery or production role adoption | [Backup smoke](../../../infra/scripts/backup_restore_smoke.sh), [infrastructure](../../../infra/README.md) |
| Public-mode guards and worker provider-mode checks | Successful health checks do not prove production identity, live extraction, available evidence or complete product flows | [Railway operational notes](../../../infra/railway/README.md) |

Open changes for citation approval, evidence reads, verifier and publication
backfill were reviewed separately in PRs #413–#418. They are not part of this
baseline. Do not repeat or overwrite those packages; inspect their merged state
and release their file ownership before dispatching overlapping work. The
[earlier code review](../2026-11-13-repository-code-review.md) contains verified
findings and explicitly unverified leads; reproduce relevant leads before
treating them as accepted defects.

**Production boundaries**

Four boundaries need distinct controls and acceptance evidence:

- Authenticated web/REST: request-scoped identity, workspace membership,
  tenant isolation, private content and user-funded provider access.
- Anonymous MCP: separately enabled public evidence only, its dedicated
  read-only role/pool, strict cutoffs, bounded resource use, no tool-time
  model or network fetch. See [ADR-0034](../../decisions/ADR-0034-public-read-only-evidence-surface.md).
- Ingestion/extraction: untrusted upstream documents, least-privilege workers,
  external request budgets, durable jobs, provenance and human approval.
- CI/evidence: untrusted PR source, trusted release identity, short-lived
  publisher credentials and independently retained evidence.

Public MCP permission is not REST authorization. Security archive permissions
are not application object-storage permissions. Development diagnostic logs
are not immutable business audit events.

**Targets and retention**

Preserve the parent specification's existing performance profile and §19.6/§26
release gates. The accepted availability objective is 99.5% monthly with the
specified maintenance exclusion; at least 99% of asynchronous jobs must finish
or reach an actionable terminal failure within documented timeouts.
Performance testing uses the parent §16.1 reference workload, including
25 concurrent users and its larger reference corpus. The 20-issuer hosted MCP
pilot is a different workload and does not establish full MVP acceptance.

The parent §17.2 already specifies 365-day default query/model-run retention and
seven-year audit metadata/approved-lineage retention, subject to its lawful
policy exception. Do not replace these with a generic log-retention recommendation.
Classify security-scan evidence and diagnostic logs separately and have the
owner/auditor approve their policy. SOC 2 itself supplies no universal seven-year
CVE-report rule. Proposals such as shorter operational-log retention, stronger
availability targets or new recovery objectives require explicit decisions.

**Recommended sequence**

First resolve release-blocking integrity/security defects for the selected
product scope, define the control boundary and freeze minimal interfaces.
Then parallelize three independent engineering lanes: supply-chain evidence,
logging, and runtime packaging. Develop acceptance fixtures separately from
implementation. Introduce shared storage and admission control through existing
interfaces, followed by tightly owned runtime integration. Prove multi-replica,
restore, fault and release behavior before hosted acceptance.

The [parallel plan](parallel-work-packages.md) separates local implementation
from hosted prerequisites. Missing auditor scope, budget or cloud permissions
must not block offline scanner adapters, formatters, container builds or test
fixtures once their own contracts are accepted. Conversely, elapsed time or
completed code does not authorize a hosted deployment.

**Architecture decisions still owed**

| Decision | Evidence required before adoption |
| --- | --- |
| Production service scope, customer commitments and control owners | Product launch scope, data-flow diagram, access and vendor inventory |
| Security-evidence retention/archive provider | Classification against §17.2; legal/auditor needs; access model, cost, recovery and key-retention plan |
| SEC-08 publisher App identity and key custody | Named identity/owner, minimum permissions, protected key storage/rotation/recovery and expected-App branch binding; retain the hosted pre-ACK activation proof |
| Exact-image hosting/promotion mechanism | Demonstration that the selected deployment uses the verified digest without rebuilding |
| Shared quota implementation | Measured throughput/latency; correctness under replica concurrency and backend failure; existing-stack option evaluated first |
| Shared object-storage binding | Immutable concurrent-write semantics, role separation, compatibility and restore proof |
| New libraries or infrastructure | Scoped dependency authorization or accepted ADR, as applicable; benchmark evidence for a stack change |
| Recovery targets and on-call operation | Owner-selected RPO/RTO, provider capabilities, timed recovery and alert exercises |

Docker packaging is proposed as a reproducible build/deploy option; direct
local development remains available. Kubernetes, Redis, a new queue, Terraform
and full OpenTelemetry infrastructure are not default additions.
[ADR-0002](../../decisions/ADR-0002-mvp-stack.md) governs stack changes.

**External research method**

Topic researchers checked primary AICPA, GitHub, AWS, Docker, Next.js,
Railway, OWASP, Python, OpenTelemetry and scanner documentation. Each topic
lists direct URLs, access date, scope and limitations. Recommendations are
distinguished from platform facts. Version-sensitive commands must be checked
against the exact approved tool version at implementation time.

[NIST SP 800-218, SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final)
(accessed 2026-11-14) supports integrating secure-development practices through
the software lifecycle, including protection, verification and vulnerability
response. It is a supporting framework, not a substitute for a SOC examination.
See the [review record](review-record.md) for independent verification.

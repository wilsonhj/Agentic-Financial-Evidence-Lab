# Proposed production implementation specification

**Status:** external-review proposal for [#419](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/419).
**Parent:** [FEL specification](../../../specs/001-financial-evidence-lab/spec.md);
parent requirements and accepted ADRs govern conflicts.
**Baseline:** `33c6a63`, researched 2026-11-14.

Requirement IDs below identify this proposal, not canonical task completion.
Implementation begins only after the relevant decisions, issue registration,
path ownership and shared-path approvals described in the
[parallel plan](parallel-work-packages.md). No hosted work is implied.

**Scope and invariants**

- PROD-01: Name the enabled product surfaces, data classes, operators, vendors,
  deployment environments and control owners in a versioned system description.
  Distinguish authenticated REST/web from anonymous read-only MCP.
- PROD-02: Preserve financial Decimal computation, strict temporal visibility,
  tenant isolation, citation hashes, immutable approved history and corpus replay.
  Security/availability work must not relax parent release gates.
- PROD-03: Retain direct local development and fixture-only CI. Cloud access,
  live provider calls, paid resources and production retention activation are
  separately authorized acceptance steps.
- PROD-04: Every release must identify commit, immutable runtime artifacts,
  migration set, configuration version, required checks, approver and deployment
  receipt. Observed deployed digest must equal the approved scanned digest.
- PROD-05: Document and test coherent recovery of database, objects, corpus pins,
  roles, configuration and necessary key versions. Measure owner-approved RPO/RTO;
  a successful empty-database restore is insufficient.

**Control operation and evidence**

- SOC-01: Define examination boundary, control ownership, frequencies and evidence
  with an independent CPA firm. Type II operating-effectiveness evidence must
  cover the agreed period; code completion is not an attestation.
- SOC-02: Maintain risk/vendor inventories, access lifecycle and reviews, MFA,
  device security, training, incident response, change approvals, backup/restore
  and exception reviews. Record overdue and failed controls, not only successes.
- SOC-03: Classify diagnostic logs, security evidence, query/model data and business
  audit lineage separately. Preserve parent §17.2 retention. Approve retention,
  deletion, access and key lifetime before configuring irreversible locks.
- SOC-04: Review the evidence population for missing runs and inaccessible objects.
  Export immutable evidence receipts and remediation/retest records. An auditor
  must be able to select a sample independently of the implementation author.
- SOC-05: Preserve human accountability for code/security exceptions, production
  access and business approvals. Internal AI review is supplemental; it neither
  replaces an auditor nor satisfies a different-vendor review by itself.

**Vulnerability and software supply-chain controls**

- SEC-01: Scan exact JS and Python runtime, development and build dependency locks
  on PRs and protected-branch changes; schedule recurring scans against protected
  source and deployed artifact inventory.
- SEC-02: Scan the final runtime image by digest, including OS packages. Produce an
  SBOM and bind scan results and provenance to that digest. A source scan does not
  establish image safety; a signature alone does not establish vulnerability status.
- SEC-03: Keep SAST, dependency/image scanning, secret scanning and authorized
  dynamic testing distinct. Retain existing gates and expiring allowlist behavior.
- SEC-04: A failed scanner must not skip independent scanners. Represent at least
  `clean`, `findings`, `failed` and `incomplete`; preserve cancellation,
  skipped/missing runs and upstream failures as explicit reason codes plus native
  job states, following [Security CI](security-ci.md). Include explicit
  completeness and policy decision. Zero packages or a missing required report
  must not be accepted as clean without an approved expected-empty scope.
- SEC-05: Archive available outputs on success and failure, then enforce a final
  required gate. Release requires complete applicable reports and archive receipts.
  Alert independently when workflow cancellation or infrastructure failure prevents
  the normal collector from running.
- SEC-06: Use reviewed tool/action pins, read-only scan permissions and least-
  privilege short-lived publishing identity. Privileged collectors must not execute
  PR source, consume executable artifacts, trust PR-provided object destinations
  or promote untrusted findings to release attestations.
- SEC-07: Exceptions name exact advisory/package scope, reason, owner, approving
  authority, compensating controls and expiration. Keep original findings and
  rescans. Scanner/service errors are not vulnerability exceptions.

**Evidence interchange contract to freeze before coding**

The detailed [evidence design](soc2-and-evidence.md) supplies the proposed JSON
envelope. The following semantic fields are required even if names change during
review: schema version; repository identity; source and tested commit (including
PR merge-test SHA where applicable); workflow identity/ref; run ID and attempt;
trigger/trust class; scanner identity/version/configuration hash; target lockfile
hashes or image digest; start/finish time; advisory database snapshot or query time;
scan status/completeness; findings and aliases; exception/policy version; tool exit
status; report hashes; archive object versions; retention policy identifier.

The final schema owner must publish valid/invalid and malicious fixtures before
parallel consumers start. Receipts are produced by the trusted archive boundary;
a scanner cannot self-assert trusted archival. Canonicalization and signature
identity rules must be explicit. Never include credentials or customer content.
A checksum detects changed bytes but does not authenticate the producer.

**Developer-readable structured logging**

- LOG-01: Emit one valid UTF-8 JSON object per line in deployed application logs.
  Use UTC timestamps, stable schema/event names, severity, service, environment,
  release identity and a concise human-readable message.
- LOG-02: Propagate bounded validated request/trace IDs and durable job/run/attempt
  IDs through web, API and worker boundaries. Treat inbound correlation fields as
  untrusted; they are never authorization credentials. Reset context after async
  requests, errors and worker attempts.
  PRO-23 owns the accepted queue metadata, enqueue and claim propagation; new
  metadata must not silently alter financial input hashes or public job contracts.
- LOG-03: Use allowlisted structured attributes and safe error codes. Do not log
  bearer tokens, cookies, provider keys, DSNs, prompts, model responses, filing
  text, request bodies or sensitive URL query strings. Keep customer content out
  of exception stacks and third-party telemetry too.
- LOG-04: Bound event size, string lengths, collection depth and cardinality.
  Serialize embedded newlines; never interpolate untrusted text into JSON.
  On formatting/redaction failure emit a minimal safe diagnostic, not the raw input.
- LOG-05: Provide a local pretty renderer and examples of common debugging flows:
  request → queued job → attempt → provider call outcome → terminal result.
  Preserve raw JSON as the machine-readable source; pretty output is opt-in.
- LOG-06: Ordinary logging failures must not corrupt work or block indefinitely.
  Expose bounded drop/error counters and alert on sustained loss. Required business
  audit persistence retains its separate fail-closed transactional semantics.
- LOG-07: Freeze fields, event vocabulary, severity rules and privacy rules from
  [logging research](structured-logging.md), with Python/TypeScript parity fixtures.
  Existing Sentry/JSON support is the first implementation; full OTel infrastructure
  remains outside scope absent a separately accepted decision.

**Containers and release identity**

- IMG-01: Build one Python runtime image usable by API and explicit worker commands,
  a web runtime image, and a privileged migration invocation isolated from runtime.
  Preserve installed-package/resource checks and use locked build dependencies.
  Include the migration runner and required SQL files explicitly; first-party
  wheels do not imply these repository assets exist in the image. Run apply/check
  against an isolated fixture database from the final digest before approval.
- IMG-02: Use pinned base digests, multi-stage builds, a non-root numeric user,
  exec-form startup and an explicit writable-path list. Validate read-only-root
  operation where supported. Keep compiler/dev tools out of final runtime.
- IMG-03: Exclude secrets, local environments, tests not needed at runtime and
  unrelated workspace files from image contents. Build without hosted credentials;
  use scoped BuildKit secret mounts only if private dependency access requires them.
- IMG-04: Validate Next standalone output and workspace tracing from the final
  image, including static assets and shared-contract imports. Public build variables
  must be classified; private runtime secrets must never enter client bundles.
- IMG-05: Run migrations once per controlled release under a separate identity.
  Serialize competing releases, retain migration ledger checks, use compatible
  expand/contract changes and rehearse application rollback. Replicas never
  acquire migration credentials or independently migrate on startup.
- IMG-06: Verify the hosting platform can deploy the approved immutable artifact
  without rebuilding. Adding Dockerfiles alone must not change live Railpack
  services. If immutable promotion cannot be demonstrated, release remains blocked.

**Horizontal scaling and lifecycle**

- SCALE-01: Shared durable storage preserves content-addressed keys, atomic
  create-if-absent, identical-write idempotency and conflicting-byte rejection.
  Prove cross-replica access, authorization, coherent restore and migration of
  existing blobs before switching the production binding.
  PRO-10 must replace the API reader's local-file binding and verify extraction
  evidence reads that reuse it; changing the worker provider alone is insufficient.
- SCALE-02: Enforce organization/user/provider budgets and SEC request admission
  across every process, retry and overlapping deployment. Use atomic reservation
  and reconciliation for cost. Document a conservative failure policy; never
  silently fall back to independent full-capacity buckets.
- SCALE-03: Budget peak connections across API processes, worker handlers and
  heartbeats, migrations, monitoring and rolling overlap. Keep bounded pools and
  transaction-local tenant/role state, including error/rollback reuse tests.
- SCALE-04: Preserve at-least-once queue behavior and lease-fenced durable writes.
  Each external side effect defines an idempotency or reconciliation strategy;
  a lost lease does not undo a provider call.
- SCALE-05: Separate startup, readiness, process liveness and handler-progress
  deadlines. On termination stop new claims/admission, continue safe heartbeats,
  finish bounded work or abandon for recovery, then exit within measured grace.
  Avoid restart storms during dependency outages.
- SCALE-06: Persist stream events and resume on another replica using the existing
  authorized event cursor. Test ordering, duplicate handling and retention expiry.
  Signing-key rotation and shared cache keys must preserve tenant and evidence pins.
- SCALE-07: Benchmark one, two and overlapping replicas under fixed resource and
  workload definitions. Record bottlenecks and correctness before approving new
  infrastructure. Preserve parent SLOs; do not invent a capacity claim from CI fixtures.

**Decisions and completion gates**

The decision list in the [research report](research-report.md) must identify an
owner and accepted outcome for each applicable implementation package. No global
hosted blocker should unnecessarily block an independent offline package.

A package is complete only with its registered issue/branch, accepted input
contract, exact owned diff, appropriate regression/negative tests, sanitized
evidence, operational notes and independent review. Passing its tests does not
close a parent product gate. Hosted readiness additionally requires real identity,
storage, providers, cost accounting and the selected product's outstanding live
acceptance. SOC 2 readiness additionally requires operation of organizational
controls and the independent examination.

[Verification plan](verification-plan.md) maps these requirements to test
populations, fault cases and evidence. [Parallel work packages](parallel-work-packages.md)
define implementation and integration ownership.

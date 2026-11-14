# Verification and acceptance plan

**Status:** proposed for [#419](https://github.com/wilsonhj/Agentic-Financial-Evidence-Lab/issues/419).
Requirements: [implementation specification](implementation-spec.md).
Ownership and ordering: [parallel packages](parallel-work-packages.md).
The parent specification's existing quality and release gates remain authoritative.

**Levels of evidence**

| Level | What it proves | What it cannot prove |
| --- | --- | --- |
| Research/source review | A cited source/code path supports a statement at a named revision | Deployed behavior or compliance |
| Unit/contract fixtures | A bounded component obeys its accepted interface and negative cases | Real cloud permission, storage or platform behavior |
| Isolated integration | Components and immutable images interoperate on disposable data | Production identity, scale or recovery objectives |
| Authorized staging/hosted acceptance | Actual platform settings and observed behavior meet a scoped gate | Sustained operation throughout a SOC examination |
| Ongoing control evidence and CPA examination | Controls operated for the agreed scope/period, assessed independently | A universal guarantee that software is vulnerability-free |

Never promote a lower level to a higher-level claim. Every result records commit,
test/harness version, fixture IDs, image digests where applicable, environment
class, exact command, timestamp, observed result, skips and limitations.

**Independent fixture contract**

PRO-09 owns new `evals/production/**` acceptance harness files. It consumes
published CLI/HTTP/storage interfaces and artifact schemas; it must not import
producer implementation helpers to compute expected results. Keep oracle data
and expected failures independently specified. Component unit tests remain with
each producer. A harness bug is returned to the harness owner rather than patched
concurrently by multiple producers.

Use seeded fixture identities, no real credentials, no customer data and no live
provider requests. Give every test run an isolated project/database/object prefix.
Normal teardown preserves explicitly requested debugging evidence; destructive
reset/removal is a separate intentional command. All archived fixtures and logs
are checked for secret-like material before publication.

**Requirement-to-evidence matrix**

| Requirements | Independent acceptance | Owner / evidence |
| --- | --- | --- |
| PROD-01/02, SOC-01/02/05 | System-boundary review; sample control owner, access/offboarding, vendor and exception workflow; confirm separate MCP/public and tenant REST permissions | PRO-18/19; control matrix and signed review |
| PROD-03/04, IMG-05/06 | Fail missing authorization; reject rebuilt/mismatched digest and wrong signer; verify migration identity cannot reach runtime process | PRO-14/19; release manifest, negative results and deployment receipt |
| PROD-05, SOC-03/04 | Restore DB+objects+necessary key/config/role state into isolated target; verify retained pins, hashes and citations; reconcile expected evidence population | PRO-16/19; timed restore and gap report |
| SEC-01/02/03 | Check all locks, languages, runtime image platforms and deployed/rollback inventory; distinguish SAST/secrets/dependency/image results | PRO-01/09/13; complete target inventory and reports |
| SEC-04/05/07 | Inject malformed, missing, cancelled, stale, zero-scope and expired-exception cases; demonstrate failing final check while retaining outputs | PRO-09/13; expected-failure transcript and receipt |
| SEC-06 | Deny fork/unauthorized OIDC and overwrite/delete; reject forged artifact provenance and hostile archive contents; collector never executes artifact code | PRO-02/20; local threat fixtures plus separately authorized permission proof |
| LOG-01/04/05/07 | Parse every log line as JSON; check schema/limits, Python/TS fixtures and human event explanations; pretty renderer preserves identifiers | PRO-03/04/09; parity/redaction/golden tests |
| LOG-02/03/06 | Concurrent mixed-tenant requests/jobs, durable enqueue/claim metadata, cancellation, retries and logging outage; no context or secret leakage; audit-write failure retains its separate behavior | PRO-23/10/11/12/15; sanitized trace and fault results |
| IMG-01/02/03/04 | Final-image imports/assets/resources; non-root, explicit writable paths and PID1; inspect layers/build arguments/bundles for forbidden content | PRO-05/06/09; image inspect/SBOM/smoke artifacts |
| SCALE-01 | Two-client object races, checksum tamper, migration verification, authorization denial and cross-replica reads | PRO-07/16; storage invariant report |
| SCALE-02/03 | Race quotas/cost reservations across replicas and overlap; coordinator outage; connection saturation and tenant rollback/reuse | PRO-08/10/11/15; invariants, metrics and connection budget |
| SCALE-04/05/06/07 | Kill/reclaim/drain, duplicate side effect and stale lease; stream/cursor replay and rotation; one/two/overlap benchmark | PRO-11/15; reproducible fixture results and limits |

PRO-19 reviews local and authorized archive evidence for pilot entry. PRO-21
must subsequently review PRO-17's actual hosted results before recommending
production promotion; a pre-pilot review cannot establish hosted behavior.

**Mandatory negative scenarios**

- Scanner A reports a vulnerability while scanner B crashes: both attempts and
  outcomes remain visible; the required gate fails. A lint failure cannot prevent
  the security scan population from being attempted.
- Artifact/collector outage: source job completes without claiming a durable
  receipt; the appropriate downstream evidence check remains pending/fails under
  its deadline. An independent monitor records runner loss or cancellation.
- Archived bytes/hash/commit/signer/run attempt mismatch: receipt verification
  fails. A PR-provided destination, traversal member, symlink, oversized archive
  or executable payload is rejected without executing artifact content.
- Secret canaries across header, URL, nested object, exception, logging format
  failure and Sentry event: no canary survives output. Quotes/newlines produce one
  valid JSON event, not forged lines. Overflow is counted and bounded.
- Two tenants reuse the same pooled connection after exception/cancellation:
  role, claims, request/job context and cached data remain isolated.
- Two replicas consume one quota and cost allowance: admission/reservation totals
  stay within the declared shared policy, including retries and rolling overlap.
- Worker dies after external side effect but before durable completion: replay
  respects the selected provider idempotency or reconciliation rule; no claim of
  exactly-once behavior without a demonstrated mechanism.
- Database becomes unavailable during a healthy process: readiness/alert behavior
  is explicit, no infinite retry storm, no forged completion and no leaked secret.
- Archived key version unavailable or object missing after restore: restoration
  fails the relevant gate rather than presenting partial evidence as complete.
- Image is rebuilt after scan or a mutable tag moves: reject promotion even if
  source SHA matches. Verify per-platform digest for a multi-platform artifact.

**Performance method**

Use the parent's §16.1 hardware/workload and SLO definitions for release claims.
Use smaller deterministic CI fixtures only as regression tests, clearly labeled.
Report offered load, completed operations, errors, p50/p95/p99, queue-age
distribution, connection occupancy/pool waits, memory/CPU, quota denials, provider
attempts and correctness. Compare one replica, two replicas, rolling overlap and
dependency failure at the same total resource budget where feasible. Record warmup,
duration, random seed, datasets and raw sanitized results. Successful requests
alone must not hide timeouts/errors from percentile interpretation.

Do not assume throughput doubles. A database or upstream quota can remain the
bottleneck. The acceptance goal is preserved correctness and bounded behavior;
a capacity recommendation requires measured demand and headroom.

**Recovery and operations**

Run recovery in an isolated target, not over a production database. Establish a
declared checkpoint and object inventory, restore to the selected time, verify
roles/migrations and fetch known citations under retained corpus pins. Include
missing/corrupt blobs, an unavailable old encryption/signing key, backup-job
failure and access-denied cases. Measure RPO and RTO against owner-approved values.

Exercise alert delivery, on-call acknowledgement, break-glass access and rollback
with named humans. Collect access/exception reviews and vendor/control evidence
according to the approved cadence. A monitoring dashboard screenshot alone does
not prove these actions occurred.

**Documentation/research validation for this PR**

Before publishing the final research revision:

1. Verify all seven questions map to requirements and independently owned packages.
2. Independently check high-impact external claims against primary sources and
   baseline code; distinguish source documentation from runtime proof.
3. Check package dependency graph is acyclic and all references resolve.
4. Check relative links, JSON examples, Markdown formatting and docs-index reachability.
5. Run `git diff --check`, confirm docs-only scope and record actual results in
   [review record](review-record.md).
6. Push the reviewed revision, verify remote head, inspect CI results and leave
   a draft PR with current limitations and exact next action for external review.

No application code changes are included, so a fresh application/load/hosted test
run is not claimed as research verification. Repository CI may run its normal
checks on the documentation PR; record those separately from local checks.

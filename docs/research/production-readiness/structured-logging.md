# Structured developer logging

Research for issue #419; inspected `main` at `33c6a63`; accessed 2026-11-14.
This is a proposal, not evidence of implementation or production readiness.

## Recommendation and repository evidence

Keep Python stdlib logging and a small server-only TypeScript JSON writer.
Define one versioned event envelope and typed event catalogue before changing
call sites. Production emits JSON Lines; local development may render the same
sanitized event as readable text. No new collector, logging vendor, or full
OpenTelemetry installation is needed: [ADR-0002](../../decisions/ADR-0002-mvp-stack.md)
already selects Sentry plus structured JSON logs and defers full OpenTelemetry.
Use its data model as a vocabulary and future mapping target, not a stack change.[S2]

Observed behavior at the inspected commit:

| Area | Existing implementation | Production gap |
| --- | --- | --- |
| API | [`observability.py`](../../../apps/api/app/observability.py): `json.dumps`, root stderr handler, request timing, request ID, append-only audit writer | `formatTime` lacks explicit UTC offset; arbitrary incoming request ID; no common event code, version, environment, or async context; formatter ignores `exc_info` |
| Workers | [`__main__.py`](../../../workers/src/fel_workers/__main__.py): `basicConfig` with a JSON-shaped interpolation format | Quotes/newlines in messages can break JSON; default exception formatting can add separate lines |
| Job failures | [`consumer.py`](../../../workers/src/fel_workers/consumer.py): `log.exception`; [`queue.py`](../../../workers/src/fel_workers/queue.py): sanitized durable error envelopes | Free-form exception paths need one explicit reporting owner; queue error request ID is job ID, not originating request context |
| Extraction | [`telemetry.py`](../../../workers/src/fel_workers/extraction/telemetry.py): redacted dictionary passed to `%s` | Python dictionary representation embedded in `msg`, rather than queryable event fields |
| Calculation | [`telemetry.py`](../../../packages/calculation-engine/fel_calculation_engine/telemetry.py): injectable sink and recursive redaction | Same string embedding; key-based masking does not make arbitrary values safe |
| Web | [`route.ts`](../../../apps/web/src/app/api/telemetry/route.ts): JSON encoding after [`telemetry-validation.ts`](../../../apps/web/src/lib/telemetry-validation.ts) | Existing event/attribute allowlists, 50-event batch limit, and timing bounds are useful; common service/time/context fields are absent |
| Errors | API and worker optional Sentry initialization disable default PII, frame locals, request bodies | Those flags alone do not remove sensitive exception messages, URLs, extras, or breadcrumbs; no explicit final event allowlist is configured |

The web package pins Next.js 16.4.2; root Node requirement is 24.x; API and worker
declare Python >=3.11. Next.js development request/fetch logging is not the
production event pipeline.[S5] Consult runtime-specific docs, not newest-only APIs.

## Proposed event contract

Serialize one object with a JSON library followed by exactly one LF. Never
construct JSON with interpolation, merge arbitrary `extra`, or serialize objects
using `repr`, `str`, `default=str`, `Error.stack`, or a request dump. Event definitions
own both the approved message template and attribute types. Unknown fields fail
tests and are dropped at runtime with a bounded safe diagnostic.[S1]

| Field | Requirement and meaning |
| --- | --- |
| `schema_version` | Required integer `1`; schema changes require compatibility review |
| `timestamp` | Required server event time, RFC 3339 UTC with milliseconds and `Z` |
| `severity` | Required enum `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`; normalize Python `WARNING`/`CRITICAL` |
| `event_code` | Required stable catalogue key, e.g. `job.attempt.failed`; never derive from user text |
| `message` | Required short human explanation from the catalogue; no arbitrary interpolation |
| `service` | Required `fel-api`, `fel-worker`, or `fel-web` from trusted process configuration |
| `environment` | Required controlled deployment name; never infer from incoming headers |
| `version` | Required build release identifier/commit, injected at build/deploy; no secret-bearing image URL |
| `request_id` | Optional bounded opaque identifier generated or accepted at the trusted ingress boundary |
| `trace_id`, `span_id` | Optional validated W3C identifiers: 32/16 lowercase hex, nonzero; span requires trace |
| `trace_sampled` | Optional boolean matching the accepted trace context; not a severity or log sampling switch |
| `job_id`, `attempt` | Required for job events: validated opaque ID and positive claimed attempt integer |
| `tenant_pseudonym`, `pseudonym_key_id` | Present only after authenticated tenant resolution; keyed pseudonym and key version |
| `duration_ms` | Optional finite nonnegative number from monotonic elapsed time, never wall-clock subtraction |
| `error_code` | Required on failure events; bounded catalogue value, e.g. `UPSTREAM_TIMEOUT` |
| `attributes` | Optional closed per-event object: route template, HTTP status, stage, counts, retryability |
| `exception` | Optional safe type and sanitized bounded frame metadata; no original exception message/locals |

Illustrative single physical log line; all identifiers are synthetic:

```json
{"schema_version":1,"timestamp":"2026-11-14T12:34:56.789Z","severity":"WARN","event_code":"job.attempt.failed","message":"Job attempt failed; retry scheduled.","service":"fel-worker","environment":"production","version":"33c6a63","request_id":"req-a7e8b9c0d1e2","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","trace_sampled":false,"job_id":"9f99d541-8192-4c74-8416-07c2bb868489","attempt":2,"tenant_pseudonym":"tp_k3_4e9b6614c8bc75cb29aec38f76afe021","pseudonym_key_id":"k3","duration_ms":1200.5,"error_code":"UPSTREAM_TIMEOUT","attributes":{"stage":"filing_fetch","retryable":true}}
```

Map event time to OTel `Timestamp`, severity to `SeverityText`/`SeverityNumber`,
message to `Body`, event code to `EventName`, service/version/environment to
resource attributes, and correlation IDs to the dedicated trace fields.[S2]
This JSON is an FEL envelope, not an assertion of OTLP wire compatibility.

Catalogue initial events: `service.started`, `service.stopping`,
`http.request.completed`, `http.request.failed`, `job.attempt.started`,
`job.attempt.completed`, `job.attempt.failed`, `job.lease.lost`,
`security.access.denied`, and `telemetry.event.rejected`.
INFO records normal lifecycle; WARN records retryable degradation; ERROR records
terminal or unexpected failure; FATAL is reserved for process inability to run.
One terminal request outcome includes duration and status, including handled
errors; distinguish response completion from SSE connection-open timing.

## Context and cross-process correlation

1. At public ingress generate a cryptographically random request ID. Accept an
   incoming `X-Request-ID` only from an explicitly trusted proxy that removes
   client-supplied copies, with ASCII syntax and a 64-character ceiling. Return
   the accepted/generated ID in the response; it grants no authorization.
2. Bind a fresh immutable Python context with `ContextVar.set`, and reset the
   returned token in `finally`, including cancellation, streaming disconnect,
   exception, and worker retry paths.[S3] Resolve tenant identity from verified
   auth/database state; never bind an unverified header or job payload tenant.
3. Use pure ASGI request lifetime binding, or prove existing middleware's task
   and streaming semantics with tests. Child tasks inherit context: explicitly
   start detached work with a fresh context and pass only intended correlation
   fields. For thread/heartbeat work copy only an approved immutable snapshot;
   never share a mutable context dictionary between tenants.
4. In Node server code use `AsyncLocalStorage.run(frozenContext, callback)`;
   avoid global mutable request state and `enterWith` scope leakage.[S4]
   Browser events remain untrusted measurements: the ingest server assigns its
   own envelope and does not accept browser tenant/service/version assertions.
5. In-process context does not cross HTTP, process, queue, or restart boundaries.
   Propagate only validated correlation metadata through an explicit internal
   HTTP adapter and approved queue metadata. Keep origin request ID separate
   from job ID; bind fresh job scope for each claimed attempt, then reset it.
   Use `ClaimedJob.org_id`, checked against payload identity, for the tenant.

W3C `traceparent` is correlation metadata, never a trust or tenant identity
signal. Parse the specification's supported version, length, nonzero IDs, flags,
and invalid-header behavior; do not rely on a permissive regular expression.[S6]
At an untrusted external boundary start a new internal trace; trusted proxy or
service callers may continue validated context. Carry fresh child span IDs at
actual service/attempt boundaries, not fabricated exporter claims. Preserve the
accepted sampled flag through internal calls; a service may make a documented
boundary sampling decision, and client `sampled=1` must not force expensive work.
With performance tracing disabled, new internal roots use sampled=false.
Never use trace sampling to suppress errors or durable audit events.
Do not forward `baggage` or `tracestate` by default, and never send internal
context to arbitrary provider origins. An approved queue metadata change must
include enqueue/claim tests and contract review; until then record job/request
correlation only where the existing committed interface supports it.

## Privacy, safety, and operational delivery

Use an allowlist before encoding, with key/value scrubbing only as defense in
depth. Exclude Authorization/Cookie headers, JWTs, API/BYOK keys, database or
Sentry DSNs, connection URLs, request/response bodies, query strings, raw paths
with identifiers, SQL/bind parameters, filing text, financial values, search
queries, prompts, model outputs, document labels, emails, user IDs and IPs.[S1]
Logging a truncated secret or filing passage still leaks it. Keep safe route
templates and error codes; do not fall back to the original rejected value.

Derive tenant pseudonyms using HMAC-SHA-256 over a domain-separated canonical
tenant ID with an environment-specific secret, retaining 128 bits. An unkeyed
hash of enumerable IDs is insufficient. Store keys only in approved secret
management, publish only nonsecret key IDs, rotate on a documented schedule or
incident, and restrict old keys to the retention/deletion investigation window.
Rotation deliberately breaks ordinary cross-period correlation; any re-linking
requires restricted access. These are still sensitive pseudonymous records.

Map exceptions to reviewed error codes and safe messages at the owning boundary.
An allowlisted exception type plus repository-relative file/function/line frames
can explain failures without exception `str`, source snippets, locals, causes'
messages, absolute paths, or provider response text. Bound chains and frames.
Unknown exceptions use `INTERNAL`; preserve useful sanitized frames for operators.
Sanitize before both JSON and local pretty rendering; escape terminal controls.
JSON encoding escapes CR/LF/quotes; reject unsafe attribute keys and remove other
control characters so untrusted input cannot forge log entries.[S1]

Proposed initial bounds: 16 KiB UTF-8 per event, message <=256 characters,
attribute strings <=128 characters, <=16 attributes, no untyped nested objects,
and <=20 safe exception frames. Measure encoded bytes; do not truncate an
already encoded JSON line. Drop optional fields deterministically, set an
allowlisted `truncated` flag, and emit a minimal safe event if still oversized.
Never serialize cyclic/hostile objects or invoke their custom string methods.

Use stderr for all application severities across Python and Node, retaining
stdout for command results. Severity comes from the envelope, not the stream.
This preserves current Python handler behavior and avoids split-stream ordering
surprises. Verify the hosted collector parses severity correctly; do not assume
every stderr line means ERROR. Adapt Uvicorn/Next runtime logs separately and
avoid duplicate request access events. Libraries never configure root handlers.
Configuration must be idempotent under reload and initialize before accepting work.

Use bounded buffering when measured stream behavior needs it: Python bounded
`QueueHandler`/`QueueListener` and Node writable backpressure handling. Capture
context and sanitize before enqueueing, not in the listener's context.[S3][S4][S9]
Set a maximum pending-byte budget and bounded shutdown flush; avoid immediate
`process.exit()` before asynchronous writes finish. Node output can block or be
asynchronous depending on destination.[S7] Never await a remote logging backend
on the request path. On sink failure, preserve application behavior, count drops
without recursive logging, and expose one rate-limited safe diagnostic when
possible. Logs are best effort; monitoring must reveal loss.[S1]

Keep DEBUG off in production by default. Enable time-bounded, service-scoped
debugging with the same allowlist. Sample repetitive success/health events using
stable trace/request hashing; retain failures and security signals with bounded
aggregate counters for floods. Suggested operational retention is 14 days,
subject to a named owner confirming hosted capability, access controls, deletion,
cost, and incident needs; this is not an existing configured policy.
Append-only `audit_events` remain the transactional security/business record,
with their own reviewed payload, restricted access, integrity, and retention
policy. Developer logs neither replace audit writes nor inherit permission to
copy audit payloads. Audit failure follows transaction policy; debug sink failure
must not make an authorized business transaction fail.

Sentry remains optional when `FEL_SENTRY_DSN` is absent. Keep existing privacy
flags and add final `before_send`/breadcrumb filtering with the same allowlist;
strip request context, extras and exception text before any network transport.[S8]
Choose one capture owner per failure: framework integration for escaped API
exceptions, explicit capture for caught worker terminal failures. Avoid automatic
logging integration plus manual capture of the same exception; test one Sentry
event and one operational terminal log. Share safe error code/release/correlation
tags; keep expected retries as bounded breadcrumbs, not repeated error reports.

## Independently owned implementation slices and acceptance

Proposed slices require separate registered issues/branches before dispatch;
these are future file ownership boundaries, not edits authorized by this report.

| Slice | Exclusive paths and interface | Evidence before integration |
| --- | --- | --- |
| Envelope core | New `packages/observability/fel_observability/{events,context,formatting,privacy}.py`, `packages/observability/tests/**`, `packages/observability/fixtures/**` | Stdlib-only `emit(event_code, context, fields)`, `bind_context(...)`, safe JSON encoder; synthetic schema/catalogue fixtures |
| API adapter (PRO-10) | `apps/api/app/observability.py`, existing `apps/api/tests/test_observability.py`, new `apps/api/tests/test_structured_logging.py`, `apps/api/tests/fixtures/logging/**` | Inject core sink/context; auth-resolved tenant, route templates, failure/SSE outcomes, response request ID and real Sentry initialization/transport canary |
| Worker adapter | `workers/src/fel_workers/{__main__,consumer}.py`, new `workers/src/fel_workers/log_context.py`, `workers/tests/test_log_context.py`, `workers/tests/fixtures/logging/**` | Per-attempt bind/reset and lease outcomes; inject recording sink; no queue schema change |
| Web adapter (PRO-12) | `apps/web/src/app/api/telemetry/route.ts`, `apps/web/src/lib/telemetry-validation.ts`, named HTTP transports/server bindings and adapter tests in the integrated plan | Consume PRO-04's `lib/observability/**` core; bind server context and map bounded client events; no second logging core |
| Telemetry adapters (PRO-11 checkpoint) | `workers/src/fel_workers/extraction/telemetry.py`, new `workers/tests/extraction/test_telemetry.py`, `packages/calculation-engine/fel_calculation_engine/telemetry.py`, existing `packages/calculation-engine/tests/test_telemetry.py` | Preserve injectable sinks and existing redaction defense; replace dictionary-to-message rendering with typed catalogue fields without duplicating core configuration |

### Emitter migration inventory and integrated owners

These topic-local slices are checkpoints of the
[integrated 24-package plan](parallel-work-packages.md), not additional dispatches.
At the pinned baseline, a source search for Python logger calls identifies seven
application emitter files; the web telemetry route supplies the application console
writer. All require migration or a named reviewed safe legacy mapping:

| Baseline emitter/configuration | Integrated owner and required disposition |
| --- | --- |
| `apps/api/app/observability.py` | PRO-10: migrate `JsonLogFormatter`, `configure_logging()`, request middleware and warning path; filter Sentry through real `configure_error_reporting()`; preserve transactional `record_audit_event()` separately |
| `workers/src/fel_workers/__main__.py` | PRO-11: replace JSON-shaped `basicConfig`, lifecycle/configuration/error messages and Sentry initialization; no raw exception string fallback |
| `workers/src/fel_workers/consumer.py` | PRO-11: catalogue heartbeat/lease/run/failure outcomes, safe identifiers, per-attempt context and one capture owner |
| `workers/src/fel_workers/health.py` | PRO-11: map startup/watchdog/access messages; raw HTTP server format/arguments must not bypass route-template/attribute limits |
| `workers/src/fel_workers/storage.py` | PRO-11: migrate database-role diagnostic to approved catalogue fields; never serialize a connection/DSN |
| `workers/src/fel_workers/extraction/telemetry.py` | PRO-11: adapt actual `emit()` before `%s` rendering; unknown event/fields are rejected safely |
| `packages/calculation-engine/fel_calculation_engine/telemetry.py` | PRO-11: adapt actual `LoggingSink`/default path before `%s` rendering; retain injectable `TelemetrySink` and `RecordingSink` payload/event contract |
| `apps/web/src/app/api/telemetry/route.ts` and `apps/web/src/lib/telemetry-validation.ts` | PRO-12: retain client allowlists and bounds, then map to common server event envelope |
| Uvicorn/Next runtime and third-party logger output | PRO-10/11/12: inventory effective configured handlers at startup; explicitly map safe legacy events or drop unknown messages with bounded diagnostics; no arbitrary `record.getMessage()` passthrough |

Repeat source and configured-handler inventory against current main at registration;
assign every new emitter before acceptance. `http.py`/`ingestion/sec_client.py` and
web HTTP transports remain integration scope for correlation even where they do not
currently emit logs. A formatter cannot recover safe typed attributes after a
dictionary has become free-form text. Core-only acceptance therefore does not
complete the telemetry migration.

PRO-11's adapter tests call extraction `emit()` and calculation `emit(None, ...)`
and `LoggingSink.emit()` through the installed logger/handler, then parse captured
bytes. Assert catalogue `event_code`, typed/queryable attributes, request/job/attempt
context where applicable, exactly one JSON line and the encoded size limit. Inject
a synthetic secret under an unknown/renamed key, nested object, oversized string
and unknown event; no original value reaches JSON, pretty output or Sentry. Exercise
an engine evaluation with the default sink as well as the existing recording-sink
tests; keep injected recording events compatible without exposing arbitrary values
through the default log sink. Update terminal-run worker tests that currently inspect
rendered message strings to assert approved catalogue fields.

PRO-10 tests call the real `configure_logging()` and `configure_error_reporting()`
from `observability.py`, with an in-memory Sentry transport and synthetic DSN;
capture a canary exception including request/extras/breadcrumbs and inspect the final
transport envelope. Verify filtering, safe correlation tags, no duplicate capture,
no-DSN behavior and idempotent initialization. Direct calls to a privacy helper alone
do not satisfy this integration acceptance.

Core owns its synthetic golden JSONL and adversarial fixtures; adapters consume
a frozen fixture version through explicit interfaces, never edit another slice's
fixtures. Core and adapter work can be prepared against mocks independently;
adapter integration waits for the frozen envelope. Integration lead alone owns
root package/lock/CI registration, environment wiring, hosted retention evidence,
contracts/migrations, and any queue metadata or ADR amendment. Do not hide those
edits inside a logging adapter. No full OTel backend stack without an accepted ADR.

Acceptance must verify JSON schema and byte limits; quoted/newline/control input
and multiline exceptions each produce one parseable physical line; no original
secret appears under nested, mixed-case, renamed-key, array, exception, or DSN
fixtures; concurrent tenant requests, cancellation and sequential job attempts
cannot inherit another context; malformed/spoofed trace headers cannot assert
tenant identity or force sampling; event timestamps are UTC and durations monotonic;
reload does not duplicate handlers; blocked/failed sinks and full buffers remain
bounded without recursive errors or tenant-data fallback. Test Sentry transport
payloads as well as logger output, and verify audit behavior separately.
Hosted acceptance must ingest API/web/worker canaries, query by event/error code
and request/job ID, confirm no double Sentry captures, and prove retention/deletion.
Offline fixtures cannot establish hosted delivery or retention guarantees.

## Primary sources

All sources accessed 2026-11-14 via Tavily; extraction returned no failed URLs.
Recommendations and numeric limits above are FEL proposals, not quoted defaults.

[S1]: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html "OWASP: event attributes, exclusions, sanitization, verification and disposal"
[S2]: https://opentelemetry.io/docs/specs/otel/logs/data-model/ "OpenTelemetry Logs Data Model"
[S3]: https://docs.python.org/3.11/library/contextvars.html "Python 3.11 ContextVar reset and asyncio semantics"
[S4]: https://nodejs.org/docs/latest-v24.x/api/async_context.html "Node 24 AsyncLocalStorage run and enterWith"
[S5]: https://nextjs.org/docs/app/api-reference/config/next-config-js/logging "Next.js logging configuration and development-only behavior"
[S6]: https://www.w3.org/TR/trace-context/ "W3C Trace Context: processing, sampling, security and privacy"
[S7]: https://nodejs.org/docs/latest-v24.x/api/process.html#a-note-on-process-io "Node 24 process I/O blocking and asynchronous writes"
[S8]: https://docs.sentry.io/platforms/python/data-management/sensitive-data/ "Sentry Python sensitive data filtering"
[S9]: https://docs.python.org/3.11/howto/logging-cookbook.html#dealing-with-handlers-that-block "Python 3.11 QueueHandler and QueueListener"

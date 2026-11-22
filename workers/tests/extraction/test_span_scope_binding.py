"""A cited span must lie inside the run's own scope: cutoff, status, manifest, entity and corpus.

``_bind_evidence_to_spans`` verified that a span resolves, that its
``document_version_id`` matches the evidence block and that its ``text_hash``
matches the supplied text (#451, finding C2 of the 2026-11-13 code review). It
never compared the span with the run it was being cited by. The run row pins
``as_of``, ``entity_id``, ``corpus_version_id`` and ``input_manifest``, and
``load_run_pins`` reads all of them, but none reached span binding. The only
cutoff check downstream, in ``stages/assemble_evidence``, read ``published_at``
from the PAYLOAD, so a payload that omitted or understated it passed.

So a durable run could cite, with a perfectly valid hash:

- a span from a filing published (or made public per migration 0012's
  ``public_at`` rule) after the run's ``as_of`` (look-ahead);
- a span from a ``quarantined`` document version;
- a span absent from ``request.input_manifest["source_span_ids"]`` when pinned;
- a span from another issuer's filing;
- a span from a document version outside the run's pinned corpus (or in no corpus).

Each test below seeds one such span, real and hash-correct, and expects the
run to be refused before ``mark_running``: ``integrity_error``, the run still
``queued`` and no proposal persisted. Pure-Python unit tests at the bottom
exercise ``_bind_evidence_to_spans`` and ``_restore_output`` directly without
requiring a database.

DB tests run against the isolated ``<db>_extraction`` sibling for the reason
documented in ``test_postgres_crash_resume``.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from fel_providers.mocks import MockStructuredLLMProvider
from fel_workers.extraction.errors import CutoffViolation, ExtractionError, IntegrityError
from fel_workers.extraction.handler import (
    _bind_evidence_to_spans,
    handle_extraction_run,
    request_from_payload,
)
from fel_workers.extraction.hashing import sha256_hex
from fel_workers.extraction.persist_types import SpanPin
from fel_workers.extraction.types import WORKFLOW_VERSION, EvidenceBlock, WorkflowState
from fel_workers.extraction.workflow_codec import _restore_output

from .test_postgres_crash_resume import _CORPUS as _SEEDED_CORPUS
from .test_postgres_crash_resume import _ENTITY as _SEEDED_ENTITY
from .test_postgres_crash_resume import (
    _ORG,
    _POLICY,
    _USER,
    _WORKSPACE,
    LONG_SPAN_TEXT,
    _seed_parents,
    ensure_extraction_database,
)
from .test_run_binding import _AS_OF, _durable, _payload, _seed_run

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL not configured"
)

_OTHER_ENTITY = "00000000-0000-0000-0000-00000000d401"
_OTHER_CORPUS = "00000000-0000-0000-0000-00000000db01"

# Every out-of-scope span carries the SAME text as the seeded in-scope span, so
# its hash is correct and the existing checks all pass. Only scope differs.
_SPAN_HASH = sha256_hex(LONG_SPAN_TEXT)

# Inside the cutoff by a comfortable margin; the "late" case is a year past it.
_EARLY = datetime(2026, 6, 30, tzinfo=UTC)
_LATE = datetime(2027, 12, 31, tzinfo=UTC)
# Same-day publication after midnight UTC cutoff (_AS_OF): migration 0012 leak case.
_LATE_PUBLIC_AT = datetime(2026, 12, 31, 14, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def extraction_db_url() -> str:
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not configured")
    return ensure_extraction_database(TEST_DATABASE_URL)


def _seed_span(
    conn: psycopg.Connection[Any],
    tag: str,
    *,
    entity_id: str,
    published_at: datetime,
    corpus_version_id: str | None,
    public_at: datetime | None = None,
    document_version_status: str = "parsed",
) -> tuple[str, str]:
    """Seed one document -> version -> section -> span chain; return (span, version).

    Ids are derived from ``tag`` so reruns against the persistent sibling
    database are idempotent. ``corpus_version_id=None`` leaves the version out
    of every corpus.
    """
    ns = uuid.UUID("5c0be000-0000-4000-8000-000000000451")
    document = str(uuid.uuid5(ns, f"document|{tag}"))
    version = str(uuid.uuid5(ns, f"version|{tag}"))
    section = str(uuid.uuid5(ns, f"section|{tag}"))
    span = str(uuid.uuid5(ns, f"span|{tag}"))
    if public_at is None:
        doc_stmt: tuple[str, tuple[Any, ...]] = (
            "INSERT INTO documents (id, entity_id, accession, source_url,"
            " content_hash, storage_key, published_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                document,
                entity_id,
                f"span-scope-{tag}",
                f"https://example.test/span-scope-{tag}",
                sha256_hex(f"span-scope-doc|{tag}"),
                f"span-scope-{tag}",
                published_at,
            ),
        )
    else:
        doc_stmt = (
            "INSERT INTO documents (id, entity_id, accession, source_url,"
            " content_hash, storage_key, published_at, accepted_at, public_at,"
            " public_at_basis, timestamp_precision)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'acceptance', 'second')",
            (
                document,
                entity_id,
                f"span-scope-{tag}",
                f"https://example.test/span-scope-{tag}",
                sha256_hex(f"span-scope-doc|{tag}"),
                f"span-scope-{tag}",
                published_at,
                public_at,
                public_at,
            ),
        )
    statements: list[tuple[str, tuple[Any, ...]]] = [
        doc_stmt,
        (
            "INSERT INTO document_versions (id, document_id, parser_version,"
            " normalizer_version, status, canonical_text_key)"
            " VALUES (%s, %s, 'p1', 'n1', %s, %s)",
            (version, document, document_version_status, f"text/span-scope-{tag}"),
        ),
        (
            "INSERT INTO sections (id, document_version_id, heading, heading_path,"
            " ord, start_char, end_char) VALUES (%s, %s, 'One', ARRAY['One'], 0, 0, %s)",
            (section, version, len(LONG_SPAN_TEXT)),
        ),
        (
            "INSERT INTO source_spans (id, document_version_id, section_id,"
            " start_char, end_char, text_hash) VALUES (%s, %s, %s, 0, %s, %s)",
            (span, version, section, len(LONG_SPAN_TEXT), _SPAN_HASH),
        ),
    ]
    if corpus_version_id is not None:
        statements.append(
            (
                "INSERT INTO corpus_version_documents (corpus_version_id,"
                " document_version_id) VALUES (%s, %s)",
                (corpus_version_id, version),
            )
        )
    for sql, args in statements:
        conn.execute(f"{sql} ON CONFLICT DO NOTHING", args)
    return span, version


def _seed_run_with_manifest(
    conn: psycopg.Connection[Any], run_id: str, input_manifest: dict[str, Any]
) -> None:
    """Insert one queued ``extraction_runs`` row carrying a pinned ``input_manifest``."""
    conn.execute(
        """
        INSERT INTO extraction_runs (
            id, org_id, workspace_id, entity_id, modes, as_of, corpus_version_id,
            ontology_version, workflow_version, provider, model, policy_id,
            input_manifest, input_hash, idempotency_key, created_by, status
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s::jsonb, %s, %s, %s, 'queued'
        )
        """,
        (
            run_id,
            _ORG,
            _WORKSPACE,
            _SEEDED_ENTITY,
            ["kpi"],
            _AS_OF,
            _SEEDED_CORPUS,
            "saas-metrics/v1",
            WORKFLOW_VERSION,
            "mock",
            "mock-structured-v1",
            _POLICY,
            json.dumps(input_manifest),
            sha256_hex(f"manifest|{run_id}"),
            f"span-scope|{run_id}",
            _USER,
        ),
    )


def _cite(
    run_id: str,
    span: str,
    version: str,
    *,
    published_at: datetime | None = _EARLY,
    input_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A payload that agrees with its run row and cites ``span`` honestly.

    When ``published_at`` is not ``None``, the block claims that instant;
    passing ``None`` omits ``published_at`` from the payload block altogether.
    """
    payload = _payload(run_id)
    if input_manifest is not None:
        payload["input_manifest"] = input_manifest
    block: dict[str, Any] = {
        "source_span_id": span,
        "document_version_id": version,
        "text": LONG_SPAN_TEXT,
        "text_hash": _SPAN_HASH,
    }
    if published_at is not None:
        block["published_at"] = published_at.isoformat()
    payload["evidence"] = [block]
    return payload


def _run_out_of_scope(
    conn: psycopg.Connection[Any],
    span: str,
    version: str,
    *,
    published_at: datetime | None = _EARLY,
    input_manifest: dict[str, Any] | None = None,
) -> ExtractionError:
    run_id = str(uuid.uuid4())
    if input_manifest is None:
        _seed_run(conn, run_id)
    else:
        _seed_run_with_manifest(conn, run_id, input_manifest)
    with pytest.raises(ExtractionError) as excinfo:
        handle_extraction_run(
            conn,
            MockStructuredLLMProvider(),
            _cite(run_id, span, version, published_at=published_at, input_manifest=input_manifest),
            job_org_id=_ORG,
        )
    durable = _durable(conn, run_id)
    assert durable["status"] == "queued", "an out-of-scope citation started the run"
    assert durable["proposals"] == 0, "an out-of-scope citation persisted a proposal"
    return excinfo.value


@requires_db
def test_span_published_after_the_runs_cutoff_is_refused(extraction_db_url: str) -> None:
    """A filing published after ``as_of`` is not evidence the run could have seen.

    The payload even declares an in-cutoff ``published_at`` for the block: the
    only cutoff check that existed read that claim, not the document row.
    """
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "late",
            entity_id=_SEEDED_ENTITY,
            published_at=_LATE,
            corpus_version_id=_SEEDED_CORPUS,
        )
        error = _run_out_of_scope(conn, span, version)

    assert _LATE > _AS_OF
    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "as_of" in str(error)


@requires_db
def test_span_with_public_at_after_cutoff_is_refused(extraction_db_url: str) -> None:
    """Migration 0012: ``published_at <= as_of < public_at`` is refused before ``mark_running``."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "public-after-cutoff",
            entity_id=_SEEDED_ENTITY,
            published_at=_AS_OF,
            public_at=_LATE_PUBLIC_AT,
            corpus_version_id=_SEEDED_CORPUS,
        )
        error = _run_out_of_scope(conn, span, version)

    assert _AS_OF < _LATE_PUBLIC_AT
    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "as_of" in str(error)


@requires_db
def test_late_span_with_omitted_payload_published_at_is_refused(extraction_db_url: str) -> None:
    """Omitting ``published_at`` in the payload cannot bypass cutoff binding on a late document."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "late-omitted-published-at",
            entity_id=_SEEDED_ENTITY,
            published_at=_LATE,
            corpus_version_id=_SEEDED_CORPUS,
        )
        error = _run_out_of_scope(conn, span, version, published_at=None)

    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "as_of" in str(error)


@requires_db
def test_span_from_quarantined_document_version_is_refused(extraction_db_url: str) -> None:
    """A span from a ``quarantined`` document version is refused before ``mark_running``."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "quarantined",
            entity_id=_SEEDED_ENTITY,
            published_at=_EARLY,
            corpus_version_id=_SEEDED_CORPUS,
            document_version_status="quarantined",
        )
        error = _run_out_of_scope(conn, span, version)

    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "quarantined" in str(error)


@requires_db
def test_span_absent_from_pinned_input_manifest_is_refused(extraction_db_url: str) -> None:
    """An in-scope span outside ``input_manifest['source_span_ids']`` is refused."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        pinned_span, _ = _seed_span(
            conn,
            "manifest-pinned",
            entity_id=_SEEDED_ENTITY,
            published_at=_EARLY,
            corpus_version_id=_SEEDED_CORPUS,
        )
        unpinned_span, unpinned_version = _seed_span(
            conn,
            "manifest-unpinned",
            entity_id=_SEEDED_ENTITY,
            published_at=_EARLY,
            corpus_version_id=_SEEDED_CORPUS,
        )
        error = _run_out_of_scope(
            conn,
            unpinned_span,
            unpinned_version,
            input_manifest={"source_span_ids": [pinned_span]},
        )

    assert error.code == "integrity_error", error
    assert unpinned_span in str(error)
    assert "source_span_ids" in str(error)


@requires_db
def test_span_from_another_entity_is_refused(extraction_db_url: str) -> None:
    """A run pinned to one issuer cannot cite another issuer's filing."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "other-entity",
            entity_id=_OTHER_ENTITY,
            published_at=_EARLY,
            corpus_version_id=_SEEDED_CORPUS,
        )
        error = _run_out_of_scope(conn, span, version)

    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "entity" in str(error)


@requires_db
def test_span_outside_the_runs_corpus_pin_is_refused(extraction_db_url: str) -> None:
    """A document version absent from the run's pinned corpus is not citable.

    The version here IS in a corpus, just not the run's: membership must be
    checked against the pin, not merely exist.
    """
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        conn.execute(
            "INSERT INTO corpus_versions (id, label, status, is_active)"
            " VALUES (%s, 'Span Scope Other Corpus', 'draft', false)"
            " ON CONFLICT DO NOTHING",
            (_OTHER_CORPUS,),
        )
        span, version = _seed_span(
            conn,
            "other-corpus",
            entity_id=_SEEDED_ENTITY,
            published_at=_EARLY,
            corpus_version_id=_OTHER_CORPUS,
        )
        error = _run_out_of_scope(conn, span, version)

    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "corpus" in str(error)


@requires_db
def test_span_in_no_corpus_is_refused(extraction_db_url: str) -> None:
    """A document version that belongs to NO corpus is refused before ``mark_running``."""
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "no-corpus",
            entity_id=_SEEDED_ENTITY,
            published_at=_EARLY,
            corpus_version_id=None,
        )
        error = _run_out_of_scope(conn, span, version)

    assert error.code == "integrity_error", error
    assert span in str(error)
    assert "corpus" in str(error)


@requires_db
def test_span_published_exactly_at_the_cutoff_is_admitted(extraction_db_url: str) -> None:
    """The cutoff is inclusive (``<= as_of``), as in the retrieval lanes.

    Also checks that the bound block carries the document row's effective
    visibility instant rather than the payload's claim, so the downstream
    cutoff check in ``assemble_evidence`` reads the record too.
    """
    run_id = str(uuid.uuid4())
    with psycopg.connect(extraction_db_url, autocommit=True) as conn:
        conn.execute("SELECT set_config('app.org_id', %s, false)", (_ORG,))
        _seed_parents(conn)
        span, version = _seed_span(
            conn,
            "at-cutoff",
            entity_id=_SEEDED_ENTITY,
            published_at=_AS_OF,
            corpus_version_id=_SEEDED_CORPUS,
        )
        _seed_run(conn, run_id)
        state = handle_extraction_run(
            conn, MockStructuredLLMProvider(), _cite(run_id, span, version), job_org_id=_ORG
        )

    assert state.status == "waiting_review"
    assert [block.published_at for block in state.evidence] == [_AS_OF]


# ---------------------------------------------------------------------------
# Pure-Python unit tests (no Postgres required)
# ---------------------------------------------------------------------------


class _FakePersistStore:
    def __init__(self, pins: dict[str, SpanPin]) -> None:
        self._pins = pins

    def load_span_pins(self, span_ids: list[str]) -> dict[str, SpanPin]:
        del span_ids
        return dict(self._pins)


def _unit_request(*, input_manifest: dict[str, Any] | None = None) -> Any:
    run_id = str(uuid.uuid4())
    payload = _payload(run_id)
    if input_manifest is not None:
        payload["input_manifest"] = input_manifest
    return request_from_payload(payload)


def _unit_pin(
    span_id: str,
    version_id: str,
    *,
    entity_id: str = _SEEDED_ENTITY,
    published_at: datetime = _EARLY,
    corpus_version_ids: frozenset[str] = frozenset({_SEEDED_CORPUS}),
    document_version_status: str = "parsed",
) -> SpanPin:
    return SpanPin(
        source_span_id=span_id,
        document_version_id=version_id,
        text_hash=_SPAN_HASH,
        entity_id=entity_id,
        published_at=published_at,
        corpus_version_ids=corpus_version_ids,
        document_version_status=document_version_status,
    )


def _unit_block(
    span_id: str,
    version_id: str,
    *,
    published_at: datetime | None = _EARLY,
) -> EvidenceBlock:
    return EvidenceBlock(
        source_span_id=span_id,
        document_version_id=version_id,
        text=LONG_SPAN_TEXT,
        text_hash=_SPAN_HASH,
        published_at=published_at,
    )


def test_bind_evidence_unit_enforces_effective_public_at_cutoff() -> None:
    span_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    request = _unit_request()

    late_pin = _unit_pin(span_id, version_id, published_at=_LATE_PUBLIC_AT)
    with pytest.raises(IntegrityError, match="as_of"):
        _bind_evidence_to_spans(
            [_unit_block(span_id, version_id, published_at=_EARLY)],
            _FakePersistStore({span_id: late_pin}),  # type: ignore[arg-type]
            request,
        )

    with pytest.raises(IntegrityError, match="as_of"):
        _bind_evidence_to_spans(
            [_unit_block(span_id, version_id, published_at=None)],
            _FakePersistStore({span_id: late_pin}),  # type: ignore[arg-type]
            request,
        )

    at_cutoff_pin = _unit_pin(span_id, version_id, published_at=_AS_OF)
    bound = _bind_evidence_to_spans(
        [_unit_block(span_id, version_id, published_at=None)],
        _FakePersistStore({span_id: at_cutoff_pin}),  # type: ignore[arg-type]
        request,
    )
    assert [b.published_at for b in bound] == [_AS_OF]


def test_bind_evidence_unit_refuses_non_parsed_document_version() -> None:
    span_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    pin = _unit_pin(span_id, version_id, document_version_status="quarantined")
    with pytest.raises(IntegrityError, match="quarantined"):
        _bind_evidence_to_spans(
            [_unit_block(span_id, version_id)],
            _FakePersistStore({span_id: pin}),  # type: ignore[arg-type]
            _unit_request(),
        )


def test_bind_evidence_unit_refuses_span_in_no_corpus() -> None:
    span_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    pin = _unit_pin(span_id, version_id, corpus_version_ids=frozenset())
    with pytest.raises(IntegrityError, match="corpus"):
        _bind_evidence_to_spans(
            [_unit_block(span_id, version_id)],
            _FakePersistStore({span_id: pin}),  # type: ignore[arg-type]
            _unit_request(),
        )


def test_bind_evidence_unit_enforces_pinned_input_manifest_source_span_ids() -> None:
    pinned_id = str(uuid.uuid4())
    unpinned_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    unpinned_pin = _unit_pin(unpinned_id, version_id)
    pinned_pin = _unit_pin(pinned_id, version_id)

    with pytest.raises(IntegrityError, match="source_span_ids"):
        _bind_evidence_to_spans(
            [_unit_block(unpinned_id, version_id)],
            _FakePersistStore({unpinned_id: unpinned_pin}),  # type: ignore[arg-type]
            _unit_request(input_manifest={"source_span_ids": [pinned_id]}),
        )

    for bad_manifest in (
        {"source_span_ids": pinned_id},
        {"source_span_ids": None},
        {"source_span_ids": {"id": pinned_id}},
        {"source_span_ids": [123]},
        {"source_span_ids": ["not-a-uuid"]},
        {"source_span_ids": []},
    ):
        with pytest.raises(IntegrityError, match="source_span_ids"):
            _bind_evidence_to_spans(
                [_unit_block(pinned_id, version_id)],
                _FakePersistStore({pinned_id: pinned_pin}),  # type: ignore[arg-type]
                _unit_request(input_manifest=bad_manifest),
            )

    # Uppercase UUID normalization matches canonical pin; absent key stays compatible.
    bound_upper = _bind_evidence_to_spans(
        [_unit_block(pinned_id.upper(), version_id)],
        _FakePersistStore({pinned_id: pinned_pin}),  # type: ignore[arg-type]
        _unit_request(input_manifest={"source_span_ids": [pinned_id.upper()]}),
    )
    assert [b.source_span_id for b in bound_upper] == [pinned_id]

    bound_absent = _bind_evidence_to_spans(
        [_unit_block(pinned_id, version_id)],
        _FakePersistStore({pinned_id: pinned_pin}),  # type: ignore[arg-type]
        _unit_request(input_manifest={}),
    )
    assert [b.source_span_id for b in bound_absent] == [pinned_id]


def test_restore_output_fails_closed_on_missing_or_late_published_at() -> None:
    span_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    request = _unit_request()

    base_dict: dict[str, Any] = {
        "source_span_id": span_id,
        "document_version_id": version_id,
        "text": LONG_SPAN_TEXT,
        "text_hash": _SPAN_HASH,
    }
    for bad_block in (
        dict(base_dict),
        {**base_dict, "published_at": None},
        {**base_dict, "published_at": ""},
        {**base_dict, "published_at": "not-a-timestamp"},
        {**base_dict, "published_at": _LATE.isoformat()},
        {**base_dict, "published_at": _LATE_PUBLIC_AT.isoformat()},
        _unit_block(span_id, version_id, published_at=None),
        _unit_block(span_id, version_id, published_at=_LATE),
    ):
        state = WorkflowState(request=request)
        with pytest.raises(CutoffViolation):
            _restore_output(state, "assemble_evidence", [bad_block])

    # Inclusive cutoff (== as_of) and earlier timestamps restore cleanly.
    for ok_ts in (_EARLY, _AS_OF):
        state = WorkflowState(request=request)
        _restore_output(
            state,
            "assemble_evidence",
            [{**base_dict, "published_at": ok_ts.isoformat()}],
        )
        assert [b.published_at for b in state.evidence] == [ok_ts]

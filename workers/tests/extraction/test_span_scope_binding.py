"""A cited span must lie inside the run's own scope: cutoff, entity and corpus.

``_bind_evidence_to_spans`` verified that a span resolves, that its
``document_version_id`` matches the evidence block and that its ``text_hash``
matches the supplied text (#451, finding C2 of the 2026-11-13 code review). It
never compared the span with the run it was being cited by. The run row pins
``as_of``, ``entity_id`` and ``corpus_version_id``, and ``load_run_pins`` reads
all three, but none of them reached span binding. The only cutoff check
downstream, in ``stages/assemble_evidence``, reads ``published_at`` from the
PAYLOAD, so a payload that omits or understates it passes.

So a durable run could cite, with a perfectly valid hash:

- a span from a filing published after the run's ``as_of`` (look-ahead);
- a span from another issuer's filing;
- a span from a document version outside the run's pinned corpus.

Each test below seeds one such span, real and hash-correct, and expects the
run to be refused before ``mark_running``: ``integrity_error``, the run still
``queued`` and no proposal persisted.

Runs against the isolated ``<db>_extraction`` sibling for the reason documented
in ``test_postgres_crash_resume``.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from fel_providers.mocks import MockStructuredLLMProvider
from fel_workers.extraction.errors import ExtractionError
from fel_workers.extraction.handler import handle_extraction_run
from fel_workers.extraction.hashing import sha256_hex

from .test_postgres_crash_resume import _CORPUS as _SEEDED_CORPUS
from .test_postgres_crash_resume import _ENTITY as _SEEDED_ENTITY
from .test_postgres_crash_resume import (
    _ORG,
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
# its hash is correct and the existing three checks all pass. Only scope differs.
_SPAN_HASH = sha256_hex(LONG_SPAN_TEXT)

# Inside the cutoff by a comfortable margin; the "late" case is a year past it.
_EARLY = datetime(2026, 6, 30, tzinfo=UTC)
_LATE = datetime(2027, 12, 31, tzinfo=UTC)


@pytest.fixture(scope="module")
def extraction_db_url() -> str:
    if TEST_DATABASE_URL is None:
        pytest.skip("TEST_DATABASE_URL not configured")
    return ensure_extraction_database(TEST_DATABASE_URL)


def _seed_span(
    conn: psycopg.Connection,
    tag: str,
    *,
    entity_id: str,
    published_at: datetime,
    corpus_version_id: str | None,
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
    statements: list[tuple[str, tuple[Any, ...]]] = [
        (
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
        ),
        (
            "INSERT INTO document_versions (id, document_id, parser_version,"
            " normalizer_version, canonical_text_key) VALUES (%s, %s, 'p1', 'n1', %s)",
            (version, document, f"text/span-scope-{tag}"),
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


def _cite(run_id: str, span: str, version: str) -> dict[str, Any]:
    """A payload that agrees with its run row and cites ``span`` honestly.

    The block also claims an in-cutoff ``published_at``. That claim is the
    payload's, and the record must overrule it.
    """
    payload = _payload(run_id)
    payload["evidence"] = [
        {
            "source_span_id": span,
            "document_version_id": version,
            "text": LONG_SPAN_TEXT,
            "text_hash": _SPAN_HASH,
            "published_at": _EARLY.isoformat(),
        }
    ]
    return payload


def _run_out_of_scope(conn: psycopg.Connection, span: str, version: str) -> ExtractionError:
    run_id = str(uuid.uuid4())
    _seed_run(conn, run_id)
    with pytest.raises(ExtractionError) as excinfo:
        handle_extraction_run(
            conn, MockStructuredLLMProvider(), _cite(run_id, span, version), job_org_id=_ORG
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
def test_span_published_exactly_at_the_cutoff_is_admitted(extraction_db_url: str) -> None:
    """The cutoff is inclusive (``<= as_of``), as in the retrieval lanes.

    Also checks that the bound block carries the document row's ``published_at``
    rather than the payload's claim, so the downstream cutoff check in
    ``assemble_evidence`` reads the record too.
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

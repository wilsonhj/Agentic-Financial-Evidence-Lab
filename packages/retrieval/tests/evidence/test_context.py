"""Context resolution (design contract §6.1, §6.3; MCP-402): cutoff and pins."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from fel_retrieval import content_sha256
from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.context import effective_as_of, resolve_context
from fel_retrieval.index_version import index_version_id

NOW = datetime(2026, 11, 14, 15, 30, 0, 123456, tzinfo=UTC)
CORPUS = "a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8"
INDEX = "b18dab9f-3a2e-4f5b-8c4d-8495a6b7c8d9"
MICRO = timedelta(microseconds=1)


def _error(code: str, field: str | None) -> Any:
    return pytest.raises(i.EvidenceReadError, check=lambda e: (e.code, e.field) == (code, field))


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (None, NOW),
        (NOW, NOW),
        (date(2024, 3, 6), datetime(2024, 3, 6, 5, 0, tzinfo=UTC)),  # 00:00 EST
        (date(2024, 7, 1), datetime(2024, 7, 1, 4, 0, tzinfo=UTC)),  # 00:00 EDT
        (date(2024, 3, 10), datetime(2024, 3, 10, 5, 0, tzinfo=UTC)),  # DST begins that day
        (
            datetime(2024, 3, 6, 16, 14, 9, tzinfo=timezone(timedelta(hours=-5))),
            datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC),
        ),
        (datetime(1994, 1, 1, tzinfo=UTC), datetime(1994, 1, 1, tzinfo=UTC)),
    ],
)
def test_effective_as_of(as_of: datetime | date | None, expected: datetime) -> None:
    resolved = effective_as_of(as_of, NOW)
    assert resolved == expected
    assert resolved.utcoffset() == timedelta(0)  # echoed in UTC, so replays are byte-identical


@pytest.mark.parametrize(
    "as_of",
    [
        NOW + MICRO,  # the future, by the smallest step
        date(2026, 11, 15),
        datetime(1994, 1, 1, tzinfo=UTC) - MICRO,
        date(1993, 12, 31),
    ],
)
def test_as_of_outside_the_contract_range_is_rejected(as_of: datetime | date) -> None:
    with _error("invalid_input", "as_of"):
        effective_as_of(as_of, NOW)


def test_a_naive_as_of_never_reaches_resolution() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        i.ContextRequest(request_time=NOW, as_of=datetime(2024, 3, 6))


def test_rejections_that_need_no_database_do_no_database_work(fake_conn: Any) -> None:
    conn = fake_conn()
    cases = [
        (i.ContextRequest(request_time=NOW, as_of=NOW + MICRO), "invalid_input", "as_of"),
        (
            i.ContextRequest(request_time=NOW, timestamp_mode="approximate"),
            "invalid_input",
            "timestamp_mode",
        ),
        (
            i.ContextRequest(request_time=NOW, corpus_version_id="latest"),
            "invalid_input",
            "corpus_version_id",
        ),
        (
            i.ContextRequest(request_time=NOW, index_version_id="1"),
            "invalid_input",
            "index_version_id",
        ),
        (
            i.ContextRequest(request_time=NOW, verifier_version="deterministic-v2"),
            "pin_unavailable",
            "verifier_version",
        ),
    ]
    for request, code, field in cases:
        with _error(code, field):
            resolve_context(conn, request)
    assert conn.statements == []


def test_resolution_echoes_pins_and_keeps_a_null_index(fake_conn: Any) -> None:
    conn = fake_conn({"WHERE id = %s AND status IN ('active', 'superseded')": [(CORPUS,)]})
    request = i.ContextRequest(
        request_time=NOW,
        as_of=date(2024, 3, 6),
        corpus_version_id=CORPUS,
        filters=i.ContextFilters(company="CRM"),
    )
    context = resolve_context(conn, request)
    assert context == i.EvidenceContext(
        effective_as_of=datetime(2024, 3, 6, 5, 0, tzinfo=UTC),
        timestamp_mode="strict",
        temporal_guarantee="strict",
        corpus_version_id=CORPUS,
        index_version_id=None,
        parser_version=None,
        verifier_version="deterministic-v1",
        document_version_id=None,
        filters=i.ContextFilters(company="CRM"),
    )
    assert not any("retrieval_index_versions" in sql for sql in conn.sql)
    assert "SET LOCAL ROLE fel_public_read" in conn.sql


def test_an_unavailable_corpus_pin_never_falls_back_to_the_active_corpus(fake_conn: Any) -> None:
    conn = fake_conn({"WHERE is_active": [(CORPUS,)]})
    with _error("pin_unavailable", "corpus_version_id"):
        resolve_context(conn, i.ContextRequest(request_time=NOW, corpus_version_id=INDEX))
    assert not any("WHERE is_active" in sql for sql in conn.sql)


def test_no_active_corpus_is_unavailable_not_a_guess(fake_conn: Any) -> None:
    with pytest.raises(i.EvidenceReadError) as raised:
        resolve_context(fake_conn(), i.ContextRequest(request_time=NOW))
    assert (raised.value.code, raised.value.retryable) == ("unavailable", True)


def test_an_incompatible_index_pin_is_named(fake_conn: Any) -> None:
    conn = fake_conn({"FROM corpus_versions": [(CORPUS,)]})
    with _error("pin_unavailable", "index_version_id"):
        resolve_context(conn, i.ContextRequest(request_time=NOW, index_version_id=INDEX))
    with _error("pin_unavailable", "index_version_id"):
        resolve_context(conn, i.ContextRequest(request_time=NOW, require_index=True))


# ---------------------------------------------------------------------------
# PostgreSQL (CI): the pin queries against the real schema and role
# ---------------------------------------------------------------------------


def _index(conn: Any, corpus_version_id: str, status: str) -> str:
    config_hash = content_sha256(str(uuid.uuid4()))
    identity = index_version_id(
        corpus_version_id=corpus_version_id, config_hash=config_hash, provider="none", model="none"
    )
    conn.execute(
        "INSERT INTO retrieval_index_versions (id, corpus_version_id, chunker_version, "
        "config_hash, embedding_provider, embedding_model) VALUES (%s, %s, 'c/1', %s, "
        "'none', 'none')",
        (identity, corpus_version_id, config_hash),
    )
    steps = {
        "building": "UPDATE retrieval_index_versions SET status = 'building' WHERE id = %s",
        "ready": "UPDATE retrieval_index_versions SET status = 'ready', published_at = now() "
        "WHERE id = %s",
        "superseded": "UPDATE retrieval_index_versions SET status = 'superseded' WHERE id = %s",
    }
    for step, statement in steps.items():
        if status == "draft":
            break
        conn.execute(statement, (identity,))
        if step == status:
            break
    return identity


def test_corpus_pins_against_postgres(pg_conn: Any, evidence_helpers: Any) -> None:
    published = evidence_helpers.new_corpus(pg_conn, "superseded")
    draft = evidence_helpers.new_corpus(pg_conn, "draft")
    context = resolve_context(
        pg_conn, i.ContextRequest(request_time=NOW, corpus_version_id=published)
    )
    assert (context.corpus_version_id, context.index_version_id) == (published, None)
    for unavailable in (draft, str(uuid.uuid4())):
        with _error("pin_unavailable", "corpus_version_id"):
            resolve_context(
                pg_conn, i.ContextRequest(request_time=NOW, corpus_version_id=unavailable)
            )


def test_an_omitted_corpus_pin_resolves_the_active_corpus(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    previous = pg_conn.execute("SELECT id FROM corpus_versions WHERE is_active").fetchone()
    retire = "UPDATE corpus_versions SET is_active = false, status = 'superseded' WHERE id = %s"
    if previous is not None:
        pg_conn.execute(retire, (previous[0],))
    active = evidence_helpers.new_corpus(pg_conn, "active")
    try:
        assert (
            resolve_context(pg_conn, i.ContextRequest(request_time=NOW)).corpus_version_id == active
        )
    finally:
        pg_conn.execute(retire, (active,))
        if previous is not None:
            pg_conn.execute(
                "UPDATE corpus_versions SET is_active = true, status = 'active' WHERE id = %s",
                (previous[0],),
            )


def test_index_pins_against_postgres(pg_conn: Any, evidence_helpers: Any) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    other = evidence_helpers.new_corpus(pg_conn)

    def resolve(**pins: Any) -> i.EvidenceContext:
        return resolve_context(
            pg_conn, i.ContextRequest(request_time=NOW, corpus_version_id=corpus, **pins)
        )

    with _error("pin_unavailable", "index_version_id"):
        resolve(require_index=True)  # search needs an index and none is published
    older = _index(pg_conn, corpus, "superseded")
    newer = _index(pg_conn, corpus, "ready")
    unpublished = [_index(pg_conn, corpus, "draft"), _index(pg_conn, corpus, "building")]
    foreign = _index(pg_conn, other, "ready")

    assert resolve().index_version_id is None
    assert resolve(require_index=True).index_version_id == newer
    assert resolve(index_version_id=older).index_version_id == older
    assert resolve(index_version_id=older, require_index=True).index_version_id == older
    for unavailable in (*unpublished, foreign, str(uuid.uuid4())):
        with _error("pin_unavailable", "index_version_id"):
            resolve(index_version_id=unavailable)

"""Fixtures for the evidence-read service tests (#395).

Unit tests use ``FakeConn``, a fake at the connection boundary, so they run
without a database. Tests that prove SQL behaviour take ``pg_conn`` from the
parent conftest and need ``TEST_DATABASE_URL``; CI sets ``FEL_REQUIRE_DB=1`` so
a lost URL fails collection instead of skipping them silently (#202).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from fel_retrieval import content_sha256
from fel_retrieval.evidence import interfaces as i

if os.environ.get("FEL_REQUIRE_DB") == "1" and os.environ.get("TEST_DATABASE_URL") is None:
    raise RuntimeError(
        "FEL_REQUIRE_DB=1 but TEST_DATABASE_URL is unset, so the evidence-read "
        "database tests would have skipped silently."
    )

# The #386 fixture: a supplementary-plane character precedes the cited text.
FILLER = "x" * 400
CANONICAL_TEXT = FILLER + "A\U0001f600B"
SPANS = ((402, 403), (401, 403), (0, 400))  # "B", "\U0001f600B", the filler


class _Cursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class FakeConn:
    """Records every statement; answers by the first matching SQL fragment."""

    def __init__(self, answers: Mapping[str, list[tuple[Any, ...]]] | None = None) -> None:
        self.answers = dict(answers or {})
        self.statements: list[tuple[str, Any]] = []
        self.raise_on_execute: Exception | None = None

    def execute(self, query: str, params: Any = None) -> _Cursor:
        self.statements.append((query, params))
        if self.raise_on_execute is not None and "SET" not in query and "set_config" not in query:
            raise self.raise_on_execute
        for fragment, rows in self.answers.items():
            if fragment in query:
                return _Cursor(rows)
        return _Cursor([])

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.statements.append(("BEGIN", None))
        yield

    @property
    def sql(self) -> list[str]:
        return [statement for statement, _ in self.statements]


class MemoryTexts:
    """In-memory canonical-text store."""

    def __init__(self, objects: Mapping[str, bytes]) -> None:
        self.objects = dict(objects)
        self.error: Exception | None = None
        self.reads = 0

    def read(self, key: str, limit: int) -> bytes:
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.objects[key][:limit]


def make_context(
    as_of: datetime, corpus_version_id: str, mode: i.TimestampMode = "strict"
) -> i.EvidenceContext:
    return i.EvidenceContext(
        effective_as_of=as_of,
        timestamp_mode=mode,
        temporal_guarantee="strict" if mode == "strict" else "none",
        corpus_version_id=corpus_version_id,
        index_version_id=None,
        parser_version=None,
        verifier_version="deterministic-v1",
        document_version_id=None,
        filters=i.ContextFilters(),
    )


@dataclass(frozen=True)
class SeededFiling:
    corpus_version_id: str
    company: i.Company
    document_id: str
    document_version_id: str
    span_ids: tuple[str, ...]
    text_key: str
    accession: str


def new_corpus(conn: Any, status: str = "superseded") -> str:
    """A corpus version. ``superseded`` is published and retained, not active."""
    corpus_version_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO corpus_versions (id, label, status, is_active, published_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            corpus_version_id,
            f"evidence-{corpus_version_id[:8]}",
            status,
            status == "active",
            None if status == "draft" else datetime.now(UTC),
        ),
    )
    return corpus_version_id


def seed_filing(
    conn: Any,
    corpus_version_id: str,
    *,
    public_at: datetime | None,
    published_at: datetime,
    accepted_at: datetime | None = None,
    form: str | None = "10-K",
    accession: str | None = None,
    version_status: str = "parsed",
    in_corpus: bool = True,
    entity_id: str | None = None,
) -> SeededFiling:
    """One filing with the #386 canonical text and three spans."""
    serial = uuid.uuid4().int
    accession = accession or f"{serial % 10**10:010d}-24-{(serial >> 40) % 10**6:06d}"
    entity_id = entity_id or str(uuid.uuid4())
    document_id, version_id, section_id = (str(uuid.uuid4()) for _ in range(3))
    accepted_at = accepted_at if accepted_at is not None else public_at
    basis = None
    if public_at is not None:
        basis = "acceptance" if public_at == accepted_at else "next_session_open"
    conn.execute(
        "INSERT INTO documents (id, entity_id, accession, form, source_url, content_hash, "
        "storage_key, published_at, accepted_at, public_at, public_at_basis, "
        "timestamp_precision) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            document_id,
            entity_id,
            accession,
            form,
            f"https://www.sec.gov/Archives/edgar/data/{document_id}.htm",
            content_sha256(document_id),
            f"raw/{document_id}",
            published_at,
            accepted_at,
            public_at,
            basis,
            "date" if public_at is None else "second",
        ),
    )
    text_key = f"text/sha256/{document_id}"
    conn.execute(
        "INSERT INTO document_versions (id, document_id, parser_version, "
        "normalizer_version, status, canonical_text_key) VALUES (%s, %s, 'p/1', 'n/1', %s, %s)",
        (version_id, document_id, version_status, text_key),
    )
    conn.execute(
        "INSERT INTO sections (id, document_version_id, heading, heading_path, ord, "
        "start_char, end_char) VALUES (%s, %s, 'Item 7', %s, 0, 0, %s)",
        (section_id, version_id, ["Part II", "Item 7"], len(CANONICAL_TEXT)),
    )
    span_ids = []
    for start, end in SPANS:
        span_ids.append(str(uuid.uuid4()))
        conn.execute(
            "INSERT INTO source_spans (id, document_version_id, section_id, start_char, "
            "end_char, text_hash) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                span_ids[-1],
                version_id,
                section_id,
                start,
                end,
                content_sha256(CANONICAL_TEXT[start:end]),
            ),
        )
    if in_corpus:
        conn.execute(
            "INSERT INTO corpus_version_documents (corpus_version_id, document_version_id) "
            "VALUES (%s, %s)",
            (corpus_version_id, version_id),
        )
    company = i.Company(entity_id=entity_id, cik=accession[:10], ticker="TST", name="Test Co")
    return SeededFiling(
        corpus_version_id, company, document_id, version_id, tuple(span_ids), text_key, accession
    )


@pytest.fixture()
def fake_conn() -> Callable[..., FakeConn]:
    return FakeConn


@pytest.fixture()
def evidence_helpers() -> Any:
    """Seeders and builders; a fixture because importlib mode has no sibling imports."""

    class Helpers:
        CANONICAL_TEXT = CANONICAL_TEXT
        SPANS = SPANS
        MemoryTexts = MemoryTexts
        make_context = staticmethod(make_context)
        new_corpus = staticmethod(new_corpus)
        seed_filing = staticmethod(seed_filing)

    return Helpers

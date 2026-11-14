"""Strict visibility on PostgreSQL (ADR-0034 decision 4 and Amendment 1; MCP-401, MCP-407).

These tests need ``TEST_DATABASE_URL`` and run in CI's Python job. They prove
what a fake connection cannot: the SQL predicate, the ``fel_public_read``
grants, and the statement timeout.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fel_retrieval import content_sha256
from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.citations import get_citation
from fel_retrieval.evidence.visibility import STATEMENT_TIMEOUT_MS, public_read_session

CUTOFF = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
MICRO = timedelta(microseconds=1)
HOUR = timedelta(hours=1)
NOT_FOUND = vars(i.EvidenceReadError.not_found())


def _read(conn: Any, helpers: Any, filing: Any, as_of: datetime, **overrides: Any) -> Any:
    """Read the filing's "B" span at ``as_of``; a citation, or the error's fields."""
    arguments: dict[str, Any] = {
        "ref": i.SpanIdRef(filing.span_ids[0]),
        "corpus": filing.corpus_version_id,
        "companies": {filing.company.entity_id: filing.company},
        **overrides,
    }
    try:
        return get_citation(
            conn,
            arguments["ref"],
            helpers.make_context(as_of, arguments["corpus"]),
            companies=arguments["companies"],
            texts=helpers.MemoryTexts({filing.text_key: helpers.CANONICAL_TEXT.encode()}),
        ).citation
    except i.EvidenceReadError as error:
        return vars(error)


def test_property_a_filing_is_visible_exactly_from_its_public_instant(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    rng = random.Random(395)
    corpus = evidence_helpers.new_corpus(pg_conn)
    offsets = [timedelta(0), MICRO, -MICRO, timedelta(seconds=1), -timedelta(seconds=1)]
    offsets += [timedelta(microseconds=rng.randint(-(10**12), 10**12)) for _ in range(15)]
    filings = [
        (
            evidence_helpers.seed_filing(
                pg_conn, corpus, public_at=CUTOFF + offset, published_at=CUTOFF + offset - HOUR
            ),
            CUTOFF + offset,
        )
        for offset in offsets
    ]
    cutoffs = [
        CUTOFF,
        CUTOFF - MICRO,
        CUTOFF + MICRO,
        *(public_at for _, public_at in filings[5:9]),
    ]
    seen = set()
    for as_of in cutoffs:
        for filing, public_at in filings:
            outcome = _read(pg_conn, evidence_helpers, filing, as_of)
            if public_at <= as_of:
                assert (outcome.span_id, outcome.text, outcome.public_at) == (
                    filing.span_ids[0],
                    "B",
                    public_at,
                )
            else:
                assert outcome == NOT_FOUND
            seen.add(public_at <= as_of)
    assert seen == {True, False}


def test_acceptance_is_not_publication(pg_conn: Any, evidence_helpers: Any) -> None:
    # Accepted 18:00 EST on 03-05, filing date 03-06: public at 06:00 EST on 03-06.
    corpus = evidence_helpers.new_corpus(pg_conn)
    opens = datetime(2024, 3, 6, 11, 0, tzinfo=UTC)
    filing = evidence_helpers.seed_filing(
        pg_conn,
        corpus,
        accepted_at=datetime(2024, 3, 5, 23, 0, tzinfo=UTC),
        public_at=opens,
        published_at=datetime(2024, 3, 6, tzinfo=UTC),
    )
    assert _read(pg_conn, evidence_helpers, filing, opens - MICRO) == NOT_FOUND
    citation = _read(pg_conn, evidence_helpers, filing, opens)
    assert (citation.public_at_basis, citation.accepted_at) == (
        "next_session_open",
        datetime(2024, 3, 5, 23, 0, tzinfo=UTC),
    )
    assert citation.filing_date.isoformat() == "2024-03-06"


HIDDEN = {
    "no verified public_at, filing date long past": {"public_at": None},
    "version is quarantined": {"version_status": "quarantined"},
    "version is not in the pinned corpus": {"in_corpus": False},
    "company-facts snapshot": {"form": "COMPANYFACTS"},
    "not a filing accession": {"snapshot_shaped": True},
    "public_at precedes a later filing date": {"published_at": CUTOFF + MICRO},
}


@pytest.mark.parametrize("case", sorted(HIDDEN))
def test_hidden_evidence_is_indistinguishable_from_missing(
    pg_conn: Any, evidence_helpers: Any, case: str
) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    seed: dict[str, Any] = {"public_at": CUTOFF - HOUR, "published_at": CUTOFF - 2 * HOUR}
    seed.update(HIDDEN[case])
    if seed.pop("snapshot_shaped", False):
        # The shape company-facts snapshots are stored under, on a 10-K form.
        snapshot = "-".join(["COMPANYFACTS", "0001108524", "2024-03-01", uuid.uuid4().hex[:8]])
        seed.update(accession=snapshot)
    control = evidence_helpers.seed_filing(
        pg_conn, corpus, public_at=CUTOFF, published_at=CUTOFF - HOUR
    )
    hidden = evidence_helpers.seed_filing(pg_conn, corpus, **seed)

    assert _read(pg_conn, evidence_helpers, control, CUTOFF).text == "B"
    by_id = _read(pg_conn, evidence_helpers, hidden, CUTOFF)
    by_range = _read(
        pg_conn,
        evidence_helpers,
        hidden,
        CUTOFF,
        ref=i.SpanRangeRef(hidden.document_version_id, 402, 403),
    )
    missing = _read(pg_conn, evidence_helpers, hidden, CUTOFF, ref=i.SpanIdRef(str(uuid.uuid4())))
    assert by_id == by_range == missing == NOT_FOUND


def test_scope_is_the_pinned_corpus_and_the_served_cohort(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    other = evidence_helpers.new_corpus(pg_conn)
    filing = evidence_helpers.seed_filing(
        pg_conn, corpus, public_at=CUTOFF, published_at=CUTOFF - HOUR
    )
    assert _read(pg_conn, evidence_helpers, filing, CUTOFF, corpus=other) == NOT_FOUND
    assert _read(pg_conn, evidence_helpers, filing, CUTOFF, companies={}) == NOT_FOUND


def test_references_and_coverage_on_postgres(pg_conn: Any, evidence_helpers: Any) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    entity = str(uuid.uuid4())
    early, late = CUTOFF - 3 * HOUR, CUTOFF - HOUR
    seeds = [
        {"public_at": early},
        {"public_at": late},
        {"public_at": CUTOFF + HOUR},  # not yet public: outside the coverage range
        {"public_at": CUTOFF - 5 * HOUR, "form": "8-K"},  # another form
    ]
    filings = [
        evidence_helpers.seed_filing(
            pg_conn, corpus, published_at=CUTOFF - 9 * HOUR, entity_id=entity, **seed
        )
        for seed in seeds
    ]
    target = filings[1]
    texts = evidence_helpers.MemoryTexts(
        {target.text_key: evidence_helpers.CANONICAL_TEXT.encode()}
    )
    context = evidence_helpers.make_context(CUTOFF, corpus)
    companies = {entity: target.company}

    by_id = get_citation(
        pg_conn, i.SpanIdRef(target.span_ids[1]), context, companies=companies, texts=texts
    )
    by_range = get_citation(
        pg_conn,
        i.SpanRangeRef(target.document_version_id, 401, 403),
        context,
        companies=companies,
        texts=texts,
    )
    assert by_id == by_range
    assert by_id.citation.text == "\U0001f600B"
    assert by_id.citation.text_hash == content_sha256("\U0001f600B")
    assert by_id.citation.section_path == ("Part II", "Item 7")
    assert by_id.citation.document_content_hash == content_sha256(target.document_id)
    assert by_id.coverage_note.date_range == i.DateRange(from_=early, to=late)
    assert (by_id.coverage_note.issuers, by_id.coverage_note.forms) == (
        (target.company.cik,),
        ("10-K",),
    )
    unstored = i.SpanRangeRef(target.document_version_id, 401, 402)
    with pytest.raises(i.EvidenceReadError, check=lambda e: vars(e) == NOT_FOUND):
        get_citation(pg_conn, unstored, context, companies=companies, texts=texts)


def test_reads_run_on_the_public_read_role_with_a_statement_timeout(pg_conn: Any) -> None:
    session_user = pg_conn.execute("SELECT current_user").fetchone()[0]
    with public_read_session(pg_conn):
        settings = pg_conn.execute(
            "SELECT current_user::text, current_setting('statement_timeout'), "
            "current_setting('transaction_read_only'), current_setting('transaction_isolation')"
        ).fetchone()
        assert settings == (
            "fel_public_read",
            f"{STATEMENT_TIMEOUT_MS // 1000}s",
            "on",
            "repeatable read",
        )
        assert pg_conn.execute("SELECT count(*) FROM documents").fetchone() is not None
    assert pg_conn.execute("SELECT current_user").fetchone()[0] == session_user

    for denied in (
        "SELECT 1 FROM ingestion_runs",
        "SELECT 1 FROM retrieval_embeddings",
        "SELECT 1 FROM organizations",
        "INSERT INTO corpus_versions (id, label) VALUES (gen_random_uuid(), 'x')",
    ):
        with pytest.raises(Exception) as raised, public_read_session(pg_conn):
            pg_conn.execute(denied)
        assert getattr(raised.value, "sqlstate", None) in {"42501", "25006"}, denied


def test_a_slow_statement_is_cancelled_as_deadline_exceeded(pg_conn: Any) -> None:
    with pytest.raises(i.EvidenceReadError) as raised:
        with public_read_session(pg_conn, statement_timeout_ms=20):
            pg_conn.execute("SELECT pg_sleep(2)")
    assert (raised.value.code, raised.value.retryable) == ("deadline_exceeded", True)

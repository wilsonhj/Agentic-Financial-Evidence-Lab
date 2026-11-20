"""Company resolver and filing listing on PostgreSQL (MCP-403). Runs in CI's Python job."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.cursors import CursorCodec
from fel_retrieval.evidence.filings import list_filings, resolve_company

CUTOFF = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
MICRO = timedelta(microseconds=1)
HOUR = timedelta(hours=1)
MAX_PAGES = 40  # more than any listing here: 14 visible filings at one per page
CURSORS = CursorCodec(b"k" * 32, lambda: datetime(2026, 11, 14, tzinfo=UTC))


def _company() -> i.Company:
    return i.Company(str(uuid.uuid4()), "0000000395", "TST", "Test Co")


def _pages(conn: Any, context: Any, company: i.Company, limit: int, forms: Any) -> list[Any]:
    """Every page of the listing, checking that only the last page is short.

    Bounded, so a keyset regression that repeats a page fails instead of hanging.
    """
    filings: list[Any] = []
    cursor = None
    for _ in range(MAX_PAGES):
        request = i.ListFilingsRequest(company="tst", limit=limit, forms=forms, cursor=cursor)
        page = list_filings(
            conn, request, context, companies={company.entity_id: company}, cursors=CURSORS
        )
        filings.extend(page.filings)
        cursor = page.next_cursor
        if cursor is None:
            return filings
        assert len(page.filings) == limit
    pytest.fail(f"the listing did not end within {MAX_PAGES} pages")


def test_property_pages_and_coverage_hold_exactly_the_visible_filings(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    rng = random.Random(403)
    corpus = evidence_helpers.new_corpus(pg_conn)
    company = _company()
    stamps = [CUTOFF - 24 * HOUR, CUTOFF, CUTOFF, CUTOFF + MICRO, CUTOFF - MICRO]
    stamps += [CUTOFF + timedelta(microseconds=rng.randint(-(10**10), 10**10)) for _ in range(9)]
    seeded = []
    for public_at in stamps:
        form = rng.choice(["10-K", "10-Q", "8-K"])
        filing = evidence_helpers.seed_filing(
            pg_conn,
            corpus,
            public_at=public_at,
            published_at=public_at - HOUR,
            form=form,
            entity_id=company.entity_id,
        )
        seeded.append((public_at, filing.document_id, form, filing.accession))
    never_visible: list[dict[str, Any]] = [
        {"public_at": None},
        {"version_status": "quarantined"},
        {"in_corpus": False},
        {"form": "COMPANYFACTS"},
    ]
    for hidden in never_visible:
        seed = {"public_at": CUTOFF - 2 * HOUR, "published_at": CUTOFF - 3 * HOUR, **hidden}
        evidence_helpers.seed_filing(pg_conn, corpus, entity_id=company.entity_id, **seed)

    for as_of in (CUTOFF, CUTOFF - MICRO, max(stamps)):
        context = evidence_helpers.make_context(as_of, corpus)
        visible = sorted((row for row in seeded if row[0] <= as_of), reverse=True)
        for forms in (None, ("10-K",), ("8-K", "10-Q")):
            expected = [row for row in visible if forms is None or row[2] in forms]
            for limit in (1, 3, 50):
                listed = _pages(pg_conn, context, company, limit, forms)
                assert [
                    (f.public_at, f.document_id, f.form, f.accession) for f in listed
                ] == expected

        match = resolve_company(
            pg_conn,
            i.ResolveCompanyRequest(query="Test"),
            context,
            companies={company.entity_id: company},
        ).matches[0]
        coverage = match.coverage
        assert coverage.visible_filing_count == len(visible)
        assert coverage.visible_forms == tuple(sorted({row[2] for row in visible}))
        assert (
            coverage.first_visible_filing is not None and coverage.last_visible_filing is not None
        )
        assert coverage.first_visible_filing.accession == visible[-1][3]
        assert coverage.last_visible_filing.accession == visible[0][3]
        assert coverage.last_visible_filing.public_at == visible[0][0] <= as_of


def test_a_company_whose_filings_are_all_hidden_equals_an_unknown_company(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    company = _company()
    evidence_helpers.seed_filing(
        pg_conn,
        corpus,
        public_at=CUTOFF + MICRO,
        published_at=CUTOFF - HOUR,
        entity_id=company.entity_id,
    )
    context = evidence_helpers.make_context(CUTOFF, corpus)
    cohort = {company.entity_id: company}

    def outcomes(name: str) -> tuple[Any, Any]:
        resolved = resolve_company(
            pg_conn, i.ResolveCompanyRequest(query=name), context, companies=cohort
        )
        with pytest.raises(i.EvidenceReadError) as raised:
            list_filings(
                pg_conn,
                i.ListFilingsRequest(company=name, limit=10),
                context,
                companies=cohort,
                cursors=CURSORS,
            )
        return resolved, vars(raised.value)

    hidden, unknown = outcomes("TST"), outcomes("no such company")
    assert hidden == unknown
    assert hidden[0].matches == ()
    assert hidden[1] == vars(i.EvidenceReadError.not_found())
    later = evidence_helpers.make_context(CUTOFF + MICRO, corpus)
    assert len(_pages(pg_conn, later, company, 10, None)) == 1  # the control: visible a tick later


def test_two_parsed_versions_in_one_corpus_fail_closed(pg_conn: Any, evidence_helpers: Any) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    company = _company()
    filing = evidence_helpers.seed_filing(
        pg_conn,
        corpus,
        public_at=CUTOFF,
        published_at=CUTOFF - HOUR,
        entity_id=company.entity_id,
    )
    second = str(uuid.uuid4())
    pg_conn.execute(
        "INSERT INTO document_versions (id, document_id, parser_version, normalizer_version, "
        "canonical_text_key) VALUES (%s, %s, 'p/2', 'n/1', %s)",
        (second, filing.document_id, filing.text_key),
    )
    pg_conn.execute(
        "INSERT INTO corpus_version_documents (corpus_version_id, document_version_id) "
        "VALUES (%s, %s)",
        (corpus, second),
    )
    context = evidence_helpers.make_context(CUTOFF, corpus)
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.code == "integrity_error"):
        _pages(pg_conn, context, company, 10, None)
    resolved = resolve_company(
        pg_conn,
        i.ResolveCompanyRequest(query="TST"),
        context,
        companies={company.entity_id: company},
    )
    assert resolved.matches[0].coverage.visible_filing_count == 1  # documents, not versions


def test_shared_name_cursor_uses_the_visible_issuer_and_can_page_past_the_end(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    company = _company()
    hidden = i.Company(str(uuid.uuid4()), "0000000396", "HID", company.name)
    cohort = {c.entity_id: c for c in (company, hidden)}
    early, late = [
        evidence_helpers.seed_filing(
            pg_conn,
            corpus,
            public_at=stamp,
            published_at=stamp - HOUR,
            entity_id=company.entity_id,
        )
        for stamp in (CUTOFF - HOUR, CUTOFF)
    ]
    evidence_helpers.seed_filing(
        pg_conn,
        corpus,
        public_at=CUTOFF + MICRO,
        published_at=CUTOFF - HOUR,
        entity_id=hidden.entity_id,
    )
    context = evidence_helpers.make_context(CUTOFF, corpus)

    def listing(name: str, cursor: str | None = None) -> i.ListFilingsResult:
        return list_filings(
            pg_conn,
            i.ListFilingsRequest(company=name, limit=1, cursor=cursor),
            context,
            companies=cohort,
            cursors=CURSORS,
        )

    first = listing(company.name)
    assert [filing.document_id for filing in first.filings] == [late.document_id]
    assert first.next_cursor is not None
    for name in (company.name, company.entity_id, company.cik, "tst"):
        second = listing(name, first.next_cursor)
        assert [filing.document_id for filing in second.filings] == [early.document_id]
        assert second.next_cursor is None
    binding = {"tool": "list_filings", "entities": [company.entity_id], "forms": None}
    past_end = CURSORS.encode(
        context, binding, ["1994-01-01T00:00:00+00:00", "00000000-0000-0000-0000-000000000000"]
    )
    empty = listing(company.name, past_end)
    assert (empty.filings, empty.next_cursor) == ((), None)
    invalid = CURSORS.encode(context, binding, [None, None])
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.code == "invalid_input"):
        listing(company.name, invalid)  # must never silently restart at the first page


def test_resolution_does_not_drop_visible_issuers_after_a_hidden_candidate_batch(
    pg_conn: Any, evidence_helpers: Any
) -> None:
    corpus = evidence_helpers.new_corpus(pg_conn)
    cohort = {}
    for n in range(25):
        company = i.Company(str(uuid.uuid4()), f"{n:010d}", None, f"Cohort {n:02d}")
        cohort[company.entity_id] = company
        # First twenty match by name but have only future evidence.
        stamp = CUTOFF + MICRO if n < 20 else CUTOFF
        evidence_helpers.seed_filing(
            pg_conn,
            corpus,
            public_at=stamp,
            published_at=CUTOFF - HOUR,
            entity_id=company.entity_id,
        )
    context = evidence_helpers.make_context(CUTOFF, corpus)
    result = resolve_company(
        pg_conn, i.ResolveCompanyRequest(query="cohort"), context, companies=cohort
    )
    assert [match.company.entity_id for match in result.matches] == list(cohort)[20:]

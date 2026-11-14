"""Guarded citation read (MCP-401, MCP-404): one hidden-or-missing path, code-point
slicing and hash recomputation. Unit level, with a fake at the connection boundary;
``test_strict_visibility_db.py`` proves the SQL predicate on PostgreSQL.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from fel_retrieval import content_sha256
from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.citations import MAX_CANONICAL_BYTES, get_citation

AS_OF = datetime(2024, 3, 7, 14, 30, tzinfo=UTC)
PUBLIC = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
CORPUS = "a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8"
SPAN = "7e4f6d5b-9c8a-4b1d-8e0f-405162738495"
VERSION = "6d3e5c4a-8b7f-4a0c-9d9e-3f4051627384"
DOCUMENT = "5c2d4b3f-7a6e-4f9b-8c8d-2e3f40516273"
COMPANY = i.Company("4b1c3a2e-6f5d-4e8a-9b7c-1d2e3f405162", "0001108524", "CRM", "Salesforce, Inc.")
KEY = "text/sha256/abc"


def _row(start: int, end: int, text_hash: str) -> tuple[Any, ...]:
    return (
        SPAN,
        start,
        end,
        text_hash,
        ["Part II", "Item 7"],
        VERSION,
        "edgar-html-v3",
        KEY,
        DOCUMENT,
        COMPANY.entity_id,
        "0001108524-24-000012",
        "10-K",
        "https://www.sec.gov/Archives/edgar/data/1108524/crm.htm",
        content_sha256("raw"),
        date(2024, 3, 6),
        PUBLIC,
        PUBLIC,
        "acceptance",
    )


@pytest.fixture()
def read(fake_conn: Any, evidence_helpers: Any) -> Any:
    """Call ``get_citation`` over one stored span of the #386 canonical text."""
    text = evidence_helpers.CANONICAL_TEXT

    class Read:
        texts = evidence_helpers.MemoryTexts({KEY: text.encode()})
        companies = {COMPANY.entity_id: COMPANY}
        context = evidence_helpers.make_context(AS_OF, CORPUS)
        conn: Any = None

        def __call__(
            self,
            start: int = 402,
            end: int = 403,
            *,
            text_hash: str | None = None,
            ref: i.SpanRef | None = None,
            rows: int = 1,
        ) -> i.CitationResult:
            stored = content_sha256(text[start:end]) if text_hash is None else text_hash
            self.conn = fake_conn(
                {
                    "source_spans": [_row(start, end, stored)] * rows,
                    "min(d.public_at)": [(PUBLIC, PUBLIC)],
                }
            )
            return get_citation(
                self.conn,
                ref or i.SpanIdRef(SPAN),
                self.context,
                companies=self.companies,
                texts=self.texts,
            )

    return Read()


def _raises(code: str) -> Any:
    return pytest.raises(i.EvidenceReadError, check=lambda e: e.code == code)


def test_a_visible_span_is_returned_with_its_recomputed_hash(read: Any) -> None:
    result = read()
    citation = result.citation
    assert result.hash_verified is True
    assert result.evidence_context is read.context  # returned unchanged
    assert citation == i.Citation(
        span_id=SPAN,
        accession="0001108524-24-000012",
        form="10-K",
        company=COMPANY,
        document_id=DOCUMENT,
        document_version_id=VERSION,
        parser_version="edgar-html-v3",
        section_path=("Part II", "Item 7"),
        start_char=402,
        end_char=403,
        text="B",
        text_hash=content_sha256("B"),
        document_content_hash=content_sha256("raw"),
        source_url="https://www.sec.gov/Archives/edgar/data/1108524/crm.htm",
        filing_date=date(2024, 3, 6),
        accepted_at=PUBLIC,
        public_at=PUBLIC,
        public_at_basis="acceptance",
        timestamp_precision="second",
    )
    assert citation.reader_url is None  # no public scoped reader is deployed (§7.1)
    assert result.coverage_note == i.CoverageNote(
        text=(
            "Searched 10-K filings of Salesforce, Inc. (CIK 0001108524) public from "
            "2024-03-06T21:14:09Z to 2024-03-06T21:14:09Z, visible at 2024-03-07T14:30:00Z."
        ),
        issuers=("0001108524",),
        forms=("10-K",),
        date_range=i.DateRange(from_=PUBLIC, to=PUBLIC),
    )


@pytest.mark.parametrize(
    ("start", "end", "text"),
    [(402, 403, "B"), (401, 403, "\U0001f600B"), (400, 402, "A\U0001f600"), (403, 403, "")],
)
def test_offsets_are_code_points_after_a_supplementary_character(
    read: Any, start: int, end: int, text: str
) -> None:
    # UTF-16 units would put "B" at 403..404 and byte offsets at 405..406.
    citation = read(start, end).citation
    assert (citation.text, citation.text_hash) == (text, content_sha256(text))


def test_the_query_is_bound_to_the_cutoff_and_corpus_on_the_read_role(read: Any) -> None:
    read()
    statements = dict(read.conn.statements)
    span_sql = next(sql for sql in statements if "source_spans" in sql)
    assert statements[span_sql]["as_of"] == AS_OF
    assert statements[span_sql]["corpus"] == CORPUS
    assert read.conn.sql.index("SET LOCAL ROLE fel_public_read") < read.conn.sql.index(span_sql)


def test_hidden_and_missing_references_are_one_code_path_and_one_error(read: Any) -> None:
    with pytest.raises(i.EvidenceReadError) as no_row:
        read(rows=0)
    statements_without_a_row = read.conn.sql
    read.companies = {}
    with pytest.raises(i.EvidenceReadError) as not_served:
        read()  # a visible row whose issuer is outside the served cohort
    for raised in (no_row, not_served):
        assert vars(raised.value) == vars(i.EvidenceReadError.not_found())
    assert not any("min(d.public_at)" in sql for sql in statements_without_a_row)
    assert read.texts.reads == 0  # canonical text is never read for an unresolved reference


def test_an_invalid_reference_does_no_database_work(fake_conn: Any, read: Any) -> None:
    conn = fake_conn()
    for ref in (i.SpanIdRef("not-a-uuid"), i.SpanRangeRef(VERSION, 0, 2**31)):
        with _raises("invalid_input"):
            get_citation(conn, ref, read.context, companies=read.companies, texts=read.texts)
    assert conn.statements == []


def test_approximate_contexts_fail_closed(fake_conn: Any, read: Any, evidence_helpers: Any) -> None:
    conn = fake_conn()
    context = evidence_helpers.make_context(AS_OF, CORPUS, "approximate")
    with _raises("invalid_input"):
        get_citation(conn, i.SpanIdRef(SPAN), context, companies=read.companies, texts=read.texts)
    assert conn.statements == []


def test_a_range_reference_selects_by_version_and_offsets(read: Any) -> None:
    assert read(ref=i.SpanRangeRef(VERSION, 402, 403)).citation.span_id == SPAN
    params = next(p for sql, p in read.conn.statements if "source_spans" in sql)
    assert (params["version"], params["start"], params["end"]) == (VERSION, 402, 403)


def test_integrity_failures_fail_closed(read: Any) -> None:
    with _raises("integrity_error"):
        read(text_hash=content_sha256("A"))  # stored hash is for other text
    with _raises("integrity_error"):
        read(403, 404, text_hash=content_sha256(""))  # offsets run past the text
    with _raises("integrity_error"):
        read(rows=2)  # two stored spans answer one reference
    read.texts.objects[KEY] = b"\xff" + read.texts.objects[KEY]
    with _raises("integrity_error"):
        read()  # canonical text is not UTF-8
    read.texts.objects[KEY] = b"x" * (MAX_CANONICAL_BYTES + 1)
    with _raises("integrity_error"):
        read(0, 1)  # one byte past the 4 MiB read cap
    read.texts.objects[KEY] = b"x" * MAX_CANONICAL_BYTES
    assert read(0, 1).citation.text == "x"
    del read.texts.objects[KEY]
    with pytest.raises(i.EvidenceReadError) as raised:
        read()  # the canonical object is gone
    assert raised.value.code == "integrity_error"
    assert "x" * 8 not in raised.value.message  # never filing text


def test_a_storage_outage_is_retryable_unavailable(read: Any) -> None:
    read.texts.error = OSError("connection reset")
    with pytest.raises(i.EvidenceReadError) as raised:
        read()
    assert (raised.value.code, raised.value.retryable) == ("unavailable", True)
    assert raised.value.retry_after_seconds is not None


def test_a_statement_timeout_is_deadline_exceeded(fake_conn: Any, read: Any) -> None:
    class Cancelled(Exception):
        sqlstate = "57014"

    conn = fake_conn()
    conn.raise_on_execute = Cancelled()
    with _raises("deadline_exceeded"):
        get_citation(
            conn, i.SpanIdRef(SPAN), read.context, companies=read.companies, texts=read.texts
        )
    conn.raise_on_execute = RuntimeError("anything else propagates")
    with pytest.raises(RuntimeError):
        get_citation(
            conn, i.SpanIdRef(SPAN), read.context, companies=read.companies, texts=read.texts
        )

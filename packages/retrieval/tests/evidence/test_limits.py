"""Request limits (design contract §7.4, MCP-407): pure, before any database work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence import limits

SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "schemas"
ID = "7e4f6d5b-9c8a-4b1d-8e0f-405162738495"
ACCESSION = "0001108524-24-000012"
FORMS = tuple(f"F-{n}" for n in range(10))
NAMES = tuple(f"company {n}" for n in range(10))
PERIODS = tuple(f"FY20{n:02d}" for n in range(12))

AT_THE_LIMIT: list[Any] = [
    i.ResolveCompanyRequest(query="q" * 500),
    i.ListFilingsRequest(company="c" * 200, limit=50, forms=FORMS, cursor="k" * 2048),
    i.ListFilingsRequest(company="CRM", limit=1, forms=("10-K/A", "S-1 MEF", "8-K")),
    i.SearchRequest(query="q" * 500, top_k=20, companies=NAMES, forms=FORMS, periods=PERIODS),
    i.SearchRequest(query="revenue", top_k=1, periods=("p" * 32,)),
    i.ReadFilingRequest(document_id=ID, section=tuple("s" * 500 for _ in range(10))),
    i.ReadFilingRequest(accession=ACCESSION, section=ID, cursor="k"),
    i.FactsRequest(company="c" * 200, limit=50, concept="c" * 200, period="p" * 32),
    i.SpanIdRef(ID.upper()),
    i.SpanRangeRef(ID, 0, 2**31 - 1),
]

ONE_PAST_THE_LIMIT: list[tuple[Any, str]] = [
    (i.ResolveCompanyRequest(query="q" * 501), "query"),
    (i.ResolveCompanyRequest(query=""), "query"),
    (i.ResolveCompanyRequest(query="a\x00b"), "query"),
    (i.ListFilingsRequest(company="c" * 201, limit=10), "company"),
    (i.ListFilingsRequest(company="CRM", limit=51), "limit"),
    (i.ListFilingsRequest(company="CRM", limit=0), "limit"),
    (i.ListFilingsRequest(company="CRM", limit=True), "limit"),
    (i.ListFilingsRequest(company="CRM", limit=10, forms=(*FORMS, "F-10")), "forms"),
    (i.ListFilingsRequest(company="CRM", limit=10, forms=()), "forms"),
    (i.ListFilingsRequest(company="CRM", limit=10, forms=("10-K", "10-K")), "forms"),
    (i.ListFilingsRequest(company="CRM", limit=10, forms=("F" * 21,)), "forms"),
    (i.ListFilingsRequest(company="CRM", limit=10, forms=("10-K;",)), "forms"),
    (i.ListFilingsRequest(company="CRM", limit=10, cursor="k" * 2049), "cursor"),
    (i.SearchRequest(query="q", top_k=21), "top_k"),
    (i.SearchRequest(query="q", top_k=0), "top_k"),
    (i.SearchRequest(query="q", top_k=5, companies=(*NAMES, "one more")), "companies"),
    (i.SearchRequest(query="q", top_k=5, companies=("c" * 201,)), "companies"),
    (i.SearchRequest(query="q", top_k=5, periods=(*PERIODS, "FY2030")), "periods"),
    (i.SearchRequest(query="q", top_k=5, periods=("p" * 33,)), "periods"),
    (i.ReadFilingRequest(document_id="not-a-uuid"), "document_id"),
    (i.ReadFilingRequest(accession="1108524-24-12"), "accession"),
    (i.ReadFilingRequest(document_id=ID, section="Item 7"), "section"),
    (i.ReadFilingRequest(document_id=ID, section=tuple("s" for _ in range(11))), "section"),
    (i.ReadFilingRequest(document_id=ID, section=("s" * 501,)), "section"),
    (i.ReadFilingRequest(document_id=ID, section=()), "section"),
    (i.FactsRequest(company="CRM", limit=10, concept="c" * 201), "concept"),
    (i.FactsRequest(company="CRM", limit=10, period="p" * 33), "period"),
    (i.SpanIdRef("7e4f6d5b9c8a4b1d8e0f405162738495"), "span_id"),
    (i.SpanRangeRef("nope", 0, 1), "document_version_id"),
    (i.SpanRangeRef(ID, 0, 2**31), "end_char"),
]


@pytest.mark.parametrize("request_", AT_THE_LIMIT)
def test_requests_at_the_limit_pass(request_: Any) -> None:
    limits.check_request(request_)


@pytest.mark.parametrize(("request_", "field"), ONE_PAST_THE_LIMIT)
def test_one_past_the_limit_is_invalid_input_naming_the_field(request_: Any, field: str) -> None:
    with pytest.raises(i.EvidenceReadError) as raised:
        limits.check_request(request_)
    assert (raised.value.code, raised.value.field, raised.value.retryable) == (
        "invalid_input",
        field,
        False,
    )


def test_an_unknown_request_type_fails_closed() -> None:
    with pytest.raises(TypeError):
        limits.check_request(object())


def test_limits_equal_the_frozen_input_schemas() -> None:
    def props(tool: str) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads((SCHEMAS / f"mcp-{tool}-input.schema.json").read_text())
        return dict(loaded["properties"])

    search, listing, facts = (
        props("search-filings"),
        props("list-filings"),
        props("get-financial-facts"),
    )
    section_path = props("read-filing")["section"]["oneOf"][1]
    assert limits.MAX_QUERY_CHARS == search["query"]["maxLength"]
    assert limits.MAX_QUERY_CHARS == props("resolve-company")["query"]["maxLength"]
    assert limits.MAX_TOP_K == search["top_k"]["maximum"]
    assert limits.MAX_LIMIT == listing["limit"]["maximum"] == facts["limit"]["maximum"]
    assert limits.MAX_COMPANIES == search["companies"]["maxItems"]
    assert limits.MAX_FORMS == search["forms"]["maxItems"] == listing["forms"]["maxItems"]
    assert limits.MAX_PERIODS == search["periods"]["maxItems"]
    assert limits.MAX_NAME_CHARS == listing["company"]["maxLength"] == facts["concept"]["maxLength"]
    assert limits.MAX_NAME_CHARS == search["companies"]["items"]["maxLength"]
    assert limits.MAX_FORM_CHARS == listing["forms"]["items"]["maxLength"]
    assert limits.FORM_PATTERN.pattern == listing["forms"]["items"]["pattern"]
    assert limits.MAX_PERIOD_CHARS == facts["period"]["maxLength"]
    assert limits.MAX_PERIOD_CHARS == search["periods"]["items"]["maxLength"]
    assert limits.MAX_CURSOR_CHARS == listing["cursor"]["maxLength"]
    assert limits.MAX_SECTION_PATH == section_path["maxItems"]
    assert limits.MAX_HEADING_CHARS == section_path["items"]["maxLength"]
    assert limits.ACCESSION_PATTERN.pattern == props("read-filing")["accession"]["pattern"]

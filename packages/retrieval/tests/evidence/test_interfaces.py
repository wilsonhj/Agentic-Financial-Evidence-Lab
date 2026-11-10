"""Contract tests for ``fel_retrieval.evidence.interfaces`` (#392, MCP-107).

Three guarantees, so the Python interface and the frozen MCP schemas cannot
drift:

1. Every dataclass builds from the committed contract fixtures (or valid
   values), is immutable, and enforces the invariants it declares.
2. In-memory fakes satisfy both Protocols structurally.
3. Every interface type's field names equal the ``properties`` of its JSON
   Schema in ``packages/contracts/schemas/``, including ``public_at`` and
   ``public_at_basis``.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fel_retrieval.evidence import interfaces as i

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"


def _load(kind: str, name: str) -> Any:
    suffix = ".schema.json" if kind == "schemas" else ".json"
    return json.loads((CONTRACTS / kind / f"{name}{suffix}").read_text())


def _instant(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


def _day(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


# ---------------------------------------------------------------------------
# Builders from the committed fixtures
# ---------------------------------------------------------------------------


def _context(raw: dict[str, Any]) -> i.EvidenceContext:
    filters: dict[str, Any] = {
        k: tuple(v) if isinstance(v, list) else v for k, v in raw["filters"].items()
    }
    effective = _instant(raw["effective_as_of"])
    assert effective is not None
    return i.EvidenceContext(
        effective_as_of=effective,
        timestamp_mode=raw["timestamp_mode"],
        temporal_guarantee=raw["temporal_guarantee"],
        corpus_version_id=raw["corpus_version_id"],
        index_version_id=raw["index_version_id"],
        parser_version=raw["parser_version"],
        verifier_version=raw["verifier_version"],
        document_version_id=raw["document_version_id"],
        filters=i.ContextFilters(**filters),
    )


def _coverage_note(raw: dict[str, Any]) -> i.CoverageNote:
    return i.CoverageNote(
        text=raw["text"],
        issuers=tuple(raw["issuers"]),
        forms=tuple(raw["forms"]),
        date_range=i.DateRange(
            from_=_instant(raw["date_range"]["from"]), to=_instant(raw["date_range"]["to"])
        ),
    )


def _company(raw: dict[str, Any]) -> i.Company:
    return i.Company(**raw)


def _publication(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted_at": _instant(raw["accepted_at"]),
        "public_at": _instant(raw["public_at"]),
        "public_at_basis": raw["public_at_basis"],
    }


def _citation(raw: dict[str, Any]) -> i.Citation:
    filing_date = _day(raw["filing_date"])
    assert filing_date is not None
    return i.Citation(
        span_id=raw["span_id"],
        accession=raw["accession"],
        form=raw["form"],
        company=_company(raw["company"]),
        document_id=raw["document_id"],
        document_version_id=raw["document_version_id"],
        parser_version=raw["parser_version"],
        section_path=tuple(raw["section_path"]),
        start_char=raw["start_char"],
        end_char=raw["end_char"],
        text=raw["text"],
        text_hash=raw["text_hash"],
        document_content_hash=raw["document_content_hash"],
        source_url=raw["source_url"],
        filing_date=filing_date,
        timestamp_precision=raw["timestamp_precision"],
        reader_url=raw.get("reader_url"),
        offset_unit=raw["offset_unit"],
        untrusted_source_text=raw["untrusted_source_text"],
        **_publication(raw),
    )


def _filing_meta(raw: dict[str, Any]) -> i.FilingMeta:
    filing_date = _day(raw["filing_date"])
    assert filing_date is not None
    return i.FilingMeta(
        entity_id=raw["entity_id"],
        accession=raw["accession"],
        form=raw["form"],
        filing_date=filing_date,
        timestamp_precision=raw["timestamp_precision"],
        period_end=_day(raw["period_end"]),
        document_id=raw["document_id"],
        document_version_id=raw["document_version_id"],
        source_url=raw["source_url"],
        content_hash=raw["content_hash"],
        amends=raw["amends"],
        **_publication(raw),
    )


def _verdict(raw: dict[str, Any]) -> i.CitationVerdict:
    numeric = raw.get("numeric_checks")
    return i.CitationVerdict(
        index=raw["index"],
        checks=i.IntegrityChecks(**raw["checks"]),
        reason=raw["reason"],
        edge_status=raw["edge_status"],
        numeric_checks=None if numeric is None else i.NumericChecks(**numeric),
    )


def _report(raw: dict[str, Any]) -> i.VerificationReport:
    return i.VerificationReport(
        verifier=raw["verifier"],
        claim_status=raw["claim_status"],
        citations=tuple(_verdict(c) for c in raw["citations"]),
        quote_normalization=raw["quote_normalization"],
        semantic_entailment=raw["semantic_entailment"],
        entailment_method=raw["entailment_method"],
    )


def _live_status(raw: dict[str, Any]) -> i.LiveStatus:
    observed = _instant(raw["observed_at"])
    assert observed is not None
    return i.LiveStatus(
        observed_at=observed,
        active_corpus_version_id=raw["active_corpus_version_id"],
        retained_corpus_versions=tuple(
            i.CorpusVersionRow(r["id"], r["status"], _instant(r["published_at"]))
            for r in raw["retained_corpus_versions"]
        ),
        active_index_version_id=raw["active_index_version_id"],
        retained_index_versions=tuple(
            i.IndexVersionRow(
                r["id"], r["corpus_version_id"], r["status"], _instant(r["published_at"])
            )
            for r in raw["retained_index_versions"]
        ),
        verifier_versions=tuple(raw["verifier_versions"]),
        known_limitations=tuple(i.Limitation(**lim) for lim in raw["known_limitations"]),
        replayable=raw["replayable"],
    )


CONTEXT = _context(_load("fixtures", "mcp-evidence-context"))
NOTE = _coverage_note(_load("fixtures", "mcp-resolve-company-output")["coverage_note"])
CITATION = _citation(_load("fixtures", "mcp-citation"))


# ---------------------------------------------------------------------------
# 1. Construction, immutability and declared invariants
# ---------------------------------------------------------------------------


def test_fixture_citation_and_context_build() -> None:
    assert CITATION.public_at == CITATION.accepted_at
    assert CITATION.public_at_basis == "acceptance"
    assert CITATION.offset_unit == "unicode_code_point"
    assert CITATION.end_char - CITATION.start_char == len(CITATION.text)
    assert CONTEXT.temporal_guarantee == "strict"
    with pytest.raises(dataclasses.FrozenInstanceError):
        CITATION.public_at = None  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        CONTEXT.effective_as_of = datetime.now(UTC)  # type: ignore[misc]


def test_list_filings_fixture_builds_both_publication_bases() -> None:
    raw = _load("fixtures", "mcp-list-filings-output")
    filings = tuple(_filing_meta(f) for f in raw["filings"])
    result = i.ListFilingsResult(
        evidence_context=_context(raw["evidence_context"]),
        coverage_note=_coverage_note(raw["coverage_note"]),
        filings=filings,
        next_cursor=raw["next_cursor"],
    )
    by_basis = {f.public_at_basis: f for f in result.filings}
    after_hours = by_basis["next_session_open"]
    assert after_hours.accepted_at is not None and after_hours.public_at is not None
    assert after_hours.public_at > after_hours.accepted_at
    assert by_basis["acceptance"].public_at == by_basis["acceptance"].accepted_at


def test_every_output_fixture_builds() -> None:
    resolve = _load("fixtures", "mcp-resolve-company-output")
    match = resolve["matches"][0]
    first, last = (match["coverage"][k] for k in ("first_visible_filing", "last_visible_filing"))

    def filing_ref(raw: dict[str, Any]) -> i.FilingRef:
        filing_date = _day(raw["filing_date"])
        assert filing_date is not None
        return i.FilingRef(raw["accession"], raw["form"], filing_date, **_publication(raw))

    i.ResolveCompanyResult(
        evidence_context=_context(resolve["evidence_context"]),
        coverage_note=_coverage_note(resolve["coverage_note"]),
        matches=(
            i.CompanyMatch(
                company=_company(match["company"]),
                coverage=i.CompanyCoverage(
                    first_visible_filing=filing_ref(first),
                    last_visible_filing=filing_ref(last),
                    visible_forms=tuple(match["coverage"]["visible_forms"]),
                    visible_filing_count=match["coverage"]["visible_filing_count"],
                ),
            ),
        ),
    )

    search = _load("fixtures", "mcp-search-filings-output")["results"][0]
    hit = i.SearchHit(
        rank=search["rank"],
        kind=search["kind"],
        fused_score=search["fused_score"],
        lanes=tuple(i.LaneContribution(**lane) for lane in search["lanes"]),
        citation=_citation(search["citation"]),
    )
    i.SearchResult(CONTEXT, NOTE, (hit,))

    read = _load("fixtures", "mcp-read-filing-output")
    doc = read["document"]
    filing_date = _day(doc["filing_date"])
    assert filing_date is not None
    i.ReadFilingResult(
        evidence_context=_context(read["evidence_context"]),
        coverage_note=_coverage_note(read["coverage_note"]),
        document=i.DocumentHeader(
            document_id=doc["document_id"],
            document_version_id=doc["document_version_id"],
            parser_version=doc["parser_version"],
            company=_company(doc["company"]),
            accession=doc["accession"],
            form=doc["form"],
            filing_date=filing_date,
            timestamp_precision=doc["timestamp_precision"],
            source_url=doc["source_url"],
            document_content_hash=doc["document_content_hash"],
            **_publication(doc),
        ),
        section=i.SectionRef(
            read["section"]["section_id"],
            tuple(read["section"]["heading_path"]),
            read["section"]["start_char"],
            read["section"]["end_char"],
        ),
        chunk=i.TextChunk(**read["chunk"]),
        spans=tuple(_citation(c) for c in read["spans"]),
        outline=tuple(
            i.OutlineEntry(o["section_id"], tuple(o["heading_path"]), o["ord"])
            for o in read["outline"]
        ),
        next_cursor=read["next_cursor"],
    )

    i.CitationResult(CONTEXT, NOTE, CITATION)

    fact = _load("fixtures", "mcp-get-financial-facts-output")["facts"][0]
    period = fact["period"]
    i.FactsResult(
        CONTEXT,
        NOTE,
        (
            i.Fact(
                fact_id=fact["fact_id"],
                concept=fact["concept"],
                label=fact["label"],
                value=fact["value"],
                unit=fact["unit"],
                scale=fact["scale"],
                period=i.FactPeriod(
                    period["type"],
                    _day(period["instant"]),
                    _day(period["start"]),
                    _day(period["end"]),
                ),
                dimensions=fact["dimensions"],
                reported_or_derived=fact["reported_or_derived"],
                citation=_citation(fact["citation"]),
                restated_by=tuple(fact["restated_by"]),
                duplicate_of=fact["duplicate_of"],
            ),
        ),
        None,
    )

    verify = _load("fixtures", "mcp-verify-claim-output")
    report = _report(verify["report"])
    assert report.semantic_entailment == "not_evaluated"
    i.VerifyClaimResult(CONTEXT, NOTE, report)

    status = _load("fixtures", "mcp-get-corpus-status-output")
    coverage = status["coverage"]
    effective = _instant(coverage["effective_as_of"])
    assert effective is not None
    i.CorpusCoverageResult(
        evidence_context=_context(status["evidence_context"]),
        coverage_note=_coverage_note(status["coverage_note"]),
        coverage=i.CorpusCoverage(
            effective_as_of=effective,
            issuers=tuple(
                i.IssuerCoverage(
                    _company(x["company"]),
                    x["visible_filing_count"],
                    _day(x["first_filing_date"]),
                    _day(x["last_filing_date"]),
                )
                for x in coverage["issuers"]
            ),
            date_range=i.DateRange(
                _instant(coverage["date_range"]["from"]), _instant(coverage["date_range"]["to"])
            ),
            timestamp_precision_mix=coverage["timestamp_precision_mix"],
        ),
    )
    live = _live_status(status["live_status"])
    assert live.replayable is False
    assert i.REQUIRED_LIMITATION_CODES <= {lim.code for lim in live.known_limitations}


def test_request_types_build_from_input_fixtures() -> None:
    raw = _load("fixtures", "mcp-verify-claim-input")
    citations = []
    for c in raw["citations"]:
        ref: i.SpanRef = (
            i.SpanIdRef(c["span_id"])
            if "span_id" in c
            else i.SpanRangeRef(c["document_version_id"], c["start_char"], c["end_char"])
        )
        citations.append(i.CitedSpan(ref, c.get("quote")))
    numeric = raw["numeric"]
    request = i.VerifyClaimRequest(
        claim=raw["claim"],
        citations=tuple(citations),
        numeric=i.ClaimNumeric(
            value=Decimal(numeric["value"]),
            unit=numeric["unit"],
            scale=numeric["scale"],
            period=numeric["period"],
            concept=numeric["concept"],
        ),
    )
    assert request.numeric is not None and request.numeric.scale == 0
    i.ResolveCompanyRequest(_load("fixtures", "mcp-resolve-company-input")["query"])
    listing = _load("fixtures", "mcp-list-filings-input")
    i.ListFilingsRequest(listing["company"], listing["limit"], tuple(listing["forms"]))
    search = _load("fixtures", "mcp-search-filings-input")
    i.SearchRequest(search["query"], search["top_k"], tuple(search["companies"]))
    i.ReadFilingRequest(accession="0001108524-24-000012", section=("Part II",))
    facts = _load("fixtures", "mcp-get-financial-facts-input")
    i.FactsRequest(facts["company"], facts["limit"], facts["concept"], facts["period"])
    context_request = i.ContextRequest(
        request_time=datetime(2026, 11, 10, tzinfo=UTC), as_of=date(2024, 3, 7)
    )
    assert context_request.timestamp_mode == "strict"
    assert context_request.filters == i.ContextFilters()


@pytest.mark.parametrize(
    ("accepted", "public", "basis", "precision", "message"),
    [
        (None, None, None, "second", "requires accepted_at"),
        ("2024-03-06T20:00:00Z", None, "acceptance", "second", "requires accepted_at"),
        ("2024-03-06T20:00:00Z", "2024-03-06T19:00:00Z", "next_session_open", "second", "precedes"),
        ("2024-03-05T23:00:00Z", "2024-03-06T11:00:00Z", "acceptance", "second", "iff"),
        ("2024-03-06T20:00:00Z", "2024-03-06T20:00:00Z", "next_session_open", "second", "iff"),
        ("2024-03-06T20:00:00", "2024-03-06T20:00:00", "acceptance", "second", "aware"),
    ],
)
def test_publication_invariants_mirror_0012_checks(
    accepted: str | None, public: str | None, basis: Any, precision: Any, message: str
) -> None:
    def parse(v: str | None) -> datetime | None:
        return None if v is None else datetime.fromisoformat(v.replace("Z", "+00:00"))

    with pytest.raises(ValueError, match=message):
        dataclasses.replace(
            CITATION,
            accepted_at=parse(accepted),
            public_at=parse(public),
            public_at_basis=basis,
            timestamp_precision=precision,
        )


def test_approximate_precision_admits_unknown_publication_time() -> None:
    approx = dataclasses.replace(
        CITATION,
        accepted_at=None,
        public_at=None,
        public_at_basis=None,
        timestamp_precision="approximate",
    )
    assert approx.public_at is None


def test_other_declared_invariants() -> None:
    with pytest.raises(ValueError, match="offsets"):
        dataclasses.replace(CITATION, start_char=10, end_char=5)
    with pytest.raises(ValueError, match="span range"):
        i.SpanRangeRef("dv", 5, 4)
    with pytest.raises(ValueError, match="aware"):
        i.ContextRequest(request_time=datetime(2026, 11, 10))
    with pytest.raises(ValueError, match="aware"):
        i.ContextRequest(
            request_time=datetime(2026, 11, 10, tzinfo=UTC), as_of=datetime(2024, 3, 7)
        )
    with pytest.raises(ValueError, match="guarantee"):
        dataclasses.replace(CONTEXT, timestamp_mode="approximate")
    assert dataclasses.replace(
        CONTEXT, timestamp_mode="approximate", temporal_guarantee="none"
    ).temporal_guarantee == ("none")
    with pytest.raises(ValueError, match="exactly one"):
        i.ReadFilingRequest()
    with pytest.raises(ValueError, match="exactly one"):
        i.ReadFilingRequest(document_id="d", accession="a")
    with pytest.raises(ValueError, match="scale"):
        i.ClaimNumeric(Decimal("1"), "USD", 2, "FY2024")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        i.ClaimNumeric(Decimal("NaN"), "USD", 0, "FY2024")
    with pytest.raises(ValueError, match="1 to 10"):
        i.VerifyClaimRequest("claim", ())
    with pytest.raises(ValueError, match="1 to 10"):
        i.VerifyClaimRequest("claim", tuple(i.CitedSpan(i.SpanIdRef("s")) for _ in range(11)))
    fact = _load("fixtures", "mcp-get-financial-facts-output")["facts"][0]
    for bad in ("1e6", "NaN", "1.", "", "1_000"):
        with pytest.raises(ValueError, match="decimal"):
            i.Fact(
                fact["fact_id"],
                "c",
                None,
                bad,
                "USD",
                0,
                i.FactPeriod("instant", date(2024, 1, 31), None, None),
                {},
                "reported",
                CITATION,
                (),
                None,
            )
    status = _load("fixtures", "mcp-get-corpus-status-output")
    for code in sorted(i.REQUIRED_LIMITATION_CODES):
        raw = json.loads(json.dumps(status["live_status"]))
        raw["known_limitations"] = [x for x in raw["known_limitations"] if x["code"] != code]
        with pytest.raises(ValueError, match=code):
            _live_status(raw)
    with pytest.raises(ValueError, match="effective_as_of"):
        i.CorpusCoverageResult(
            CONTEXT,
            NOTE,
            i.CorpusCoverage(datetime(2020, 1, 1, tzinfo=UTC), (), i.DateRange(None, None), {}),
        )


def test_citation_verdict_shapes() -> None:
    hidden = i.CitationVerdict.not_visible(3)
    assert hidden == i.CitationVerdict(
        3, i.IntegrityChecks(False, None, None), "not_found", "irrelevant", None
    )
    for change in ({"edge_status": "partial"}, {"reason": None}):
        with pytest.raises(ValueError, match="uninformative"):
            dataclasses.replace(hidden, **change)


def test_citation_verdict_rejects_leaky_or_inconsistent_shapes() -> None:
    hidden_checks = i.IntegrityChecks(False, None, None)
    with pytest.raises(ValueError, match="uninformative"):
        i.CitationVerdict(0, hidden_checks, "not_found", "partial", None)
    with pytest.raises(ValueError, match="uninformative"):
        i.CitationVerdict(0, i.IntegrityChecks(False, False, None), "not_found", "irrelevant", None)
    ok = i.IntegrityChecks(True, True, None)
    i.CitationVerdict(0, ok, None, "partial", None)
    with pytest.raises(ValueError, match="first failed"):
        i.CitationVerdict(0, ok, "hash_mismatch", "partial", None)
    with pytest.raises(ValueError, match="first failed"):
        i.CitationVerdict(0, i.IntegrityChecks(True, False, None), None, "irrelevant", None)
    with pytest.raises(ValueError, match="first failed"):
        i.CitationVerdict(0, ok, "not_found", "irrelevant", None)
    i.CitationVerdict(
        0, i.IntegrityChecks(True, True, False), "quote_not_found", "irrelevant", None
    )
    with pytest.raises(ValueError, match="index"):
        i.CitationVerdict.not_visible(10)


def test_error_rules_mirror_mcp_error_schema() -> None:
    not_found = i.EvidenceReadError.not_found()
    assert (not_found.code, not_found.field, not_found.retry_after_seconds) == (
        "not_found",
        None,
        None,
    )
    assert str(not_found) == i.NOT_FOUND_MESSAGE
    with pytest.raises(ValueError, match="fixed message"):
        i.EvidenceReadError(
            "not_found", "Document hidden.", retryable=False, recovery=i.NOT_FOUND_RECOVERY
        )
    with pytest.raises(ValueError, match="retryable"):
        i.EvidenceReadError("rate_limited", "m", retryable=False, recovery="r")
    with pytest.raises(ValueError, match="retry_after_seconds"):
        i.EvidenceReadError("rate_limited", "m", retryable=True, recovery="r")
    with pytest.raises(ValueError, match="must not carry"):
        i.EvidenceReadError(
            "cursor_expired", "m", retryable=False, recovery="r", retry_after_seconds=1
        )
    with pytest.raises(ValueError, match="requires field"):
        i.EvidenceReadError("pin_unavailable", "m", retryable=False, recovery="r")
    pin = i.EvidenceReadError(
        "pin_unavailable", "m", retryable=False, recovery="r", field="corpus_version_id"
    )
    assert pin.field == "corpus_version_id"
    schema_codes = _load("schemas", "mcp-error")["properties"]["error"]["properties"]["code"][
        "enum"
    ]
    assert list(i.ERROR_RULES) == schema_codes


# ---------------------------------------------------------------------------
# 2. Protocol fakes
# ---------------------------------------------------------------------------


class FakeEvidenceReadService:
    """Minimal in-memory service: one visible citation, nothing else."""

    def resolve_context(self, request: i.ContextRequest) -> i.EvidenceContext:
        if request.corpus_version_id not in (None, CONTEXT.corpus_version_id):
            raise i.EvidenceReadError(
                "pin_unavailable",
                "Corpus version is not available.",
                retryable=False,
                recovery="Omit the pin.",
                field="corpus_version_id",
            )
        return CONTEXT

    def resolve_company(
        self, request: i.ResolveCompanyRequest, context: i.EvidenceContext
    ) -> i.ResolveCompanyResult:
        return i.ResolveCompanyResult(context, NOTE, ())

    def list_filings(
        self, request: i.ListFilingsRequest, context: i.EvidenceContext
    ) -> i.ListFilingsResult:
        return i.ListFilingsResult(context, NOTE, (), None)

    def search(self, request: i.SearchRequest, context: i.EvidenceContext) -> i.SearchResult:
        return i.SearchResult(context, NOTE, ())

    def read_filing(
        self, request: i.ReadFilingRequest, context: i.EvidenceContext
    ) -> i.ReadFilingResult:
        raise i.EvidenceReadError.not_found()

    def get_citation(self, ref: i.SpanRef, context: i.EvidenceContext) -> i.CitationResult:
        if isinstance(ref, i.SpanIdRef) and ref.span_id == CITATION.span_id:
            return i.CitationResult(context, NOTE, CITATION)
        raise i.EvidenceReadError.not_found()

    def get_facts(self, request: i.FactsRequest, context: i.EvidenceContext) -> i.FactsResult:
        return i.FactsResult(context, NOTE, (), None)

    def corpus_coverage(self, context: i.EvidenceContext) -> i.CorpusCoverageResult:
        coverage = i.CorpusCoverage(context.effective_as_of, (), i.DateRange(None, None), {})
        return i.CorpusCoverageResult(context, NOTE, coverage)

    def live_status(self, observed_at: datetime) -> i.LiveStatus:
        return i.LiveStatus(
            observed_at,
            None,
            (),
            None,
            (),
            ("deterministic-v1",),
            tuple(i.Limitation(code, code) for code in sorted(i.REQUIRED_LIMITATION_CODES)),
        )


class FakeReportBuilder:
    def build(
        self, request: i.VerifyClaimRequest, context: i.EvidenceContext
    ) -> i.VerifyClaimResult:
        verdicts = tuple(i.CitationVerdict.not_visible(n) for n in range(len(request.citations)))
        report = i.VerificationReport(context.verifier_version, "unsupported", verdicts, "ws-v1")
        return i.VerifyClaimResult(context, NOTE, report)


def test_fakes_satisfy_the_protocols() -> None:
    service: i.EvidenceReadService = FakeEvidenceReadService()
    builder: i.VerificationReportBuilder = FakeReportBuilder()
    assert isinstance(service, i.EvidenceReadService)
    assert isinstance(builder, i.VerificationReportBuilder)
    assert not isinstance(object(), i.EvidenceReadService)

    now = datetime(2026, 11, 10, tzinfo=UTC)
    context = service.resolve_context(i.ContextRequest(request_time=now))
    with pytest.raises(i.EvidenceReadError) as pin:
        service.resolve_context(i.ContextRequest(request_time=now, corpus_version_id="retired"))
    assert pin.value.code == "pin_unavailable"
    assert service.resolve_company(i.ResolveCompanyRequest("CRM"), context).matches == ()
    assert service.list_filings(i.ListFilingsRequest("CRM", 10), context).filings == ()
    assert service.search(i.SearchRequest("revenue", 5), context).results == ()
    assert service.get_facts(i.FactsRequest("CRM", 10), context).facts == ()
    assert service.get_citation(i.SpanIdRef(CITATION.span_id), context).hash_verified is True
    hidden = i.SpanIdRef("00000000-0000-4000-8000-00000000dead")
    missing = i.SpanRangeRef("00000000-0000-4000-8000-00000000beef", 0, 1)
    errors = []
    for call in (
        lambda: service.get_citation(hidden, context),
        lambda: service.get_citation(missing, context),
        lambda: service.read_filing(i.ReadFilingRequest(document_id="x"), context),
    ):
        with pytest.raises(i.EvidenceReadError) as err:
            call()
        errors.append((err.value.code, err.value.message, err.value.recovery, err.value.field))
    assert len(set(errors)) == 1
    assert service.corpus_coverage(context).coverage.effective_as_of == context.effective_as_of
    assert service.live_status(now).replayable is False
    result = builder.build(
        i.VerifyClaimRequest("claim", (i.CitedSpan(hidden), i.CitedSpan(missing))), context
    )
    first, second = result.report.citations
    assert dataclasses.replace(first, index=0) == dataclasses.replace(second, index=0)


# ---------------------------------------------------------------------------
# 3. Field-name parity with the frozen JSON Schemas
# ---------------------------------------------------------------------------

CONTEXT_INPUTS = {
    "as_of",
    "timestamp_mode",
    "corpus_version_id",
    "index_version_id",
    "verifier_version",
}
PY_ALIASES = {"from_": "from"}


def _unwrap(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("oneOf", "anyOf"):
        if key in node:
            for variant in node[key]:
                if variant.get("type") in ("object", "array"):
                    return dict(variant)
    return node


def _props(schema_name: str, *path: str) -> set[str]:
    node = _unwrap(_load("schemas", schema_name))
    for key in path:
        node = _unwrap(node["items"] if key == "[]" else node["properties"][key])
    return set(node["properties"])


def _fields(cls: type) -> set[str]:
    return {PY_ALIASES.get(f.name, f.name) for f in dataclasses.fields(cls)}


PARITY: list[tuple[type, str, tuple[str, ...]]] = [
    (i.EvidenceContext, "mcp-evidence-context", ()),
    (i.ContextFilters, "mcp-evidence-context", ("filters",)),
    (i.Citation, "mcp-citation", ()),
    (i.Company, "mcp-citation", ("company",)),
    (i.CoverageNote, "mcp-resolve-company-output", ("coverage_note",)),
    (i.DateRange, "mcp-resolve-company-output", ("coverage_note", "date_range")),
    (i.ResolveCompanyResult, "mcp-resolve-company-output", ()),
    (i.CompanyMatch, "mcp-resolve-company-output", ("matches", "[]")),
    (i.CompanyCoverage, "mcp-resolve-company-output", ("matches", "[]", "coverage")),
    (
        i.FilingRef,
        "mcp-resolve-company-output",
        ("matches", "[]", "coverage", "first_visible_filing"),
    ),
    (i.ListFilingsResult, "mcp-list-filings-output", ()),
    (i.FilingMeta, "mcp-list-filings-output", ("filings", "[]")),
    (i.SearchResult, "mcp-search-filings-output", ()),
    (i.SearchHit, "mcp-search-filings-output", ("results", "[]")),
    (i.LaneContribution, "mcp-search-filings-output", ("results", "[]", "lanes", "[]")),
    (i.ReadFilingResult, "mcp-read-filing-output", ()),
    (i.DocumentHeader, "mcp-read-filing-output", ("document",)),
    (i.SectionRef, "mcp-read-filing-output", ("section",)),
    (i.TextChunk, "mcp-read-filing-output", ("chunk",)),
    (i.OutlineEntry, "mcp-read-filing-output", ("outline", "[]")),
    (i.CitationResult, "mcp-get-citation-output", ()),
    (i.FactsResult, "mcp-get-financial-facts-output", ()),
    (i.Fact, "mcp-get-financial-facts-output", ("facts", "[]")),
    (i.FactPeriod, "mcp-get-financial-facts-output", ("facts", "[]", "period")),
    (i.CorpusCoverage, "mcp-get-corpus-status-output", ("coverage",)),
    (i.IssuerCoverage, "mcp-get-corpus-status-output", ("coverage", "issuers", "[]")),
    (i.LiveStatus, "mcp-get-corpus-status-output", ("live_status",)),
    (
        i.CorpusVersionRow,
        "mcp-get-corpus-status-output",
        ("live_status", "retained_corpus_versions", "[]"),
    ),
    (
        i.IndexVersionRow,
        "mcp-get-corpus-status-output",
        ("live_status", "retained_index_versions", "[]"),
    ),
    (
        i.Limitation,
        "mcp-get-corpus-status-output",
        ("live_status", "known_limitations", "[]"),
    ),
    (i.VerificationReport, "mcp-verification-report", ()),
    (i.VerifyClaimResult, "mcp-verify-claim-output", ()),
    (i.ClaimNumeric, "mcp-verify-claim-input", ("numeric",)),
]


@pytest.mark.parametrize(
    ("cls", "schema", "path"), PARITY, ids=lambda v: getattr(v, "__name__", None)
)
def test_field_names_equal_schema_properties(cls: type, schema: str, path: tuple[str, ...]) -> None:
    assert _fields(cls) == _props(schema, *path)


def test_publication_fields_travel_with_accepted_at() -> None:
    for cls, *_ in PARITY:
        names = _fields(cls)
        if "accepted_at" in names:
            assert {"public_at", "public_at_basis"} <= names, cls.__name__


def test_composite_parity() -> None:
    report = _load("schemas", "mcp-verification-report")["$defs"]
    assert _fields(i.CitationVerdict) == set(report["notVisible"]["properties"]) | set(
        report["visible"]["properties"]
    )
    assert _fields(i.IntegrityChecks) == set(
        report["visible"]["properties"]["checks"]["properties"]
    )
    numeric = _unwrap(report["visible"]["properties"]["numeric_checks"])
    assert _fields(i.NumericChecks) == set(numeric["properties"])
    assert _fields(i.CorpusCoverageResult) | {"live_status"} == _props(
        "mcp-get-corpus-status-output"
    )
    error = set(_load("schemas", "mcp-error")["properties"]["error"]["properties"])
    params = set(inspect.signature(i.EvidenceReadError.__init__).parameters) - {"self"}
    assert params == error


@pytest.mark.parametrize(
    ("schema", "request_fields"),
    [
        ("mcp-resolve-company-input", _fields(i.ResolveCompanyRequest)),
        ("mcp-list-filings-input", _fields(i.ListFilingsRequest)),
        ("mcp-search-filings-input", _fields(i.SearchRequest)),
        ("mcp-read-filing-input", _fields(i.ReadFilingRequest)),
        ("mcp-get-citation-input", _fields(i.SpanIdRef) | _fields(i.SpanRangeRef)),
        ("mcp-get-financial-facts-input", _fields(i.FactsRequest)),
        ("mcp-verify-claim-input", _fields(i.VerifyClaimRequest)),
        ("mcp-get-corpus-status-input", set()),
    ],
)
def test_input_parity(schema: str, request_fields: set[str]) -> None:
    props = _props(schema)
    assert CONTEXT_INPUTS <= _fields(i.ContextRequest)
    assert props - request_fields <= CONTEXT_INPUTS
    assert request_fields <= props


def test_cited_span_parity() -> None:
    items = _load("schemas", "mcp-verify-claim-input")["properties"]["citations"]["items"]
    variants = set().union(*(set(v["properties"]) for v in items["oneOf"]))
    assert variants == _fields(i.SpanIdRef) | _fields(i.SpanRangeRef) | {"quote"}
    assert _fields(i.CitedSpan) == {"ref", "quote"}

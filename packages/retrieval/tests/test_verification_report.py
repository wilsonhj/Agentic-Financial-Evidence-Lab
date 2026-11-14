"""The ``mcp-verification-report/v1`` builder (#396, MCP-502 and MCP-503).

Every report built here is validated against the frozen JSON Schema in
``packages/contracts``. The rule table follows the design contract §7.2 row by
row; the remaining tests cover the integrity checks in front of the rules, the
no-oracle shape, and the inputs the builder must refuse rather than guess at.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.generation import ContextItem, NumericTuple
from fel_retrieval.verification import DeterministicCitationVerifier
from fel_retrieval.verification_report import (
    QUOTE_NORMALIZATION,
    DeterministicReportBuilder,
    EvidenceFact,
    SpanEvidence,
    report_to_json,
)

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
SCHEMA = json.loads((CONTRACTS / "schemas" / "mcp-verification-report.schema.json").read_text())
FIXTURE = json.loads((CONTRACTS / "fixtures" / "mcp-verification-report.json").read_text())
CONTEXT = i.EvidenceContext(
    effective_as_of=datetime(2024, 3, 7, 14, 30, tzinfo=UTC),
    timestamp_mode="strict",
    temporal_guarantee="strict",
    corpus_version_id="a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8",
    index_version_id=None,
    parser_version=None,
    verifier_version="deterministic-v1",
    document_version_id=None,
    filters=i.ContextFilters(),
)
NOTE = i.CoverageNote(
    "Searched the visible corpus.", ("0001108524",), ("10-K",), i.DateRange(None, None)
)
ALL_TRUE = {"value": True, "unit": True, "period": True, "sign": True, "scale": True}
TEXT = "Revenue was 100"
NOT_VISIBLE = {
    "checks": {"visible": False, "hash_valid": None, "quote_found": None},
    "reason": "not_found",
    "edge_status": "irrelevant",
}


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _fact(
    value: Any = "100", unit: str = "USD", period: str = "FY2025", scale: Any = 6
) -> EvidenceFact:
    return EvidenceFact(value=value, unit=unit, period=period, scale=scale)


def _numeric(
    value: str = "100", unit: str = "USD", period: str = "FY2025", scale: Any = 6
) -> i.ClaimNumeric:
    return i.ClaimNumeric(value=Decimal(value), unit=unit, scale=scale, period=period)


def _span(
    text: str = TEXT, fact: EvidenceFact | None = None, *, text_hash: str | None = None
) -> SpanEvidence:
    return SpanEvidence("span", "dv", text, text_hash or _hash(text), fact)


class FakeSource:
    """Visible spans by reference; ``hidden`` stands for spans past the cutoff."""

    def __init__(self, spans: dict[str, SpanEvidence], hidden: tuple[str, ...] = ()) -> None:
        self.spans = {key: span for key, span in spans.items() if key not in hidden}
        self.calls = 0

    def resolve_span(self, ref: i.SpanRef, context: i.EvidenceContext) -> SpanEvidence | None:
        self.calls += 1
        return self.spans.get(ref.span_id) if isinstance(ref, i.SpanIdRef) else None

    def coverage_note(self, context: i.EvidenceContext) -> i.CoverageNote:
        return NOTE


def _build(
    claim: str,
    spans: dict[str, SpanEvidence],
    *,
    numeric: i.ClaimNumeric | None = None,
    quotes: dict[str, str] | None = None,
    cite: tuple[str, ...] | None = None,
    hidden: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a report, check it against the schema, and return its JSON form."""
    cited = tuple(
        i.CitedSpan(i.SpanIdRef(key), (quotes or {}).get(key)) for key in cite or tuple(spans)
    )
    result = DeterministicReportBuilder(FakeSource(spans, hidden)).build(
        i.VerifyClaimRequest(claim, cited, numeric), CONTEXT
    )
    assert result.evidence_context is CONTEXT and result.coverage_note is NOTE
    payload = report_to_json(result.report)
    Draft202012Validator(SCHEMA).validate(payload)
    assert [c["index"] for c in payload["citations"]] == list(range(len(cited)))
    return payload


# --- MCP-503: one row per rule of the design contract §7.2 -------------------
BIG = "123456789012345678901234567890123"  # 33 digits; the rows append a 34th


def _but(*failed: str) -> dict[str, bool]:
    return {**ALL_TRUE, **dict.fromkeys(failed, False)}


Rule = tuple[str, str, i.ClaimNumeric | None, EvidenceFact | None, str, Any, str]
# rule -> (claim, evidence text, asserted numeric, evidence fact,
#          expected edge, numeric checks, claim status)
# fmt: off
RULES: dict[str, Rule] = {
    "irrelevant: digit claim, evidence tuple, no asserted numeric":
        (TEXT, TEXT, None, _fact(), "irrelevant", None, "unsupported"),
    "irrelevant: asserted numeric, evidence has no tuple":
        (TEXT, TEXT, _numeric(), None, "irrelevant", None, "unsupported"),
    "contradictory: value differs":
        (TEXT, TEXT, _numeric("999"), _fact(), "contradictory", _but("value"), "contradicted"),
    "contradictory: unit differs":
        (TEXT, TEXT, _numeric(unit="EUR"), _fact(), "contradictory", _but("unit"), "contradicted"),
    "contradictory: period differs":
        (TEXT, TEXT, _numeric(period="FY2024"), _fact(), "contradictory", _but("period"),
         "contradicted"),
    "contradictory: sign differs":
        (TEXT, TEXT, _numeric("-100"), _fact(), "contradictory", _but("sign"), "contradicted"),
    "contradictory: scale differs":
        (TEXT, TEXT, _numeric(scale=3), _fact(), "contradictory", _but("scale"), "contradicted"),
    "contradictory: the same amount written at another scale is still a mismatch":
        (TEXT, TEXT, _numeric("0.1", scale=9), _fact(), "contradictory", _but("value", "scale"),
         "contradicted"),
    "contradictory: magnitudes differ only in the 34th digit":
        (TEXT, TEXT, _numeric(BIG + "4"), _fact(BIG + "5"), "contradictory", _but("value"),
         "contradicted"),
    "entailed: whole-evidence text identity":
        ("Revenue  grew\n", "Revenue grew", None, None, "entailed", None, "supported"),
    "entailed: identity with the numeric match as precondition":
        (TEXT, TEXT, _numeric("100.00"), _fact(), "entailed", ALL_TRUE, "supported"),
    "partial: matching tuple on changed wording is never supported":
        ("Revenue was not 100", TEXT, _numeric(), _fact(), "partial", ALL_TRUE,
         "partially_supported"),
    "partial: lexical coverage of at least 0.5":
        ("Revenue grew sharply worldwide", "Revenue grew", None, None, "partial", None,
         "partially_supported"),
    "irrelevant: anything else":
        ("Revenue grew sharply worldwide", "Weather is sunny", None, None, "irrelevant", None,
         "unsupported"),
}
# fmt: on


@pytest.mark.parametrize("rule", sorted(RULES))
def test_rule_table(rule: str) -> None:
    claim, evidence, numeric, fact, edge, numeric_checks, claim_status = RULES[rule]
    payload = _build(claim, {"a": _span(evidence, fact)}, numeric=numeric)
    assert payload["citations"] == [
        {
            "index": 0,
            "checks": {"visible": True, "hash_valid": True, "quote_found": None},
            "reason": None,
            "edge_status": edge,
            "numeric_checks": numeric_checks,
        }
    ]
    assert payload["claim_status"] == claim_status
    # The report is the promoted verifier's own edge, not a second rule set.
    tuple_ = fact and NumericTuple(Decimal(fact.value), fact.unit, fact.period, fact.scale)
    claim_tuple = numeric and NumericTuple(
        numeric.value, numeric.unit, numeric.period, numeric.scale
    )
    item = ContextItem("a", "passage", evidence, "span", "dv", numeric=tuple_)
    assert (
        DeterministicCitationVerifier().verify(claim, item, claim_numeric=claim_tuple).status
        == edge
    )


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        ((TEXT, TEXT), "supported"),
        ((TEXT, "Revenue was 100 in the quarter"), "partially_supported"),
        ((TEXT, "Weather is sunny"), "partially_supported"),
        (("Weather is sunny", "Hiring slowed"), "unsupported"),
    ],
)
def test_claim_status_folds_edges_through_classify_claim(
    texts: tuple[str, str], expected: str
) -> None:
    spans = {key: _span(text) for key, text in zip("ab", texts, strict=True)}
    assert _build(TEXT, spans)["claim_status"] == expected


def test_any_contradictory_edge_contradicts_the_claim() -> None:
    spans = {"a": _span(TEXT, _fact()), "b": _span(TEXT, _fact("999"))}
    payload = _build(TEXT, spans, numeric=_numeric())
    assert [c["edge_status"] for c in payload["citations"]] == ["entailed", "contradictory"]
    assert payload["claim_status"] == "contradicted"


def test_report_states_what_was_and_was_not_evaluated() -> None:
    payload = _build(TEXT, {"a": _span()})
    assert list(payload) == list(FIXTURE)
    assert payload["verifier"] == "deterministic-v1"
    assert payload["semantic_entailment"] == "not_evaluated"
    assert payload["entailment_method"] == "lexical-coverage-v1"
    assert payload["quote_normalization"] == QUOTE_NORMALIZATION == "whitespace-collapse-v1"


def test_no_combination_is_supported_without_whole_evidence_text_identity() -> None:
    texts = [
        TEXT,
        "Revenue was not 100",
        "100 was revenue",
        "Revenue was 100 million",
        "revenue was 100",
    ]
    numerics = [None, _numeric(), _numeric("999"), _numeric(scale=3)]
    facts = [None, _fact(), _fact("999")]
    supported = 0
    for claim, evidence, numeric, fact in itertools.product(texts, texts, numerics, facts):
        payload = _build(claim, {"a": _span(evidence, fact)}, numeric=numeric)
        if payload["claim_status"] == "supported":
            supported += 1
            assert claim.split() == evidence.split()
            assert payload["citations"][0]["numeric_checks"] in (None, ALL_TRUE)
            assert numeric is None or fact is not None
    assert supported == len(texts) * 3  # per identical pair: no tuples, or 100/100, or 999/999


# --- MCP-502: integrity checks in front of the rules -------------------------
def test_reproduces_the_contract_fixture() -> None:
    evidence = "Total revenues were $34.9 billion, an increase of 11% year-over-year."
    payload = _build(
        "Salesforce total revenues grew 11% year-over-year.",
        {"a": _span(evidence)},
        quotes={"a": "an increase of 11% year-over-year"},
        cite=("a", "missing"),
    )
    assert json.dumps(payload) == json.dumps(FIXTURE)


def test_hidden_and_nonexistent_spans_give_byte_identical_reports() -> None:
    spans = {"a": _span(), "late": _span(TEXT, _fact())}
    reports = [
        _build(
            TEXT, spans, numeric=_numeric(), quotes={ref: "Revenue"}, cite=("a", ref), hidden=hidden
        )
        for ref, hidden in (("late", ("late",)), ("never-existed", ()))
    ]
    assert json.dumps(reports[0]).encode() == json.dumps(reports[1]).encode()
    assert reports[0]["citations"][1] == {"index": 1, **NOT_VISIBLE}
    assert reports[0]["claim_status"] == "unsupported"


def test_a_not_found_error_from_the_source_takes_the_same_path() -> None:
    class Raising(FakeSource):
        def resolve_span(self, ref: i.SpanRef, context: i.EvidenceContext) -> SpanEvidence | None:
            raise i.EvidenceReadError.not_found()

    request = i.VerifyClaimRequest(TEXT, (i.CitedSpan(i.SpanRangeRef("dv", 0, 15), "Revenue"),))
    report = DeterministicReportBuilder(Raising({})).build(request, CONTEXT).report
    assert report_to_json(report)["citations"] == [{"index": 0, **NOT_VISIBLE}]
    assert report.citations == (i.CitationVerdict.not_visible(0),)


def test_other_source_errors_are_not_reported_as_not_found() -> None:
    class Down(FakeSource):
        def resolve_span(self, ref: i.SpanRef, context: i.EvidenceContext) -> SpanEvidence | None:
            raise i.EvidenceReadError(
                "unavailable", "Down.", retryable=True, recovery="Wait.", retry_after_seconds=5
            )

    request = i.VerifyClaimRequest(TEXT, (i.CitedSpan(i.SpanIdRef("a")),))
    with pytest.raises(i.EvidenceReadError) as error:
        DeterministicReportBuilder(Down({})).build(request, CONTEXT)
    assert error.value.code == "unavailable"


@pytest.mark.parametrize(
    "span",
    [
        _span(TEXT, text_hash=_hash("Revenue was 101")),
        _span("Revenue was \ud800", text_hash=_hash("x")),
    ],
)
def test_stale_hash_makes_an_identical_claim_unsupported(span: SpanEvidence) -> None:
    payload = _build(span.text, {"a": span, "b": _span(span.text.replace("\ud800", "?"))})
    assert payload["citations"][0] == {
        "index": 0,
        "checks": {"visible": True, "hash_valid": False, "quote_found": None},
        "reason": "hash_mismatch",
        "edge_status": "irrelevant",
        "numeric_checks": None,
    }
    assert payload["claim_status"] == "unsupported"


@pytest.mark.parametrize(
    ("quote", "found"),
    [
        ("Revenue was 100", True),
        ("  Revenue\n\twas   100 ", True),
        ("was \U0001f4c8 100", False),
        ("revenue was 100", False),  # verbatim, so case counts
        ("Revenue was 10 0", False),  # whitespace collapses, it is never removed
        ("Revenue was 1000", False),
        (" \n\t ", False),  # an empty needle would be found in anything
    ],
)
def test_quote_must_occur_verbatim_after_whitespace_collapse(quote: str, found: bool) -> None:
    payload = _build("Revenue  was 100", {"a": _span("Revenue  was\n100")}, quotes={"a": quote})
    citation = payload["citations"][0]
    assert citation["checks"] == {"visible": True, "hash_valid": True, "quote_found": found}
    assert citation["reason"] == (None if found else "quote_not_found")
    assert citation["edge_status"] == ("entailed" if found else "irrelevant")
    assert payload["claim_status"] == ("supported" if found else "unsupported")


def test_non_bmp_text_hashes_and_quotes_by_code_point() -> None:
    text = "Growth \U0001f4c8 in \U00020000 markets"
    payload = _build(text, {"a": _span(text)}, quotes={"a": "\U0001f4c8 in \U00020000"})
    assert payload["citations"][0]["checks"] == {
        "visible": True,
        "hash_valid": True,
        "quote_found": True,
    }
    assert payload["claim_status"] == "supported"


def test_valid_quote_with_only_lexical_overlap_is_partially_supported() -> None:
    payload = _build(
        "Revenue grew sharply", {"a": _span("Revenue grew")}, quotes={"a": "Revenue grew"}
    )
    assert payload["claim_status"] == "partially_supported"


@pytest.mark.parametrize("other", [_span(TEXT, _fact("999")), _span(TEXT, _fact())])
def test_an_integrity_failure_overrides_every_other_edge(other: SpanEvidence) -> None:
    """Without the override these fold to contradicted and partially_supported."""
    spans = {"a": other, "b": _span(TEXT, _fact(), text_hash=_hash("stale"))}
    payload = _build(TEXT, spans, numeric=_numeric())
    assert payload["citations"][1]["edge_status"] == "irrelevant"
    assert payload["citations"][1]["numeric_checks"] == ALL_TRUE  # reported, never credited
    assert payload["claim_status"] == "unsupported"
    assert _build(TEXT, {"a": _span()}, cite=("a", "missing"))["claim_status"] == "unsupported"


# --- fail closed on anything that cannot be parsed ----------------------------
@pytest.mark.parametrize(
    "fact",
    [
        _fact(scale=2),  # legal in financial_facts and mcp-get-financial-facts-output
        _fact(scale=-3),
        _fact(scale=12),
        _fact(scale=True),
        _fact(scale=6.0),
        _fact(scale="6"),
        _fact("abc"),
        _fact(""),
        _fact("NaN"),
        _fact("-Infinity"),
        _fact(100.0),  # never a float
        _fact(unit=""),
        _fact(period=""),
    ],
)
@pytest.mark.parametrize("numeric", [None, _numeric()])
def test_unparseable_evidence_fact_never_supports(
    fact: EvidenceFact, numeric: i.ClaimNumeric | None
) -> None:
    """Identical text and a matching number, yet no raw error and no support."""
    payload = _build(TEXT, {"a": _span(TEXT, fact)}, numeric=numeric)
    assert payload["citations"][0]["edge_status"] == "irrelevant"
    assert payload["citations"][0]["numeric_checks"] is None
    assert payload["citations"][0]["reason"] is None
    assert payload["claim_status"] == "unsupported"


@pytest.mark.parametrize(
    ("field", "value"),
    [("scale", 2), ("scale", "6"), ("value", 100.0), ("value", "100"), ("value", Decimal("NaN"))],
)
def test_malformed_asserted_numeric_is_invalid_input_not_a_raw_error(
    field: str, value: Any
) -> None:
    numeric = _numeric()
    object.__setattr__(numeric, field, value)  # what a caller bypassing ClaimNumeric could send
    with pytest.raises(i.EvidenceReadError) as error:
        _build(TEXT, {"a": _span(TEXT, _fact())}, numeric=numeric)
    assert (error.value.code, error.value.field) == ("invalid_input", f"numeric.{field}")


def test_unknown_verifier_pin_is_refused_before_any_read() -> None:
    source = FakeSource({"a": _span()})
    request = i.VerifyClaimRequest(TEXT, (i.CitedSpan(i.SpanIdRef("a")),))
    context = dataclasses.replace(CONTEXT, verifier_version="deterministic-v2")
    with pytest.raises(i.EvidenceReadError) as error:
        DeterministicReportBuilder(source).build(request, context)
    assert (error.value.code, error.value.field) == ("pin_unavailable", "verifier_version")
    assert source.calls == 0


def test_same_input_gives_byte_identical_reports_and_satisfies_the_protocol() -> None:
    spans = {"b": _span(TEXT, _fact()), "a": _span("Revenue grew")}
    kwargs: dict[str, Any] = {
        "numeric": _numeric(),
        "quotes": {"a": "grew"},
        "cite": ("b", "x", "a", "b"),
    }
    first, second = (json.dumps(_build(TEXT, spans, **kwargs)) for _ in range(2))
    assert first.encode() == second.encode()
    assert isinstance(DeterministicReportBuilder(FakeSource({})), i.VerificationReportBuilder)

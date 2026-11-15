"""Byte-identity of the citation verifier across its promotion (#396, MCP-501).

``GOLDEN`` and ``TRACE_SHA256`` were recorded from ``MockCitationVerifier`` at
``origin/main`` @ ``33c6a63``, before the rule implementation was extracted.
They pin every observable output of an edge (status, numeric checks, rationale
and confidence) for each rule of the design contract §7.2, and the bytes
``verify_claims`` stamps on a stored trace, including the mock's identity
strings. ADR-0034 decision 7 requires these to survive the promotion unchanged.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal

import pytest

from fel_retrieval.generation import ClaimCitation, ContextItem, GeneratedClaim, NumericTuple
from fel_retrieval.verification import (
    DETERMINISTIC_VERIFIER_VERSION,
    CitationVerifier,
    DeterministicCitationVerifier,
    DeterministicRules,
    MockCitationVerifier,
    verify_claims,
)

ALL_TRUE = {"value": True, "unit": True, "period": True, "sign": True, "scale": True}


def _num(value: str, unit: str = "USD", period: str = "FY2025", scale: int = 6) -> NumericTuple:
    return NumericTuple(value=Decimal(value), unit=unit, period=period, scale=scale)


def _item(text: str, numeric: NumericTuple | None = None, *, n: int = 1) -> ContextItem:
    return ContextItem(
        item_id=f"item-{n}",
        kind="fact" if numeric else "passage",
        text=text,
        source_span_id=f"span-{n}",
        document_version_id="dv-1",
        financial_fact_id=f"ff-{n}" if numeric else None,
        numeric=numeric,
    )


NO_TUPLE = "numeric fact claim has no independently asserted numeric tuple"
NO_EVIDENCE_TUPLE = "claim asserts numeric but evidence has no numeric tuple"
IDENTITY = "whole-evidence text identity"

# name -> (claim text, evidence text, claim numeric, evidence numeric,
#          expected status, numeric checks, rationale, confidence)
Case = tuple[str, str, NumericTuple | None, NumericTuple | None, str, dict[str, bool], str, str]
# fmt: off
GOLDEN: dict[str, Case] = {
    "digit_claim_without_asserted_tuple": (
        "Revenue was 100", "Revenue was 100", None, _num("100"), "irrelevant", {}, NO_TUPLE, "0",
    ),
    "asserted_tuple_without_evidence_tuple": (
        "Revenue was 100", "Revenue was 100", _num("100"), None,
        "irrelevant", {}, NO_EVIDENCE_TUPLE, "0",
    ),
    "value_mismatch": (
        "Revenue was 100", "Revenue was 100", _num("999"), _num("100"),
        "contradictory", {**ALL_TRUE, "value": False}, "numeric mismatch: value", "0",
    ),
    "unit_mismatch": (
        "Revenue was 100", "Revenue was 100", _num("100", unit="EUR"), _num("100"),
        "contradictory", {**ALL_TRUE, "unit": False}, "numeric mismatch: unit", "0",
    ),
    "period_mismatch": (
        "Revenue was 100", "Revenue was 100", _num("100", period="FY2024"), _num("100"),
        "contradictory", {**ALL_TRUE, "period": False}, "numeric mismatch: period", "0",
    ),
    "sign_mismatch": (
        "Revenue was 100", "Revenue was 100", _num("-100"), _num("100"),
        "contradictory", {**ALL_TRUE, "sign": False}, "numeric mismatch: sign", "0",
    ),
    "scale_mismatch": (
        "Revenue was 100", "Revenue was 100", _num("100", scale=3), _num("100"),
        "contradictory", {**ALL_TRUE, "scale": False}, "numeric mismatch: scale", "0",
    ),
    "several_mismatches_sorted": (
        "Revenue was 100", "Revenue was 100", _num("100", "EUR", "FY2024", 9), _num("100"),
        "contradictory", {**ALL_TRUE, "unit": False, "period": False, "scale": False},
        "numeric mismatch: period, scale, unit", "0",
    ),
    "identity_with_matching_tuple": (
        "  Revenue was\n100 ", "Revenue was 100", _num("100.0"), _num("100"),
        "entailed", ALL_TRUE, IDENTITY, "1",
    ),
    "identity_without_numbers": (
        "Revenue grew", "Revenue  grew", None, None, "entailed", {}, IDENTITY, "1",
    ),
    "identity_with_digit_and_no_tuples": (
        "Revenue was 100", "Revenue was 100", None, None, "entailed", {}, IDENTITY, "1",
    ),
    "changed_wording_with_matching_tuple": (
        "Revenue was not 100", "Revenue was 100", _num("100"), _num("100"),
        "partial", ALL_TRUE, "lexical coverage 0.75; semantic entailment unverified", "0.7500",
    ),
    "reordered_full_coverage_is_not_identity": (
        "100 was revenue", "Revenue was 100", None, None,
        "partial", {}, "lexical coverage 1.00; semantic entailment unverified", "0.9999",
    ),
    "half_coverage": (
        "Revenue grew sharply worldwide", "Revenue grew", None, None,
        "partial", {}, "lexical coverage 0.50; semantic entailment unverified", "0.5000",
    ),
    "low_coverage": (
        "Revenue grew sharply worldwide", "Weather is sunny", None, None,
        "irrelevant", {}, "lexical coverage 0.00; semantic entailment unverified", "0.0000",
    ),
    "identical_text_without_tokens": (
        "!!!", "!!!", None, None,
        "irrelevant", {}, "lexical coverage 0.00; semantic entailment unverified", "0.0000",
    ),
}
# fmt: on

TRACE_SHA256 = "3950122b9730a5ace73833aa922a656e2fd87b6327464d49fee58f9c863ac709"


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_mock_edge_is_byte_identical_to_the_recorded_golden(name: str) -> None:
    claim, evidence, claim_numeric, evidence_numeric, status, checks, rationale, conf = GOLDEN[name]
    edge = MockCitationVerifier().verify(
        claim, _item(evidence, evidence_numeric), claim_numeric=claim_numeric
    )
    assert (edge.status, edge.numeric_checks, edge.rationale, str(edge.confidence)) == (
        status,
        checks,
        rationale,
        conf,
    )
    assert list(edge.numeric_checks) == list(checks)  # key order is part of the stored bytes


def test_mock_identity_strings_are_unchanged() -> None:
    mock = MockCitationVerifier()
    assert (mock.name, mock.model, mock.version) == ("mock-entailment", "mock-verifier-v1", "v1")


def _trace_bytes(verifier: CitationVerifier | None = None) -> bytes:
    """Every golden case as one claim, verified and serialized as a stored trace."""
    claims = []
    context = []
    for n, name in enumerate(sorted(GOLDEN)):
        claim, evidence, claim_numeric, evidence_numeric, *_ = GOLDEN[name]
        context.append(_item(evidence, evidence_numeric, n=n))
        citation = ClaimCitation(item_id=f"item-{n}", source_span_id=f"span-{n}", quote=evidence)
        claims.append(GeneratedClaim(n, claim, "unsupported", (citation,), numeric=claim_numeric))
    verified = verify_claims(claims, context, verifier or MockCitationVerifier())
    rows = [dataclasses.asdict(claim) for claim in verified]
    return json.dumps(rows, default=str, separators=(",", ":")).encode()


def test_verify_claims_trace_is_byte_identical_to_the_recorded_golden() -> None:
    payload = _trace_bytes()
    assert payload.count(b'"verifier":"mock-entailment"') == len(GOLDEN)
    assert payload.count(b'"model":"mock-verifier-v1","version":"v1"') == len(GOLDEN)
    assert hashlib.sha256(payload).hexdigest() == TRACE_SHA256


# --- the promoted verifier (deterministic-v1) --------------------------------
def test_deterministic_verifier_is_identified_as_deterministic_v1() -> None:
    promoted = DeterministicCitationVerifier()
    assert DETERMINISTIC_VERIFIER_VERSION == "deterministic-v1"
    assert (promoted.name, promoted.model, promoted.version) == (
        "deterministic-entailment",
        "deterministic-v1",
        "v1",
    )


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_deterministic_verifier_gives_the_golden_edge_for_every_rule(name: str) -> None:
    claim, evidence, claim_numeric, evidence_numeric, *_ = GOLDEN[name]
    item = _item(evidence, evidence_numeric)
    promoted = DeterministicCitationVerifier().verify(claim, item, claim_numeric=claim_numeric)
    assert promoted == MockCitationVerifier().verify(claim, item, claim_numeric=claim_numeric)
    assert (promoted.status, promoted.rationale) == (GOLDEN[name][4], GOLDEN[name][6])


def test_both_verifiers_share_one_rule_implementation() -> None:
    """Neither verifier defines rules of its own; both run ``DeterministicRules.verify``."""
    assert MockCitationVerifier.verify is DeterministicRules.verify
    assert DeterministicCitationVerifier.verify is DeterministicRules.verify
    for verifier in (MockCitationVerifier, DeterministicCitationVerifier):
        own = {name for name in vars(verifier) if not name.startswith("__")}
        assert own == {"name", "model", "version"}


def test_promoted_trace_differs_from_the_mock_trace_only_in_identity_strings() -> None:
    promoted = _trace_bytes(DeterministicCitationVerifier())
    assert b"mock" not in promoted
    as_mock = promoted.replace(
        b'"verifier":"deterministic-entailment","model":"deterministic-v1"',
        b'"verifier":"mock-entailment","model":"mock-verifier-v1"',
    )
    assert hashlib.sha256(as_mock).hexdigest() == TRACE_SHA256

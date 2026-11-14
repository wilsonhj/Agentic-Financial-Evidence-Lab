"""Verification report for one claim (``mcp-verification-report/v1``, #396).

``DeterministicReportBuilder`` implements ``VerificationReportBuilder`` from
``fel_retrieval.evidence.interfaces``. It adds three integrity checks in front
of the unchanged ``deterministic-v1`` rules (design contract §7.2) and adds no
rule of its own:

* ``visible``: the reference resolves inside the evidence set visible under the
  context. A hidden span and a nonexistent one both come back as "no span" from
  the source, take one code path here, and produce the same verdict.
* ``hash_valid``: the hash recomputed from the span text equals the stored one.
* ``quote_found``: a supplied quote occurs verbatim in the span text after
  whitespace collapse (``QUOTE_NORMALIZATION``).

A failed check makes that edge ``irrelevant`` and the claim ``unsupported``.
Otherwise the edges fold through ``classify_claim``. Nothing here evaluates
semantic entailment, and ``supported`` still requires whole-evidence text
identity. Anything that cannot be parsed fails closed: a malformed evidence
fact supports nothing, and a malformed asserted numeric is ``invalid_input``.
The builder reads no clock and no random source, so the same request and
context give the same report.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Protocol

from fel_retrieval.evidence.interfaces import (
    CitationVerdict,
    CitedSpan,
    ClaimNumeric,
    ClaimStatus,
    CoverageNote,
    EvidenceContext,
    EvidenceReadError,
    IntegrityChecks,
    IntegrityReason,
    NumericChecks,
    SpanRef,
    VerificationReport,
    VerifyClaimRequest,
    VerifyClaimResult,
)
from fel_retrieval.generation import NUMERIC_SCALE_EXPONENTS, ContextItem, NumericTuple
from fel_retrieval.verification import (
    DETERMINISTIC_VERIFIER_VERSION,
    DeterministicCitationVerifier,
    classify_claim,
)

# Applied to the quote and to the span text before the quote_found check: every
# run of Unicode whitespace becomes one space and the ends are trimmed. This is
# the normalization the rules already apply for whole-evidence text identity.
QUOTE_NORMALIZATION: Final = "whitespace-collapse-v1"

# classify_claim can name ``derived`` in its type but never returns it; v1
# reports exclude it (design contract §7.2).
_CLAIM_STATUS: Final[Mapping[str, ClaimStatus]] = {
    "supported": "supported",
    "partially_supported": "partially_supported",
    "contradicted": "contradicted",
    "unsupported": "unsupported",
}


@dataclass(frozen=True)
class EvidenceFact:
    """The stored fact whose ``source_span_id`` is the cited span, unparsed.

    ``value`` is the stored decimal string and ``period`` the corpus period
    label the claim's ``numeric.period`` is compared with. The builder parses
    these itself, so a stored scale outside the verifier's set or a malformed
    value fails closed instead of raising.
    """

    value: str
    unit: str
    period: str
    scale: int


@dataclass(frozen=True)
class SpanEvidence:
    """A cited span resolved inside the visible evidence set.

    ``text`` is the code-point slice of canonical text and ``text_hash`` the
    stored ``sha256:<hex>`` it must hash to. ``fact`` is the fact that cites
    this span, never another visible fact.
    """

    span_id: str
    document_version_id: str
    text: str
    text_hash: str
    fact: EvidenceFact | None = None


class VerificationEvidenceSource(Protocol):
    """What the builder reads. The evidence-read service supplies it (#395).

    ``resolve_span`` returns None, or raises ``EvidenceReadError.not_found()``,
    for a reference that is missing or hidden under ``context``; the two must be
    indistinguishable. ``coverage_note`` depends on the context alone, so it
    cannot reveal whether a cited span exists.
    """

    def resolve_span(self, ref: SpanRef, context: EvidenceContext) -> SpanEvidence | None: ...

    def coverage_note(self, context: EvidenceContext) -> CoverageNote: ...


class _UnverifiableFact(Exception):
    """The evidence fact cannot be parsed into a numeric tuple."""


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _hash_valid(evidence: SpanEvidence) -> bool:
    try:
        digest = hashlib.sha256(evidence.text.encode("utf-8")).hexdigest()
    except UnicodeEncodeError:  # a lone surrogate has no UTF-8 form, so no valid hash
        return False
    return evidence.text_hash == f"sha256:{digest}"


def _quote_found(quote: str, text: str) -> bool:
    needle = _collapse(quote)
    return bool(needle) and needle in _collapse(text)


def _legal_scale(scale: object) -> bool:
    return type(scale) is int and scale in NUMERIC_SCALE_EXPONENTS


def _evidence_tuple(fact: EvidenceFact | None) -> NumericTuple | None:
    if fact is None:
        return None
    try:
        value = Decimal(fact.value) if isinstance(fact.value, str) else None
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or not _legal_scale(fact.scale):
        raise _UnverifiableFact
    if not fact.unit or not fact.period:
        raise _UnverifiableFact
    return NumericTuple(value=value, unit=fact.unit, period=fact.period, scale=fact.scale)


def _invalid_numeric(field: str, constraint: str) -> EvidenceReadError:
    return EvidenceReadError(
        "invalid_input",
        f"numeric.{field} must be {constraint}.",
        retryable=False,
        recovery="Correct the numeric tuple and retry.",
        field=f"numeric.{field}",
    )


def _claim_tuple(numeric: ClaimNumeric | None) -> NumericTuple | None:
    """The asserted tuple; sign is derived from ``value`` by ``NumericTuple``."""
    if numeric is None:
        return None
    if not isinstance(numeric.value, Decimal) or not numeric.value.is_finite():
        raise _invalid_numeric("value", "a finite decimal")
    if not _legal_scale(numeric.scale):
        raise _invalid_numeric("scale", f"one of {sorted(NUMERIC_SCALE_EXPONENTS)}")
    return NumericTuple(numeric.value, numeric.unit, numeric.period, numeric.scale)


class DeterministicReportBuilder:
    """Builds ``deterministic-v1`` reports from a ``VerificationEvidenceSource``."""

    def __init__(self, source: VerificationEvidenceSource) -> None:
        self._source = source
        self._verifier = DeterministicCitationVerifier()

    def build(self, request: VerifyClaimRequest, context: EvidenceContext) -> VerifyClaimResult:
        if context.verifier_version != DETERMINISTIC_VERIFIER_VERSION:
            raise EvidenceReadError(
                "pin_unavailable",
                "Verifier version is not available.",
                retryable=False,
                recovery=f"Omit verifier_version to use {DETERMINISTIC_VERIFIER_VERSION}.",
                field="verifier_version",
            )
        claim_numeric = _claim_tuple(request.numeric)
        verdicts = tuple(
            self._verdict(index, cited, request.claim, claim_numeric, context)
            for index, cited in enumerate(request.citations)
        )
        # Any failed integrity check makes the claim unsupported, whatever the
        # other edges say.
        status: ClaimStatus = "unsupported"
        if all(verdict.reason is None for verdict in verdicts):
            status = _CLAIM_STATUS[classify_claim([verdict.edge_status for verdict in verdicts])]
        report = VerificationReport(
            DETERMINISTIC_VERIFIER_VERSION, status, verdicts, QUOTE_NORMALIZATION
        )
        return VerifyClaimResult(context, self._source.coverage_note(context), report)

    def _resolve(self, ref: SpanRef, context: EvidenceContext) -> SpanEvidence | None:
        try:
            return self._source.resolve_span(ref, context)
        except EvidenceReadError as error:
            if error.code != "not_found":
                raise
            return None

    def _verdict(
        self,
        index: int,
        cited: CitedSpan,
        claim: str,
        claim_numeric: NumericTuple | None,
        context: EvidenceContext,
    ) -> CitationVerdict:
        evidence = self._resolve(cited.ref, context)
        if evidence is None:
            return CitationVerdict.not_visible(index)
        hash_valid = _hash_valid(evidence)
        quote_found = None if cited.quote is None else _quote_found(cited.quote, evidence.text)
        reason: IntegrityReason | None = None
        if not hash_valid:
            reason = "hash_mismatch"
        elif quote_found is False:
            reason = "quote_not_found"
        checks = IntegrityChecks(True, hash_valid, quote_found)
        try:
            evidence_numeric = _evidence_tuple(evidence.fact)
        except _UnverifiableFact:
            return CitationVerdict(index, checks, reason, "irrelevant", None)
        item = ContextItem(
            item_id=evidence.span_id,
            kind="passage" if evidence_numeric is None else "fact",
            text=evidence.text,
            source_span_id=evidence.span_id,
            document_version_id=evidence.document_version_id,
            numeric=evidence_numeric,
        )
        edge = self._verifier.verify(claim, item, claim_numeric=claim_numeric)
        return CitationVerdict(
            index,
            checks,
            reason,
            edge.status if reason is None else "irrelevant",
            NumericChecks(**edge.numeric_checks) if edge.numeric_checks else None,
        )


def report_to_json(report: VerificationReport) -> dict[str, Any]:
    """The report as a ``mcp-verification-report/v1`` JSON object.

    A not-visible citation carries exactly ``index``, ``checks``, ``reason`` and
    ``edge_status``; the schema forbids anything more, so hidden and nonexistent
    spans serialize to the same bytes.
    """
    citations: list[dict[str, Any]] = []
    for verdict in report.citations:
        citation: dict[str, Any] = {
            "index": verdict.index,
            "checks": dataclasses.asdict(verdict.checks),
            "reason": verdict.reason,
            "edge_status": verdict.edge_status,
        }
        if verdict.checks.visible:
            citation["numeric_checks"] = (
                None
                if verdict.numeric_checks is None
                else dataclasses.asdict(verdict.numeric_checks)
            )
        citations.append(citation)
    return {
        "verifier": report.verifier,
        "claim_status": report.claim_status,
        "citations": citations,
        "semantic_entailment": report.semantic_entailment,
        "entailment_method": report.entailment_method,
        "quote_normalization": report.quote_normalization,
    }


__all__ = [
    "QUOTE_NORMALIZATION",
    "DeterministicReportBuilder",
    "EvidenceFact",
    "SpanEvidence",
    "VerificationEvidenceSource",
    "report_to_json",
]

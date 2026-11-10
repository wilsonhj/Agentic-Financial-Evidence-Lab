"""Typed interface of the shared evidence-read service (ADR-0034, #392, MCP-107).

The MCP adapter (``packages/mcp-server``, #397) calls these Protocols; the
evidence-read service (#395) and the verification-report builder (#396)
implement them. This module holds types only: no implementation, no database
access, no I/O. It mirrors the JSON Schemas in ``packages/contracts/schemas/``:

* ``mcp-evidence-context/v1`` -> ``EvidenceContext``
* ``mcp-citation/v1`` -> ``Citation``
* ``mcp-verification-report/v1`` -> ``VerificationReport``
* ``mcp-error/v1`` -> ``EvidenceReadError``
* ``mcp-<tool>-input/v1`` and ``-output/v1`` -> the request and result types.

Conventions the implementations must keep (design contract §6-§7):

* Every method takes a resolved ``EvidenceContext``, and every result returns
  it unchanged with a ``CoverageNote``. Only ``resolve_context`` turns request
  inputs into a context, and it never falls back from an unavailable pin.
* Visibility is decided inside the service. A hidden reference and a missing
  one take the same code path and raise the same ``not_found`` error.
* Offsets are Unicode code points, and hashes are recomputed from canonical
  text. Financial values are exact: decimal strings on output, and ``Decimal``
  for a client-asserted numeric value.
* Results are immutable and deterministic for a given context and request.
  ``LiveStatus`` is the one exception and is labeled ``replayable=False``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal, Protocol

TimestampMode = Literal["strict", "approximate"]
TemporalGuarantee = Literal["strict", "none"]
# Stored documents.timestamp_precision is 'date' | 'second'; a served result
# is 'second' (verified acceptance) or 'approximate' (approximate mode).
ServedTimestampPrecision = Literal["second", "approximate"]
StoredTimestampPrecision = Literal["date", "second"]
ItemKind = Literal["passage", "table_row", "fact"]
SearchLane = Literal["lexical", "facts", "tables"]
ClaimStatus = Literal["supported", "partially_supported", "contradicted", "unsupported"]
EdgeStatus = Literal["entailed", "partial", "contradictory", "irrelevant"]
IntegrityReason = Literal["hash_mismatch", "quote_not_found"]
ErrorCode = Literal[
    "not_found",
    "invalid_input",
    "cursor_expired",
    "pin_unavailable",
    "rate_limited",
    "overloaded",
    "deadline_exceeded",
    "unavailable",
    "integrity_error",
]

# mcp-verify-claim-input: numeric.scale is one of NUMERIC_SCALE_EXPONENTS.
NumericScale = Literal[0, 3, 6, 9]
OFFSET_UNIT: Final = "unicode_code_point"
SEMANTIC_ENTAILMENT: Final = "not_evaluated"
ENTAILMENT_METHOD: Final = "lexical-coverage-v1"
# mcp-error/v1 fixes the not_found envelope so hidden and missing references
# are indistinguishable.
NOT_FOUND_MESSAGE: Final = "No visible evidence matches this reference."
NOT_FOUND_RECOVERY: Final = "Check the identifier, or search within the current context."


# ---------------------------------------------------------------------------
# Errors (mcp-error/v1)
# ---------------------------------------------------------------------------


class EvidenceReadError(Exception):
    """A tool-execution failure carrying one ``mcp-error/v1`` code.

    ``field`` names the offending input (``invalid_input``) or pin
    (``pin_unavailable``). ``retry_after_seconds`` is set for the retryable
    load-shedding codes. ``not_found`` carries no field and no detail.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        recovery: str,
        field: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.retryable = retryable
        self.recovery = recovery
        self.field = field
        self.retry_after_seconds = retry_after_seconds


# ---------------------------------------------------------------------------
# Context (mcp-evidence-context/v1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextFilters:
    """Filters frozen into a context's cursors (``evidence_context.filters``)."""

    company: str | None = None
    companies: tuple[str, ...] | None = None
    forms: tuple[str, ...] | None = None
    periods: tuple[str, ...] | None = None
    concept: str | None = None
    period: str | None = None
    document_id: str | None = None
    section: str | None = None


@dataclass(frozen=True)
class ContextRequest:
    """Request-side point-in-time inputs, before resolution (§6.1, §6.3).

    ``as_of`` is an aware instant, a date (00:00 America/New_York) or None
    (``request_time``). ``request_time`` is supplied by the caller so that
    resolution never reads a clock of its own.
    """

    request_time: datetime
    as_of: datetime | date | None = None
    timestamp_mode: TimestampMode = "strict"
    corpus_version_id: str | None = None
    index_version_id: str | None = None
    verifier_version: str | None = None
    filters: ContextFilters = field(default_factory=ContextFilters)


@dataclass(frozen=True)
class EvidenceContext:
    """The resolved context every result echoes (``mcp-evidence-context/v1``)."""

    effective_as_of: datetime
    timestamp_mode: TimestampMode
    temporal_guarantee: TemporalGuarantee
    corpus_version_id: str
    index_version_id: str | None
    parser_version: str | None
    verifier_version: str
    document_version_id: str | None
    filters: ContextFilters


@dataclass(frozen=True)
class DateRange:
    start: datetime | None
    end: datetime | None


@dataclass(frozen=True)
class CoverageNote:
    """Issuers (CIKs), forms and acceptance-time range searched (§7)."""

    text: str
    issuers: tuple[str, ...]
    forms: tuple[str, ...]
    date_range: DateRange


# ---------------------------------------------------------------------------
# Shared evidence shapes (mcp-citation/v1 and friends)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Company:
    entity_id: str
    cik: str
    ticker: str | None
    name: str


@dataclass(frozen=True)
class FilingRef:
    accession: str
    form: str | None
    filing_date: date
    accepted_at: datetime | None


@dataclass(frozen=True)
class Citation:
    """A span-level citation (``mcp-citation/v1``); ``text`` is untrusted."""

    span_id: str
    accession: str
    form: str | None
    company: Company
    document_id: str
    document_version_id: str
    parser_version: str
    section_path: tuple[str, ...]
    start_char: int
    end_char: int
    text: str
    text_hash: str
    document_content_hash: str
    source_url: str
    filing_date: date
    accepted_at: datetime | None
    timestamp_precision: ServedTimestampPrecision
    reader_url: str | None = None


@dataclass(frozen=True)
class SpanIdRef:
    span_id: str


@dataclass(frozen=True)
class SpanRangeRef:
    document_version_id: str
    start_char: int
    end_char: int


SpanRef = SpanIdRef | SpanRangeRef


# ---------------------------------------------------------------------------
# Tool requests and results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompanyCoverage:
    first_visible_filing: FilingRef | None
    last_visible_filing: FilingRef | None
    visible_forms: tuple[str, ...]
    visible_filing_count: int


@dataclass(frozen=True)
class CompanyMatch:
    company: Company
    coverage: CompanyCoverage


@dataclass(frozen=True)
class ResolveCompanyResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    matches: tuple[CompanyMatch, ...]


@dataclass(frozen=True)
class ListFilingsRequest:
    company: str
    limit: int
    forms: tuple[str, ...] | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class FilingMeta:
    entity_id: str
    accession: str
    form: str | None
    filing_date: date
    accepted_at: datetime | None
    timestamp_precision: ServedTimestampPrecision
    period_end: date | None
    document_id: str
    document_version_id: str
    source_url: str
    content_hash: str
    amends: str | None


@dataclass(frozen=True)
class ListFilingsResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    filings: tuple[FilingMeta, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class SearchRequest:
    query: str
    top_k: int
    companies: tuple[str, ...] | None = None
    forms: tuple[str, ...] | None = None
    periods: tuple[str, ...] | None = None


@dataclass(frozen=True)
class LaneContribution:
    lane: SearchLane
    lane_rank: int
    rrf_contribution: str


@dataclass(frozen=True)
class SearchHit:
    rank: int
    kind: ItemKind
    fused_score: str
    lanes: tuple[LaneContribution, ...]
    citation: Citation


@dataclass(frozen=True)
class SearchResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    results: tuple[SearchHit, ...]


@dataclass(frozen=True)
class ReadFilingRequest:
    """Exactly one of ``document_id`` or ``accession``.

    ``section`` is a section id or a heading path.
    """

    document_id: str | None = None
    accession: str | None = None
    section: str | tuple[str, ...] | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class DocumentHeader:
    document_id: str
    document_version_id: str
    parser_version: str
    company: Company
    accession: str
    form: str | None
    filing_date: date
    accepted_at: datetime | None
    timestamp_precision: ServedTimestampPrecision
    source_url: str
    document_content_hash: str


@dataclass(frozen=True)
class SectionRef:
    section_id: str
    heading_path: tuple[str, ...]
    start_char: int
    end_char: int


@dataclass(frozen=True)
class OutlineEntry:
    section_id: str
    heading_path: tuple[str, ...]
    ord: int


@dataclass(frozen=True)
class TextChunk:
    """A code-point slice of canonical text; ``text`` is untrusted."""

    start_char: int
    end_char: int
    text: str


@dataclass(frozen=True)
class ReadFilingResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    document: DocumentHeader
    section: SectionRef
    chunk: TextChunk
    spans: tuple[Citation, ...]
    outline: tuple[OutlineEntry, ...] | None
    next_cursor: str | None


@dataclass(frozen=True)
class CitationResult:
    """``get_citation``: returned only after the hash re-check passed."""

    context: EvidenceContext
    coverage_note: CoverageNote
    citation: Citation


@dataclass(frozen=True)
class FactsRequest:
    company: str
    limit: int
    concept: str | None = None
    period: str | None = None
    cursor: str | None = None


@dataclass(frozen=True)
class FactPeriod:
    type: Literal["instant", "duration"]
    instant: date | None
    start: date | None
    end: date | None


@dataclass(frozen=True)
class Fact:
    """A filing-native XBRL fact; ``value`` is the stored decimal string."""

    fact_id: str
    concept: str
    label: str | None
    value: str
    unit: str
    scale: int
    period: FactPeriod
    dimensions: Mapping[str, str]
    reported_or_derived: Literal["reported", "derived"]
    citation: Citation
    restated_by: tuple[str, ...]
    duplicate_of: str | None


@dataclass(frozen=True)
class FactsResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    facts: tuple[Fact, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class IssuerCoverage:
    company: Company
    visible_filing_count: int
    first_filing_date: date | None
    last_filing_date: date | None


@dataclass(frozen=True)
class CorpusCoverage:
    """``get_corpus_status.coverage``: bound to the context, replayable."""

    context: EvidenceContext
    coverage_note: CoverageNote
    issuers: tuple[IssuerCoverage, ...]
    date_range: DateRange
    timestamp_precision_mix: Mapping[StoredTimestampPrecision, int]


@dataclass(frozen=True)
class VersionRow:
    id: str
    status: str
    published_at: datetime | None
    corpus_version_id: str | None = None


@dataclass(frozen=True)
class LiveStatus:
    """``get_corpus_status.live_status``: request-time state, never replayable."""

    observed_at: datetime
    active_corpus_version_id: str | None
    retained_corpus_versions: tuple[VersionRow, ...]
    active_index_version_id: str | None
    retained_index_versions: tuple[VersionRow, ...]
    verifier_versions: tuple[str, ...]
    known_limitations: tuple[str, ...]
    replayable: Literal[False] = False


# ---------------------------------------------------------------------------
# Verification (mcp-verify-claim-input, mcp-verification-report/v1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimNumeric:
    """A client-asserted numeric tuple. Sign is derived from ``value``."""

    value: Decimal
    unit: str
    scale: NumericScale
    period: str
    concept: str | None = None


@dataclass(frozen=True)
class CitedSpan:
    """One request citation: a span reference and an optional verbatim quote."""

    ref: SpanRef
    quote: str | None = None


@dataclass(frozen=True)
class IntegrityChecks:
    visible: bool
    hash_valid: bool | None
    quote_found: bool | None


@dataclass(frozen=True)
class NumericChecks:
    value: bool
    unit: bool
    period: bool
    sign: bool
    scale: bool


@dataclass(frozen=True)
class CitationVerdict:
    """One per request citation, named only by its request position.

    An unresolvable reference is exactly ``IntegrityChecks(False, None, None)``
    with ``reason='not_found'``, ``edge_status='irrelevant'`` and
    ``numeric_checks=None``.
    """

    index: int
    checks: IntegrityChecks
    reason: IntegrityReason | Literal["not_found"] | None
    edge_status: EdgeStatus
    numeric_checks: NumericChecks | None


@dataclass(frozen=True)
class VerificationReport:
    verifier: str
    claim_status: ClaimStatus
    citations: tuple[CitationVerdict, ...]
    quote_normalization: str
    semantic_entailment: Literal["not_evaluated"] = SEMANTIC_ENTAILMENT
    entailment_method: Literal["lexical-coverage-v1"] = ENTAILMENT_METHOD


@dataclass(frozen=True)
class VerifyClaimResult:
    context: EvidenceContext
    coverage_note: CoverageNote
    report: VerificationReport


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class EvidenceReadService(Protocol):
    """Cutoff-guarded public-corpus reads on the read-only role (#395).

    Every method except ``resolve_context`` and ``live_status`` reads only
    evidence visible under ``context``. A hidden or missing reference raises
    ``EvidenceReadError('not_found', ...)`` through one code path.
    """

    def resolve_context(self, request: ContextRequest) -> EvidenceContext:
        """Resolve the cutoff and pins. Raises ``pin_unavailable`` naming the pin."""
        ...

    def resolve_company(self, query: str, context: EvidenceContext) -> ResolveCompanyResult: ...

    def list_filings(
        self, request: ListFilingsRequest, context: EvidenceContext
    ) -> ListFilingsResult: ...

    def search(self, request: SearchRequest, context: EvidenceContext) -> SearchResult:
        """Lexical, facts and tables lanes with RRF fusion. Calls no provider."""
        ...

    def read_filing(
        self, request: ReadFilingRequest, context: EvidenceContext
    ) -> ReadFilingResult: ...

    def get_citation(self, ref: SpanRef, context: EvidenceContext) -> CitationResult:
        """Raises ``integrity_error`` when the recomputed hash does not match."""
        ...

    def get_facts(self, request: FactsRequest, context: EvidenceContext) -> FactsResult:
        """Filing-native XBRL facts only; company-facts snapshots are never served."""
        ...

    def corpus_coverage(self, context: EvidenceContext) -> CorpusCoverage: ...

    def live_status(self, observed_at: datetime) -> LiveStatus: ...


class VerificationReportBuilder(Protocol):
    """Builds a ``mcp-verification-report/v1`` report (#396).

    Integrity checks (visible, hash_valid, quote_found) run in front of the
    unchanged deterministic rules. ``claim_status`` is never ``supported``
    without whole-evidence text identity.
    """

    def build(
        self,
        claim: str,
        citations: Sequence[CitedSpan],
        numeric: ClaimNumeric | None,
        context: EvidenceContext,
    ) -> VerifyClaimResult: ...

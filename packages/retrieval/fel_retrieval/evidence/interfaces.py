"""Typed interface of the shared evidence-read service (ADR-0034, #392, MCP-107).

The MCP adapter (``packages/mcp-server``, #397) calls these Protocols. The
evidence-read service (#395) and the verification-report builder (#396)
implement them. This module holds types and their invariants only: no
implementation, no database access, no I/O. Field names equal the
``properties`` of the JSON Schemas in ``packages/contracts/schemas/``, which
``packages/retrieval/tests/evidence/test_interfaces.py`` enforces. The one
spelling difference is ``DateRange.from_``, because ``from`` is a Python
keyword:

* ``mcp-evidence-context/v1`` maps to ``EvidenceContext``.
* ``mcp-citation/v1`` maps to ``Citation``.
* ``mcp-verification-report/v1`` maps to ``VerificationReport``.
* ``mcp-error/v1`` maps to ``EvidenceReadError``.
* ``mcp-<tool>-input/v1`` and ``-output/v1`` map to the request and result
  types.

Conventions the implementations must keep (design contract §6-§7):

* **Context.** Every method takes a resolved ``EvidenceContext``. Every result
  returns that context unchanged as ``evidence_context``, with a
  ``CoverageNote``. Only ``resolve_context`` turns request inputs into a
  context, and it never falls back from an unavailable pin. Every evidence
  tool accepts ``corpus_version_id``, including company and citation reads.
  Non-index tools keep ``index_version_id=None`` even when indexes change;
  search resolves the index it actually uses. Corpus status validates and
  echoes an explicit index pin, or keeps None when omitted. Non-verification
  tools fix ``verifier_version`` to ``deterministic-v1``; verification uses
  its explicit pin or ``deterministic-v1``, never an active/latest verifier.
* **Visibility.** Strict mode shows a document only when its verified
  ``public_at`` is at or before ``effective_as_of``. ``public_at`` is the
  instant the filing became public, not its acceptance time (ADR-0034
  decision 4, Amendment 1). A hidden reference and a missing one take the same
  code path and raise the same ``not_found`` error.
* **Exactness.** Offsets are Unicode code points, and hashes are recomputed
  from canonical text. Financial values are decimal strings on output; a
  client-asserted numeric value is a ``Decimal``.
* **Determinism.** Results are immutable and deterministic for a given
  context and request. ``LiveStatus`` is exempt and labeled
  ``replayable=False``. Expiring cursor token bytes are also exempt; context,
  evidence, ordering and page boundaries remain stable. Cursors stay bound
  to the context and filters and expire within 15 minutes; expired tokens
  raise ``cursor_expired`` and context mismatches raise ``invalid_input``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal, Protocol, runtime_checkable

TimestampMode = Literal["strict", "approximate"]
TemporalGuarantee = Literal["strict", "none"]
# Stored documents.timestamp_precision is 'date' | 'second'; a served result
# is 'second' (verified instants) or 'approximate' (approximate mode).
ServedTimestampPrecision = Literal["second", "approximate"]
StoredTimestampPrecision = Literal["date", "second"]
PublicAtBasis = Literal["acceptance", "next_session_open"]
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
NUMERIC_SCALES: Final = frozenset({0, 3, 6, 9})
OFFSET_UNIT: Final = "unicode_code_point"
SEMANTIC_ENTAILMENT: Final = "not_evaluated"
ENTAILMENT_METHOD: Final = "lexical-coverage-v1"
# mcp-error/v1 fixes the not_found envelope so hidden and missing references
# are indistinguishable.
NOT_FOUND_MESSAGE: Final = "No visible evidence matches this reference."
NOT_FOUND_RECOVERY: Final = "Check the identifier, or search within the current context."
# get_corpus_status.live_status must always state these (ADR-0034 Amendment 1).
REQUIRED_LIMITATION_CODES: Final = frozenset(
    {"public_at_next_session_open_is_earliest", "intraday_dissemination_delay_assumed_zero"}
)

# mcp-error/v1: (retryable, retry_after_seconds required, field required).
ERROR_RULES: Final[Mapping[ErrorCode, tuple[bool, bool, bool]]] = {
    "not_found": (False, False, False),
    "invalid_input": (False, False, True),
    "cursor_expired": (False, False, False),
    "pin_unavailable": (False, False, True),
    "rate_limited": (True, True, False),
    "overloaded": (True, True, False),
    "deadline_exceeded": (True, False, False),
    "unavailable": (True, True, False),
    "integrity_error": (False, False, False),
}


_DECIMAL_STRING: Final = re.compile(r"-?[0-9]+(\.[0-9]+)?")


def _require_aware(name: str, value: datetime | None) -> None:
    if value is not None and value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _check_publication(
    accepted_at: datetime | None,
    public_at: datetime | None,
    public_at_basis: PublicAtBasis | None,
    timestamp_precision: ServedTimestampPrecision,
) -> None:
    """Mirror of the 0012 CHECKs for a served row.

    Under ``second`` the three values are all set, ``public_at`` is not before
    ``accepted_at``, and the basis is ``acceptance`` exactly when they are
    equal. ``approximate`` admits NULLs (design contract §6.2).
    """
    values = (accepted_at, public_at, public_at_basis)
    if timestamp_precision == "second" and any(v is None for v in values):
        raise ValueError("second precision requires accepted_at, public_at and public_at_basis")
    for name, instant in (("accepted_at", accepted_at), ("public_at", public_at)):
        _require_aware(name, instant)
    if accepted_at is not None and public_at is not None:
        if public_at < accepted_at:
            raise ValueError("public_at precedes accepted_at")
        if public_at_basis is not None and (public_at_basis == "acceptance") != (
            public_at == accepted_at
        ):
            raise ValueError("public_at_basis 'acceptance' iff public_at equals accepted_at")


# ---------------------------------------------------------------------------
# Errors (mcp-error/v1)
# ---------------------------------------------------------------------------


class EvidenceReadError(Exception):
    """A tool-execution failure carrying one ``mcp-error/v1`` code.

    ``field`` names the offending input (``invalid_input``) or pin
    (``pin_unavailable``). ``retry_after_seconds`` is set for the retryable
    load-shedding codes. ``not_found`` carries the fixed message and recovery
    text and no other detail; use ``EvidenceReadError.not_found()``.
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
        expected_retryable, needs_retry_after, needs_field = ERROR_RULES[code]
        if retryable != expected_retryable:
            raise ValueError(f"{code} must have retryable={expected_retryable}")
        if needs_retry_after and retry_after_seconds is None:
            raise ValueError(f"{code} requires retry_after_seconds")
        if not retryable and retry_after_seconds is not None:
            raise ValueError(f"{code} must not carry retry_after_seconds")
        if needs_field and field is None:
            raise ValueError(f"{code} requires field")
        if code == "not_found" and (
            field is not None or message != NOT_FOUND_MESSAGE or recovery != NOT_FOUND_RECOVERY
        ):
            raise ValueError("not_found carries only the fixed message and recovery")
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.retryable = retryable
        self.recovery = recovery
        self.field = field
        self.retry_after_seconds = retry_after_seconds

    @classmethod
    def not_found(cls) -> EvidenceReadError:
        return cls("not_found", NOT_FOUND_MESSAGE, retryable=False, recovery=NOT_FOUND_RECOVERY)


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

    Both ``resolve_company`` and ``get_citation`` accept the corpus pin and
    pass it here, rather than silently resolving an active corpus on replay.
    For tools that do not use an index, the adapter leaves the index pin None.
    Corpus status may pass an explicit index pin for validation and echoing;
    omitting it stays None. Only ``verify_claim`` passes a verifier pin;
    omitted verifier pins resolve to ``deterministic-v1`` for all tools.
    Unavailable or corpus-incompatible explicit pins raise ``pin_unavailable``.

    ``require_index`` is an internal adapter signal, not a client input.
    Only search sets it True: the service resolves a compatible published
    index when its pin is omitted. The default False preserves a null index
    for non-index tools, including corpus status without an explicit pin.
    """

    request_time: datetime
    as_of: datetime | date | None = None
    timestamp_mode: TimestampMode = "strict"
    corpus_version_id: str | None = None
    index_version_id: str | None = None
    verifier_version: str | None = None
    filters: ContextFilters = field(default_factory=ContextFilters)
    require_index: bool = False

    def __post_init__(self) -> None:
        _require_aware("request_time", self.request_time)
        if isinstance(self.as_of, datetime):
            _require_aware("as_of", self.as_of)


@dataclass(frozen=True)
class EvidenceContext:
    """Stable resolved context every result echoes (``mcp-evidence-context/v1``).

    Non-index tools carry None for ``index_version_id``; status echoes an
    explicit index pin or None, while search carries its resolved index.
    Non-verification tools carry ``deterministic-v1`` as ``verifier_version``.
    Expiring cursor bytes and live status never change this context's replay
    guarantee.
    """

    effective_as_of: datetime
    timestamp_mode: TimestampMode
    temporal_guarantee: TemporalGuarantee
    corpus_version_id: str
    index_version_id: str | None
    parser_version: str | None
    verifier_version: str
    document_version_id: str | None
    filters: ContextFilters

    def __post_init__(self) -> None:
        _require_aware("effective_as_of", self.effective_as_of)
        expected = "strict" if self.timestamp_mode == "strict" else "none"
        if self.temporal_guarantee != expected:
            raise ValueError(f"timestamp_mode {self.timestamp_mode} requires guarantee {expected}")


@dataclass(frozen=True)
class DateRange:
    """Publication-time range; ``from_`` is the schema's ``from``."""

    from_: datetime | None
    to: datetime | None


@dataclass(frozen=True)
class CoverageNote:
    """Issuers (CIKs), forms and public_at range searched (§7)."""

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
    public_at: datetime | None
    public_at_basis: PublicAtBasis | None


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
    public_at: datetime | None
    public_at_basis: PublicAtBasis | None
    timestamp_precision: ServedTimestampPrecision
    reader_url: str | None = None
    offset_unit: Literal["unicode_code_point"] = OFFSET_UNIT
    untrusted_source_text: Literal[True] = True

    def __post_init__(self) -> None:
        if not 0 <= self.start_char <= self.end_char:
            raise ValueError("citation offsets must satisfy 0 <= start_char <= end_char")
        _check_publication(
            self.accepted_at, self.public_at, self.public_at_basis, self.timestamp_precision
        )


@dataclass(frozen=True)
class SpanIdRef:
    span_id: str


@dataclass(frozen=True)
class SpanRangeRef:
    document_version_id: str
    start_char: int
    end_char: int

    def __post_init__(self) -> None:
        if not 0 <= self.start_char <= self.end_char:
            raise ValueError("span range must satisfy 0 <= start_char <= end_char")


SpanRef = SpanIdRef | SpanRangeRef


# ---------------------------------------------------------------------------
# Tool requests and results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolveCompanyRequest:
    query: str


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
    evidence_context: EvidenceContext
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
    public_at: datetime | None
    public_at_basis: PublicAtBasis | None
    timestamp_precision: ServedTimestampPrecision
    period_end: date | None
    document_id: str
    document_version_id: str
    source_url: str
    content_hash: str
    amends: str | None

    def __post_init__(self) -> None:
        _check_publication(
            self.accepted_at, self.public_at, self.public_at_basis, self.timestamp_precision
        )


@dataclass(frozen=True)
class ListFilingsResult:
    evidence_context: EvidenceContext
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
    evidence_context: EvidenceContext
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

    def __post_init__(self) -> None:
        if (self.document_id is None) == (self.accession is None):
            raise ValueError("exactly one of document_id or accession is required")


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
    public_at: datetime | None
    public_at_basis: PublicAtBasis | None
    timestamp_precision: ServedTimestampPrecision
    source_url: str
    document_content_hash: str

    def __post_init__(self) -> None:
        _check_publication(
            self.accepted_at, self.public_at, self.public_at_basis, self.timestamp_precision
        )


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
    offset_unit: Literal["unicode_code_point"] = OFFSET_UNIT
    untrusted_source_text: Literal[True] = True


@dataclass(frozen=True)
class ReadFilingResult:
    evidence_context: EvidenceContext
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

    evidence_context: EvidenceContext
    coverage_note: CoverageNote
    citation: Citation
    hash_verified: Literal[True] = True


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

    def __post_init__(self) -> None:
        if not _DECIMAL_STRING.fullmatch(self.value):
            raise ValueError("fact value must be a plain decimal string")


@dataclass(frozen=True)
class FactsResult:
    evidence_context: EvidenceContext
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

    effective_as_of: datetime
    issuers: tuple[IssuerCoverage, ...]
    date_range: DateRange
    timestamp_precision_mix: Mapping[StoredTimestampPrecision, int]


@dataclass(frozen=True)
class CorpusCoverageResult:
    evidence_context: EvidenceContext
    coverage_note: CoverageNote
    coverage: CorpusCoverage

    def __post_init__(self) -> None:
        if self.coverage.effective_as_of != self.evidence_context.effective_as_of:
            raise ValueError("coverage.effective_as_of must equal evidence_context's")


@dataclass(frozen=True)
class CorpusVersionRow:
    id: str
    status: str
    published_at: datetime | None


@dataclass(frozen=True)
class IndexVersionRow:
    id: str
    corpus_version_id: str
    status: str
    published_at: datetime | None


@dataclass(frozen=True)
class Limitation:
    code: str
    text: str


@dataclass(frozen=True)
class LiveStatus:
    """``get_corpus_status.live_status``: request-time state, never replayable."""

    observed_at: datetime
    active_corpus_version_id: str | None
    retained_corpus_versions: tuple[CorpusVersionRow, ...]
    active_index_version_id: str | None
    retained_index_versions: tuple[IndexVersionRow, ...]
    verifier_versions: tuple[str, ...]
    known_limitations: tuple[Limitation, ...]
    replayable: Literal[False] = False

    def __post_init__(self) -> None:
        missing = REQUIRED_LIMITATION_CODES - {lim.code for lim in self.known_limitations}
        if missing:
            raise ValueError(f"known_limitations must state {sorted(missing)}")


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

    def __post_init__(self) -> None:
        if self.scale not in NUMERIC_SCALES:
            raise ValueError(f"numeric scale must be one of {sorted(NUMERIC_SCALES)}")
        if not self.value.is_finite():
            raise ValueError("numeric value must be finite")


@dataclass(frozen=True)
class CitedSpan:
    """One request citation: a span reference and an optional verbatim quote."""

    ref: SpanRef
    quote: str | None = None


@dataclass(frozen=True)
class VerifyClaimRequest:
    claim: str
    citations: tuple[CitedSpan, ...]
    numeric: ClaimNumeric | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.citations) <= 10:
            raise ValueError("verify_claim takes 1 to 10 citations")


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
    ``numeric_checks=None``; ``CitationVerdict.not_visible`` builds it.
    """

    index: int
    checks: IntegrityChecks
    reason: IntegrityReason | Literal["not_found"] | None
    edge_status: EdgeStatus
    numeric_checks: NumericChecks | None

    def __post_init__(self) -> None:
        if not 0 <= self.index <= 9:
            raise ValueError("citation index must be 0..9")
        if not self.checks.visible and (
            self.checks != IntegrityChecks(False, None, None)
            or self.reason != "not_found"
            or self.edge_status != "irrelevant"
            or self.numeric_checks is not None
        ):
            raise ValueError("a not-visible citation has exactly one uninformative shape")
        passed = self.checks.hash_valid is True and self.checks.quote_found is not False
        if self.checks.visible and (self.reason == "not_found" or (self.reason is None) != passed):
            raise ValueError("reason must name the first failed integrity check, or be None")

    @classmethod
    def not_visible(cls, index: int) -> CitationVerdict:
        return cls(index, IntegrityChecks(False, None, None), "not_found", "irrelevant", None)


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
    evidence_context: EvidenceContext
    coverage_note: CoverageNote
    report: VerificationReport


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class EvidenceReadService(Protocol):
    """Cutoff-guarded public-corpus reads on the read-only role (#395).

    Every method except ``resolve_context`` and ``live_status`` reads only
    evidence visible under ``context``: in strict mode, documents whose
    verified ``public_at`` is at or before ``effective_as_of``. A hidden or
    missing reference raises ``EvidenceReadError.not_found()`` through one
    code path.
    """

    def resolve_context(self, request: ContextRequest) -> EvidenceContext:
        """Resolve cutoff/pins without active-index or latest-verifier drift.

        A None index pin stays None unless ``request.require_index`` is True
        (search only), when the service resolves a compatible published index.
        Explicit pins are validated, including index/corpus compatibility;
        ``pin_unavailable`` names an unavailable pin. An omitted verifier pin
        resolves to ``deterministic-v1``.
        """
        ...

    def resolve_company(
        self, request: ResolveCompanyRequest, context: EvidenceContext
    ) -> ResolveCompanyResult:
        """Coverage counts only filings whose ``public_at`` is visible."""
        ...

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

    def corpus_coverage(self, context: EvidenceContext) -> CorpusCoverageResult: ...

    def live_status(self, observed_at: datetime) -> LiveStatus: ...


@runtime_checkable
class VerificationReportBuilder(Protocol):
    """Builds a ``mcp-verification-report/v1`` report (#396).

    Integrity checks (visible, hash_valid, quote_found) run in front of the
    unchanged deterministic rules. ``claim_status`` is never ``supported``
    without whole-evidence text identity. ``visible`` uses ``public_at``.
    """

    def build(self, request: VerifyClaimRequest, context: EvidenceContext) -> VerifyClaimResult: ...

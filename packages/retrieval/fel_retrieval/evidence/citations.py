"""Guarded citation read (#395, MCP-401 and MCP-404; design contract §7.1).

``get_citation`` resolves a span reference only inside the visible evidence
set of its context. A reference to a hidden span and a reference to nothing
both find no row and raise the same ``not_found``. The returned text is sliced
from canonical text by Unicode code points and its SHA-256 is recomputed; a
mismatch fails closed with ``integrity_error`` and nothing is returned.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final, Protocol

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.limits import check_request
from fel_retrieval.evidence.visibility import (
    VISIBLE_VERSIONS,
    public_read_session,
    visibility_params,
)
from fel_retrieval.hashing import content_sha256
from fel_retrieval.index_build import DBConnection

MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024  # §7.4: canonical-text bytes per request
_RETRY_AFTER_SECONDS: Final = 30
_LOG = logging.getLogger(__name__)


class CanonicalTextStore(Protocol):
    """Reads immutable canonical text objects by ``canonical_text_key``."""

    def read(self, key: str, limit: int) -> bytes:
        """At most the first ``limit`` bytes. ``LookupError`` if absent, ``OSError`` on outage."""
        ...


_SPAN_SELECT: Final = " ".join(
    [
        "SELECT ss.id, ss.start_char, ss.end_char, ss.text_hash, s.heading_path,",
        "dv.id, dv.parser_version, dv.canonical_text_key,",
        "d.id, d.entity_id, d.accession, d.form, d.source_url, d.content_hash,",
        "(d.published_at AT TIME ZONE 'UTC')::date, d.accepted_at, d.public_at,",
        "d.public_at_basis",
        "FROM",
        VISIBLE_VERSIONS,
        "JOIN source_spans ss ON ss.document_version_id = dv.id",
        "JOIN sections s ON s.id = ss.section_id",
    ]
)
# LIMIT 2: a second row means the reference is ambiguous, which fails closed.
_SPAN_BY_ID: Final = _SPAN_SELECT + " WHERE ss.id = %(span)s ORDER BY ss.id LIMIT 2"
_SPAN_BY_RANGE: Final = _SPAN_SELECT + (
    " WHERE dv.id = %(version)s AND ss.start_char = %(start)s AND ss.end_char = %(end)s"
    " ORDER BY ss.id LIMIT 2"
)
_COVERAGE: Final = " ".join(
    [
        "SELECT min(d.public_at), max(d.public_at) FROM",
        VISIBLE_VERSIONS,
        "WHERE d.entity_id = %(entity)s AND d.form IS NOT DISTINCT FROM %(form)s",
    ]
)


def _integrity_error(reason: str, span_id: str) -> i.EvidenceReadError:
    _LOG.error("evidence integrity failure: %s (span %s)", reason, span_id)
    return i.EvidenceReadError(
        "integrity_error",
        "Stored evidence failed integrity verification and was not returned.",
        retryable=False,
        recovery="This is a server-side fault. Report the reference to the operator.",
    )


def _instant(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _verified_text(
    texts: CanonicalTextStore, key: str, start: int, end: int, text_hash: str, span_id: str
) -> str:
    """The span's text, sliced by code points, once its recomputed hash matches."""
    try:
        raw = texts.read(key, MAX_CANONICAL_BYTES + 1)
    except LookupError:
        raise _integrity_error("canonical text object is absent", span_id) from None
    except OSError as error:
        raise i.EvidenceReadError(
            "unavailable",
            "Evidence storage is temporarily unavailable.",
            retryable=True,
            recovery="Wait, then retry.",
            retry_after_seconds=_RETRY_AFTER_SECONDS,
        ) from error
    if len(raw) > MAX_CANONICAL_BYTES:
        raise _integrity_error("canonical text exceeds the per-request read cap", span_id)
    try:
        canonical = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _integrity_error("canonical text is not UTF-8", span_id) from None
    if end > len(canonical):
        raise _integrity_error("span offsets lie outside the canonical text", span_id)
    text = canonical[start:end]
    if content_sha256(text) != text_hash:
        raise _integrity_error("recomputed text hash differs from the stored hash", span_id)
    return text


def get_citation(
    conn: DBConnection,
    ref: i.SpanRef,
    context: i.EvidenceContext,
    *,
    companies: Mapping[str, i.Company],
    texts: CanonicalTextStore,
) -> i.CitationResult:
    """One verified Citation, or ``not_found`` for a hidden, stale or missing reference.

    ``companies`` maps ``entity_id`` to the served cohort; evidence of an
    issuer outside it is not served.
    """
    check_request(ref)
    params: dict[str, Any] = visibility_params(context)
    if isinstance(ref, i.SpanIdRef):
        query = _SPAN_BY_ID
        params["span"] = ref.span_id
    else:
        query = _SPAN_BY_RANGE
        params.update(version=ref.document_version_id, start=ref.start_char, end=ref.end_char)

    with public_read_session(conn):
        rows = conn.execute(query, params).fetchall()
        company = companies.get(str(rows[0][9])) if rows else None
        if company is None:
            raise i.EvidenceReadError.not_found()
        row = rows[0]
        # An aggregate always returns one row, and it covers at least this filing.
        scope = {**visibility_params(context), "entity": row[9], "form": row[11]}
        coverage = conn.execute(_COVERAGE, scope)
        first, last = (instant.astimezone(UTC) for instant in coverage.fetchall()[0])

    span_id, start, end = str(row[0]), int(row[1]), int(row[2])
    if len(rows) > 1:
        raise _integrity_error("more than one stored span answers the reference", span_id)
    text = _verified_text(texts, str(row[7]), start, end, str(row[3]), span_id)
    form = None if row[11] is None else str(row[11])
    citation = i.Citation(
        span_id=span_id,
        accession=str(row[10]),
        form=form,
        company=company,
        document_id=str(row[8]),
        document_version_id=str(row[5]),
        parser_version=str(row[6]),
        section_path=tuple(row[4]),
        start_char=start,
        end_char=end,
        text=text,
        text_hash=str(row[3]),
        document_content_hash=str(row[13]),
        source_url=str(row[12]),
        filing_date=row[14],
        accepted_at=row[15].astimezone(UTC),
        public_at=row[16].astimezone(UTC),
        public_at_basis=row[17],
        timestamp_precision="second",
    )
    note = i.CoverageNote(
        text=(
            f"Searched {form or 'unlabeled'} filings of {company.name} (CIK {company.cik}) "
            f"public from {_instant(first)} to {_instant(last)}, "
            f"visible at {_instant(context.effective_as_of)}."
        ),
        issuers=(company.cik,),
        forms=() if form is None else (form,),
        date_range=i.DateRange(from_=first, to=last),
    )
    return i.CitationResult(evidence_context=context, coverage_note=note, citation=citation)

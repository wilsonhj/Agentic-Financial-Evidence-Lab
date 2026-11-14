"""Company resolver and filing listing (#395, MCP-403; design contract §7).

Both read only ``VISIBLE_VERSIONS``. A company is resolved against the injected
cohort and then kept only if it has a filing visible under the context, so a
company whose filings are all hidden is treated exactly like a company that is
not served: ``resolve_company`` omits it and ``list_filings`` raises
``not_found``. The same statements run in both cases. Coverage counts, form
lists and date ranges are computed under the same predicate.

Listings are ordered newest first by ``(public_at, document id)`` and paged
with a keyset cursor, so page boundaries are stable for a context.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.citations import _instant, _integrity_error
from fel_retrieval.evidence.cursors import CursorCodec
from fel_retrieval.evidence.limits import check_request, invalid_input
from fel_retrieval.evidence.visibility import (
    VISIBLE_VERSIONS,
    public_read_session,
    visibility_params,
)
from fel_retrieval.index_build import DBConnection

MAX_MATCHES: Final = 20  # mcp-resolve-company-output: matches.maxItems
_FILING_REF: Final = (
    "d.entity_id, d.accession, d.form, (d.published_at AT TIME ZONE 'UTC')::date, "
    "d.accepted_at, d.public_at, d.public_at_basis"
)
_IN_SCOPE: Final = "WHERE d.entity_id = ANY(%(entities)s::uuid[])"
# Per issuer and form: visible filings and their publication range.
_FORM_STATS: Final = " ".join(
    [
        "SELECT d.entity_id, d.form, count(DISTINCT d.id), min(d.public_at), max(d.public_at)",
        "FROM",
        VISIBLE_VERSIONS,
        _IN_SCOPE,
        "GROUP BY d.entity_id, d.form ORDER BY d.entity_id, d.form",
    ]
)
_EDGE_SELECT: Final = " ".join(
    ["SELECT DISTINCT ON (d.entity_id)", _FILING_REF, "FROM", VISIBLE_VERSIONS, _IN_SCOPE]
)
_FIRST: Final = _EDGE_SELECT + " ORDER BY d.entity_id, d.public_at ASC, d.id ASC"
_LAST: Final = _EDGE_SELECT + " ORDER BY d.entity_id, d.public_at DESC, d.id DESC"
# The window count exposes a document with two parsed versions in one corpus pin.
_PAGE: Final = " ".join(
    [
        "SELECT",
        _FILING_REF,
        ", d.period_end, d.id, dv.id, d.source_url, d.content_hash,",
        "count(*) OVER (PARTITION BY d.id)",
        "FROM",
        VISIBLE_VERSIONS,
        "WHERE d.entity_id = %(entity)s",
        "AND (%(forms)s::text[] IS NULL OR d.form = ANY(%(forms)s::text[]))",
        "AND (%(after_id)s::uuid IS NULL",
        "OR (d.public_at, d.id) < (%(after_public)s::timestamptz, %(after_id)s::uuid))",
        "ORDER BY d.public_at DESC, d.id DESC LIMIT %(take)s",
    ]
)


def match_companies(
    companies: Mapping[str, i.Company], text: str, *, partial: bool
) -> list[i.Company]:
    """Cohort companies named by ``text``: exact identifier matches, then name fragments.

    An identifier is the entity id, the CIK (leading zeros optional), the
    ticker or the full name, compared case-insensitively.
    """
    needle = text.strip().casefold()
    if not needle:
        return []
    cik = needle.zfill(10) if needle.isascii() and needle.isdigit() else None
    exact: list[i.Company] = []
    fragments: list[i.Company] = []
    for company in sorted(companies.values(), key=lambda c: (c.name.casefold(), c.cik)):
        identifiers = {company.entity_id.casefold(), company.name.casefold()}
        if company.ticker is not None:
            identifiers.add(company.ticker.casefold())
        if needle in identifiers or cik == company.cik:
            exact.append(company)
        elif partial and needle in company.name.casefold():
            fragments.append(company)
    return exact + fragments


def _form_stats(
    conn: DBConnection, visible: dict[str, Any], candidates: list[i.Company]
) -> dict[str, dict[str | None, tuple[int, datetime, datetime]]]:
    """Per entity and form, for the candidates that have a visible filing."""
    scope = {**visible, "entities": [company.entity_id for company in candidates]}
    stats: dict[str, dict[str | None, tuple[int, datetime, datetime]]] = {}
    for entity_id, form, count, first, last in conn.execute(_FORM_STATS, scope).fetchall():
        by_form = stats.setdefault(str(entity_id), {})
        by_form[form] = (int(count), first.astimezone(UTC), last.astimezone(UTC))
    return stats


def _coverage_note(
    context: i.EvidenceContext,
    issuers: list[i.Company],
    forms: list[str],
    ranges: list[tuple[int, datetime, datetime]],
) -> i.CoverageNote:
    cutoff = _instant(context.effective_as_of.astimezone(UTC))
    if not ranges:
        text = f"No matching evidence in the visible indexed corpus at {cutoff}."
        first = last = None
    else:
        first, last = min(r[1] for r in ranges), max(r[2] for r in ranges)
        names = ", ".join(f"{company.name} (CIK {company.cik})" for company in issuers)
        text = (
            f"Searched {', '.join(forms) or 'unlabeled'} filings of {names} public from "
            f"{_instant(first)} to {_instant(last)}, visible at {cutoff}."
        )
    return i.CoverageNote(
        text=text,
        issuers=tuple(company.cik for company in issuers),
        forms=tuple(forms),
        date_range=i.DateRange(from_=first, to=last),
    )


def _filing_ref(row: tuple[Any, ...]) -> i.FilingRef:
    return i.FilingRef(
        accession=str(row[1]),
        form=row[2],
        filing_date=row[3],
        accepted_at=row[4].astimezone(UTC),
        public_at=row[5].astimezone(UTC),
        public_at_basis=row[6],
    )


def resolve_company(
    conn: DBConnection,
    request: i.ResolveCompanyRequest,
    context: i.EvidenceContext,
    *,
    companies: Mapping[str, i.Company],
) -> i.ResolveCompanyResult:
    """Cohort companies matching the query that have a filing visible under ``context``."""
    check_request(request)
    visible = visibility_params(context)
    candidates = match_companies(companies, request.query, partial=True)
    with public_read_session(conn):
        stats = _form_stats(conn, visible, candidates)
        shown = [company for company in candidates if company.entity_id in stats][:MAX_MATCHES]
        scope = {**visible, "entities": [company.entity_id for company in shown]}
        first = {str(row[0]): _filing_ref(row) for row in conn.execute(_FIRST, scope).fetchall()}
        last = {str(row[0]): _filing_ref(row) for row in conn.execute(_LAST, scope).fetchall()}
    matches = []
    for company in shown:
        by_form = stats[company.entity_id]
        coverage = i.CompanyCoverage(
            first_visible_filing=first[company.entity_id],
            last_visible_filing=last[company.entity_id],
            visible_forms=tuple(sorted(form for form in by_form if form is not None)),
            visible_filing_count=sum(count for count, _, _ in by_form.values()),
        )
        matches.append(i.CompanyMatch(company=company, coverage=coverage))
    forms = sorted({form for match in matches for form in match.coverage.visible_forms})
    ranges = [entry for company in shown for entry in stats[company.entity_id].values()]
    return i.ResolveCompanyResult(
        evidence_context=context,
        coverage_note=_coverage_note(context, shown, forms, ranges),
        matches=tuple(matches),
    )


def list_filings(
    conn: DBConnection,
    request: i.ListFilingsRequest,
    context: i.EvidenceContext,
    *,
    companies: Mapping[str, i.Company],
    cursors: CursorCodec,
) -> i.ListFilingsResult:
    """One page of a company's visible filings, newest first.

    ``not_found`` when the company is not served or has no visible filing;
    ``invalid_input`` when the reference names more than one visible company.
    """
    check_request(request)
    visible = visibility_params(context)
    forms = None if request.forms is None else sorted(request.forms)
    binding = {"tool": "list_filings", "company": request.company, "forms": forms}
    after_public, after_id = (
        (None, None) if request.cursor is None else cursors.decode(request.cursor, context, binding)
    )
    candidates = match_companies(companies, request.company, partial=False)
    with public_read_session(conn):
        stats = _form_stats(conn, visible, candidates)
        shown = [company for company in candidates if company.entity_id in stats]
        if not shown:
            raise i.EvidenceReadError.not_found()
        if len(shown) > 1:
            raise invalid_input("company", "names more than one company; use its entity_id or CIK")
        page = {
            **visible,
            "entity": shown[0].entity_id,
            "forms": forms,
            "after_public": after_public,
            "after_id": after_id,
            "take": request.limit + 1,
        }
        rows = conn.execute(_PAGE, page).fetchall()
    by_form = stats[shown[0].entity_id]
    searched = sorted(form for form in by_form if form is not None) if forms is None else forms
    ranges = [entry for form, entry in by_form.items() if forms is None or form in forms]
    filings = []
    for row in rows[: request.limit]:
        if row[12] != 1:
            reason = "a document has more than one parsed version in the pinned corpus"
            raise _integrity_error(reason, f"document {row[8]}")
        ref = _filing_ref(row)
        filings.append(
            i.FilingMeta(
                entity_id=str(row[0]),
                accession=ref.accession,
                form=ref.form,
                filing_date=ref.filing_date,
                accepted_at=ref.accepted_at,
                public_at=ref.public_at,
                public_at_basis=ref.public_at_basis,
                timestamp_precision="second",
                period_end=row[7],
                document_id=str(row[8]),
                document_version_id=str(row[9]),
                source_url=str(row[10]),
                content_hash=str(row[11]),
                amends=None,  # the corpus stores no amendment link to resolve
            )
        )
    next_cursor = None
    if len(rows) > request.limit:
        last_row = rows[request.limit - 1]
        position = [last_row[5].astimezone(UTC).isoformat(), str(last_row[8])]
        next_cursor = cursors.encode(context, binding, position)
    return i.ListFilingsResult(
        evidence_context=context,
        coverage_note=_coverage_note(context, shown, searched, ranges),
        filings=tuple(filings),
        next_cursor=next_cursor,
    )

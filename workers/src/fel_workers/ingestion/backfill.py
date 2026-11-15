"""Publication-time backfill and restatement-link repair (#393, MCP-203/204).

One ``sec_publication_backfill`` job per issuer does two things in a single
transaction, using only the columns migration 0013 grants ``fel_worker``:

1. **Backfill.** For each of the issuer's filings listed in the submissions
   index, derive the publication columns with ``derive_publication`` and set
   them where they are still NULL. A row is left NULL when it cannot be
   verified: no acceptance time, an unusable one, or a stored filing date
   that disagrees with the index. A row that already holds values is never
   written: equal values need no write. A stored filing date or publication
   time that differs from the index is reported as a conflict for an
   operator, never overwritten. Company-facts snapshots are
   excluded by form in both the read and the write.

2. **Repair.** Recompute every filing fact's ``restates`` from the stored
   rows, with the rule ingest uses (``pipeline._prior_canonical_facts``),
   and write only the facts whose link is wrong. The result depends on the
   set of filings, not on the order they were ingested in.

Published pins never change (ADR-0034 Amendment 2). A document with any
version in an ``active`` or ``superseded`` corpus version keeps its
publication columns, and a fact in such a version keeps its ``restates``.
The change is rejected and reported instead: ``BackfillReport.rejected``
and ``RepairReport.rejected_versions``. Both steps take
``pipeline.lock_corpus_publication`` before reading pin membership and hold
it to commit, and corpus publication takes the same lock, so no pin can be
published between the check and the write or over uncommitted writes.

Both steps are idempotent and a rerun does only the work still outstanding.
Nothing here runs at ingest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from fel_providers.interfaces import SecClient
from fel_workers.ingestion.company_facts import entity_id_for_cik
from fel_workers.ingestion.discovery import discover_filings
from fel_workers.ingestion.pipeline import PINNED_CORPUS_STATUSES, lock_corpus_publication
from fel_workers.ingestion.publication import Publication, derive_publication
from fel_workers.ingestion.raw_store import COMPANY_FACTS_FORM

JOB_KIND_SEC_PUBLICATION_BACKFILL = "sec_publication_backfill"


@dataclass(frozen=True)
class RepairReport:
    """What one restatement repair changed. All zero means nothing was written."""

    linked: int = 0
    """Facts that had no link and now restate an earlier filing's fact."""
    relinked: int = 0
    """Facts moved to a different, later-published target filing."""
    cleared: int = 0
    """Facts whose link pointed at a filing that is not an earlier restated one."""
    document_version_ids: tuple[str, ...] = ()
    """Versions holding a changed fact."""
    rejected_versions: tuple[str, ...] = ()
    """Versions in a published pin whose facts' links would have changed; left
    as they are for a lead decision."""


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of one issuer's backfill job."""

    updated: int = 0
    """Documents whose publication columns were set by this run."""
    unresolved: int = 0
    """The issuer's filings that still have no publication time."""
    conflicts: tuple[str, ...] = ()
    """Accessions whose stored filing date or publication time differs from
    the index; left untouched."""
    rejected: tuple[str, ...] = ()
    """Accessions in a published pin that the index would resolve; left
    unresolved for a lead decision."""
    repair: RepairReport = field(default_factory=RepairReport)


# The expected target of a fact is the canonical fact with the same key in
# the latest parsed version of the latest earlier filing, when its value
# differs: exactly what ingest links (``pipeline._prior_canonical_facts``).
# A predecessor needs a known public_at strictly before the fact's own
# known public_at; the filing date never orders a pair. A link already
# pointing at the expected filing through an older parse of it is the same
# edge and is kept. Changes to facts in a published pin are not written;
# they come back flagged as rejected.
# A document version is pinned while any corpus version holding it is active
# or superseded (superseded pins are still readable). The three statements
# below spell that test out in full rather than splice it in.

_REPAIR_SQL = """
WITH filing AS (
    SELECT d.id, d.accession, d.public_at,
           (SELECT dv.id FROM document_versions dv
            WHERE dv.document_id = d.id AND dv.status = 'parsed'
            ORDER BY dv.created_at DESC, dv.id DESC
            LIMIT 1) AS latest_version_id
    FROM documents d
    WHERE d.entity_id = %(entity_id)s AND d.form IS DISTINCT FROM %(company_facts)s
),
expected AS (
    SELECT f.id, f.document_version_id, f.restates AS held_id, target.id AS target_id,
           EXISTS (SELECT 1 FROM corpus_version_documents cvd
                   JOIN corpus_versions cv ON cv.id = cvd.corpus_version_id
                   WHERE cvd.document_version_id = f.document_version_id
                     AND cv.status = ANY(%(pinned)s)) AS pinned,
           (target.id IS NOT NULL
            AND held.fact_key = f.fact_key
            AND held.duplicate_of IS NULL
            AND held_version.document_id = target.document_id) AS same_edge
    FROM financial_facts f
    JOIN document_versions fv ON fv.id = f.document_version_id
    JOIN filing fd ON fd.id = fv.document_id
    LEFT JOIN LATERAL (
        SELECT p.id, p.value, pd.id AS document_id
        FROM filing pd
        JOIN financial_facts p ON p.document_version_id = pd.latest_version_id
        WHERE p.entity_id = f.entity_id
          AND p.fact_key = f.fact_key
          AND p.duplicate_of IS NULL
          AND pd.public_at < fd.public_at
        ORDER BY pd.public_at DESC, pd.accession DESC, p.id
        LIMIT 1
    ) target ON target.value <> f.value
    LEFT JOIN financial_facts held ON held.id = f.restates
    LEFT JOIN document_versions held_version ON held_version.id = held.document_version_id
    WHERE f.entity_id = %(entity_id)s
),
change AS (
    SELECT * FROM expected
    WHERE held_id IS DISTINCT FROM target_id AND same_edge IS NOT TRUE
),
applied AS (
    UPDATE financial_facts f
    SET restates = c.target_id
    FROM change c
    WHERE f.id = c.id AND NOT c.pinned
    RETURNING f.document_version_id, c.held_id IS NULL AS was_null,
              c.target_id IS NULL AS now_null
)
SELECT false, document_version_id, was_null, now_null FROM applied
UNION ALL
SELECT true, document_version_id, held_id IS NULL, target_id IS NULL
FROM change WHERE pinned
"""


def repair_restatement_links(conn: psycopg.Connection[Any], *, entity_id: str) -> RepairReport:
    """Make one issuer's ``restates`` links what in-order ingest would produce.

    One statement under the corpus-publication lock; writes only
    ``financial_facts.restates``, only on rows whose link is wrong and never
    on a fact in a published pin, so a second run changes nothing.
    """
    with conn.transaction():
        _lock_for_pin_check(conn)
        rows = conn.execute(
            _REPAIR_SQL,
            {
                "entity_id": entity_id,
                "company_facts": COMPANY_FACTS_FORM,
                "pinned": list(PINNED_CORPUS_STATUSES),
            },
        ).fetchall()
    applied = [row[1:] for row in rows if not row[0]]
    return RepairReport(
        linked=sum(1 for _, was_null, now_null in applied if was_null and not now_null),
        relinked=sum(1 for _, was_null, now_null in applied if not was_null and not now_null),
        cleared=sum(1 for _, was_null, now_null in applied if now_null),
        document_version_ids=tuple(sorted({str(version) for version, _, _ in applied})),
        rejected_versions=tuple(sorted({str(row[1]) for row in rows if row[0]})),
    )


def _lock_for_pin_check(conn: psycopg.Connection[Any]) -> None:
    """Take the publication lock, then insist that later reads see commits.

    Under REPEATABLE READ the snapshot would be fixed by the lock statement
    itself, before any wait, and a publication committed while waiting would
    stay invisible to the pin check.
    """
    lock_corpus_publication(conn)
    level = conn.execute("SHOW transaction_isolation").fetchone()
    if level is None or level[0] != "read committed":
        raise RuntimeError("the pin check needs READ COMMITTED isolation")


def _backfill_publication(
    conn: psycopg.Connection[Any], client: SecClient, cik: str, entity_id: str
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Set the publication columns still NULL outside published pins.

    Returns (updated, conflicts, rejected). The caller holds the lock.
    """
    refs = {ref.accession: ref for ref in discover_filings(client, cik)}
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT d.id, d.accession, d.filed_at, d.accepted_at, d.public_at,"
            " d.public_at_basis, d.timestamp_precision, EXISTS ("
            "   SELECT 1 FROM document_versions dv"
            "   JOIN corpus_version_documents cvd ON cvd.document_version_id = dv.id"
            "   JOIN corpus_versions cv ON cv.id = cvd.corpus_version_id"
            "   WHERE dv.document_id = d.id AND cv.status = ANY(%(pinned)s)"
            " ) AS pinned FROM documents d"
            " WHERE d.entity_id = %(entity_id)s AND d.form IS DISTINCT FROM %(company_facts)s"
            " AND d.accession = ANY(%(accessions)s) ORDER BY d.accession",
            {
                "entity_id": entity_id,
                "company_facts": COMPANY_FACTS_FORM,
                "accessions": list(refs),
                "pinned": list(PINNED_CORPUS_STATUSES),
            },
        ).fetchall()
    updated = 0
    conflicts: list[str] = []
    rejected: list[str] = []
    for row in rows:
        ref = refs[str(row["accession"])]
        # Only a row ingested with this exact filing date is the filing the
        # index describes; anything else is reported and stays as it is.
        if row["filed_at"] != datetime.combine(ref.filed_on, time(0), tzinfo=UTC):
            conflicts.append(ref.accession)
            continue
        try:
            derived = derive_publication(ref.acceptance_datetime, ref.filed_on)
        except ValueError:
            continue  # an unusable acceptance time resolves nothing
        if derived.accepted_at is None:
            continue
        if row["accepted_at"] is not None:
            stored = Publication(
                row["accepted_at"],
                row["public_at"],
                row["public_at_basis"],
                row["timestamp_precision"],
            )
            if stored != derived:
                conflicts.append(ref.accession)
            continue
        if row["pinned"]:
            rejected.append(ref.accession)  # a published pin keeps what it showed
            continue
        # The predicate repeats every guard so the write itself can never
        # replace a stored publication time, touch a company-facts row or
        # change a pinned document.
        updated += conn.execute(
            "UPDATE documents d SET accepted_at = %(accepted_at)s, public_at = %(public_at)s,"
            " public_at_basis = %(basis)s, timestamp_precision = %(precision)s"
            " WHERE d.id = %(id)s AND d.accepted_at IS NULL"
            " AND d.form IS DISTINCT FROM %(company_facts)s AND NOT EXISTS ("
            "   SELECT 1 FROM document_versions dv"
            "   JOIN corpus_version_documents cvd ON cvd.document_version_id = dv.id"
            "   JOIN corpus_versions cv ON cv.id = cvd.corpus_version_id"
            "   WHERE dv.document_id = d.id AND cv.status = ANY(%(pinned)s))",
            {
                "accepted_at": derived.accepted_at,
                "public_at": derived.public_at,
                "basis": derived.public_at_basis,
                "precision": derived.timestamp_precision,
                "id": row["id"],
                "company_facts": COMPANY_FACTS_FORM,
                "pinned": list(PINNED_CORPUS_STATUSES),
            },
        ).rowcount
    return updated, tuple(conflicts), tuple(rejected)


def run_publication_backfill_job(
    conn: psycopg.Connection[Any], client: SecClient, payload: dict[str, Any]
) -> BackfillReport:
    """Handle a ``sec_publication_backfill`` job for one issuer (``cik``).

    The submissions index comes from the injected client: the pinned fixture
    transport in every mock run. All writes commit together or not at all,
    under the corpus-publication lock taken before anything is read.
    """
    cik = str(payload.get("cik", ""))
    entity_id = entity_id_for_cik(cik)
    with conn.transaction():
        _lock_for_pin_check(conn)
        updated, conflicts, rejected = _backfill_publication(conn, client, cik, entity_id)
        repair = repair_restatement_links(conn, entity_id=entity_id)
        remaining = conn.execute(
            "SELECT count(*) FROM documents"
            " WHERE entity_id = %s AND form IS DISTINCT FROM %s AND accepted_at IS NULL",
            (entity_id, COMPANY_FACTS_FORM),
        ).fetchone()
    return BackfillReport(
        updated=updated,
        unresolved=int(remaining[0]) if remaining else 0,
        conflicts=conflicts,
        rejected=rejected,
        repair=repair,
    )

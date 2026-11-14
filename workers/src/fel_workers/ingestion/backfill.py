"""Publication-time backfill and restatement-link repair (#393, MCP-203/204).

One ``sec_publication_backfill`` job per issuer does two things in a single
transaction, using only the columns migration 0013 grants ``fel_worker``:

1. **Backfill.** For each of the issuer's filings listed in the submissions
   index, derive the publication columns with ``derive_publication`` and set
   them where they are still NULL. A row is left NULL when it cannot be
   verified: no acceptance time, an unusable one, or a stored filing date
   that disagrees with the index. A row that already holds values is never
   written: equal values need no write, and different ones are reported as a
   conflict for an operator, not overwritten. Company-facts snapshots are
   excluded by form in both the read and the write.

2. **Repair.** Recompute every filing fact's ``restates`` from the stored
   rows, with the ordering ingest uses (``pipeline._prior_canonical_facts``),
   and write only the facts whose link is wrong. The result depends on the
   set of filings, not on the order they were ingested in.

Both steps are idempotent and a rerun does only the work still outstanding.
A repair changes rows that corpus pins may already expose, so the report
names the document versions it touched (ADR-0034 Amendment 2: repair before
exposing pins, or retire the affected ones). Nothing here runs at ingest.
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
    """Versions holding a changed fact: the corpus pins a repair can affect."""


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of one issuer's backfill job."""

    updated: int = 0
    """Documents whose publication columns were set by this run."""
    unresolved: int = 0
    """The issuer's filings that still have no publication time."""
    conflicts: tuple[str, ...] = ()
    """Accessions whose stored values differ from the index; left untouched."""
    repair: RepairReport = field(default_factory=RepairReport)


# The expected target of a fact is the canonical fact with the same key in
# the latest parsed version of the most recently visible earlier filing, when
# its value differs: exactly what ingest links. A link already pointing at
# that filing through an older parse of it is the same edge and is kept.
_REPAIR_SQL = """
WITH filing AS (
    SELECT d.id, d.accession,
           GREATEST(COALESCE(d.public_at, d.published_at), d.published_at) AS visible_at,
           (SELECT dv.id FROM document_versions dv
            WHERE dv.document_id = d.id AND dv.status = 'parsed'
            ORDER BY dv.created_at DESC, dv.id DESC
            LIMIT 1) AS latest_version_id
    FROM documents d
    WHERE d.entity_id = %(entity_id)s AND d.form IS DISTINCT FROM %(company_facts)s
),
expected AS (
    SELECT f.id, f.restates AS held_id, target.id AS target_id,
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
          AND pd.visible_at < fd.visible_at
        ORDER BY pd.visible_at DESC, pd.accession DESC, p.id
        LIMIT 1
    ) target ON target.value <> f.value
    LEFT JOIN financial_facts held ON held.id = f.restates
    LEFT JOIN document_versions held_version ON held_version.id = held.document_version_id
    WHERE f.entity_id = %(entity_id)s
)
UPDATE financial_facts f
SET restates = e.target_id
FROM expected e
WHERE f.id = e.id
  AND f.restates IS DISTINCT FROM e.target_id
  AND e.same_edge IS NOT TRUE
RETURNING f.document_version_id, e.held_id IS NULL, e.target_id IS NULL
"""


def repair_restatement_links(conn: psycopg.Connection[Any], *, entity_id: str) -> RepairReport:
    """Make one issuer's ``restates`` links what in-order ingest would produce.

    One statement; writes only ``financial_facts.restates`` and only on rows
    whose link is wrong, so a second run changes nothing.
    """
    rows = conn.execute(
        _REPAIR_SQL, {"entity_id": entity_id, "company_facts": COMPANY_FACTS_FORM}
    ).fetchall()
    return RepairReport(
        linked=sum(1 for _, was_null, now_null in rows if was_null and not now_null),
        relinked=sum(1 for _, was_null, now_null in rows if not was_null and not now_null),
        cleared=sum(1 for _, was_null, now_null in rows if now_null),
        document_version_ids=tuple(sorted({str(version_id) for version_id, _, _ in rows})),
    )


def _backfill_publication(
    conn: psycopg.Connection[Any], client: SecClient, cik: str, entity_id: str
) -> tuple[int, tuple[str, ...]]:
    """Set the publication columns still NULL; return (updated, conflicts)."""
    refs = {ref.accession: ref for ref in discover_filings(client, cik)}
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "SELECT id, accession, filed_at, accepted_at, public_at, public_at_basis,"
            " timestamp_precision FROM documents"
            " WHERE entity_id = %s AND form IS DISTINCT FROM %s AND accession = ANY(%s)"
            " ORDER BY accession",
            (entity_id, COMPANY_FACTS_FORM, list(refs)),
        ).fetchall()
    updated = 0
    conflicts: list[str] = []
    for row in rows:
        ref = refs[str(row["accession"])]
        try:
            derived = derive_publication(ref.acceptance_datetime, ref.filed_on)
        except ValueError:
            continue  # an unusable acceptance time resolves nothing
        # Only a row ingested with this exact filing date is the filing the
        # index describes; anything else stays NULL rather than be guessed.
        if derived.accepted_at is None or row["filed_at"] != datetime.combine(
            ref.filed_on, time(0), tzinfo=UTC
        ):
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
        # The predicate repeats both guards so the write itself can never
        # replace a stored publication time or touch a company-facts row.
        updated += conn.execute(
            "UPDATE documents SET accepted_at = %s, public_at = %s, public_at_basis = %s,"
            " timestamp_precision = %s"
            " WHERE id = %s AND accepted_at IS NULL AND form IS DISTINCT FROM %s",
            (
                derived.accepted_at,
                derived.public_at,
                derived.public_at_basis,
                derived.timestamp_precision,
                row["id"],
                COMPANY_FACTS_FORM,
            ),
        ).rowcount
    return updated, tuple(conflicts)


def run_publication_backfill_job(
    conn: psycopg.Connection[Any], client: SecClient, payload: dict[str, Any]
) -> BackfillReport:
    """Handle a ``sec_publication_backfill`` job for one issuer (``cik``).

    The submissions index comes from the injected client: the pinned fixture
    transport in every mock run. All writes commit together or not at all.
    """
    cik = str(payload.get("cik", ""))
    entity_id = entity_id_for_cik(cik)
    with conn.transaction():
        updated, conflicts = _backfill_publication(conn, client, cik, entity_id)
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
        repair=repair,
    )

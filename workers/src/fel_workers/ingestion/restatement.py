"""Shared restatement-link repair for backfill and corpus publication (#393)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from fel_workers.ingestion.pin_guard import lock_corpus_mutations, reject_retained_pin_changes
from fel_workers.ingestion.raw_store import COMPANY_FACTS_FORM


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


# The expected target of a fact is the canonical fact with the same key in
# the latest parsed version of the latest earlier filing, when its value
# differs: exactly what ingest links (``pipeline._prior_canonical_facts``).
# Earlier requires lower known public_at, or equal public_at with both known
# accepted_at instants strictly ordered. Filing dates never override them.
# A link already pointing at the expected filing through an older parse of it
# is the same edge and is kept.
_REPAIR_SQL = """
WITH filing AS (
    SELECT d.id, d.accession, d.public_at, d.accepted_at,
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
          AND pd.id <> fd.id
          AND (pd.public_at < fd.public_at
               OR (pd.public_at = fd.public_at AND pd.accepted_at < fd.accepted_at))
        ORDER BY pd.public_at DESC, pd.accepted_at DESC NULLS LAST, pd.accession DESC, p.id
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

    Writes only wrong ``financial_facts.restates`` links. If any changed fact
    belongs to a retained pin, the whole repair rolls back, including when
    this function is called directly or its error is caught in an outer
    transaction. A settled retained pin remains a no-op.
    """
    with conn.transaction():
        lock_corpus_mutations(conn)
        rows = conn.execute(
            _REPAIR_SQL, {"entity_id": entity_id, "company_facts": COMPANY_FACTS_FORM}
        ).fetchall()
        reject_retained_pin_changes(
            conn, document_version_ids=tuple({str(version_id) for version_id, _, _ in rows})
        )
    return RepairReport(
        linked=sum(1 for _, was_null, now_null in rows if was_null and not now_null),
        relinked=sum(1 for _, was_null, now_null in rows if not was_null and not now_null),
        cleared=sum(1 for _, was_null, now_null in rows if now_null),
        document_version_ids=tuple(sorted({str(version_id) for version_id, _, _ in rows})),
    )

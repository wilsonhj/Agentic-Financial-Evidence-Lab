"""Publication-time backfill and restatement-link repair (#393, MCP-203/204).

One ``sec_publication_backfill`` job per issuer does two things in a single
transaction, using only the columns migration 0013 grants ``fel_worker``:

1. **Backfill.** For each of the issuer's filings listed in the submissions
   index, derive the publication columns with ``derive_publication`` and set
   them where they are still NULL. A row is left NULL when it cannot be
   verified: no acceptance time, an unusable one, or a stored filing date
   that disagrees with the index. A row that already holds values is never
   written: equal values need no write. A stored filing date or publication
   time that differs from the index, or an acceptance time that cannot be
   parsed, is reported as a conflict for an operator, never overwritten. A
   missing acceptance time stays unresolved and is not a conflict.
   Company-facts snapshots are excluded by form in both the read and the write.

2. **Repair.** Recompute every filing fact's ``restates`` from the stored
   rows, with the ordering ingest uses (``pipeline._prior_canonical_facts``),
   and write only the facts whose link is wrong. The result depends on the
   set of filings, not on the order they were ingested in.

Both steps are idempotent and a rerun does only the work still outstanding.
Actual metadata or edge changes to active or retained superseded pins are
rejected atomically (ADR-0034 Amendment 2). Backfill and direct repair share
publication's transaction lock, held through the caller's outer transaction.
The submissions index is fetched before that lock is requested, so a slow
SEC response never blocks publication; only database work runs under it.
Repair must therefore finish before publishing an affected pin. No retirement
state is introduced. Corpus publication runs the same repair before activation.

Discovery currently reads ``filings.recent`` only, not the older
``filings.files`` pages. Stored filings absent from that bounded index stay
unresolved; this job does not claim to backfill the issuer's full history.
Unknown publication times establish no restatement predecessor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from fel_providers.interfaces import SecClient
from fel_workers.ingestion.company_facts import entity_id_for_cik
from fel_workers.ingestion.discovery import FilingRef, discover_filings
from fel_workers.ingestion.pin_guard import lock_corpus_mutations, reject_retained_pin_changes
from fel_workers.ingestion.publication import Publication, derive_publication
from fel_workers.ingestion.raw_store import COMPANY_FACTS_FORM
from fel_workers.ingestion.restatement import RepairReport as RepairReport
from fel_workers.ingestion.restatement import repair_restatement_links as repair_restatement_links

JOB_KIND_SEC_PUBLICATION_BACKFILL = "sec_publication_backfill"


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of one issuer's backfill job."""

    updated: int = 0
    """Documents whose publication columns were set by this run."""
    unresolved: int = 0
    """The issuer's filings that still have no publication time."""
    conflicts: tuple[str, ...] = ()
    """Accessions left untouched: a stored filing date or publication time
    differs from the index, or the acceptance time cannot be parsed. A
    missing acceptance time is unresolved, not a conflict."""
    repair: RepairReport = field(default_factory=RepairReport)


def _backfill_publication(
    conn: psycopg.Connection[Any], refs: dict[str, FilingRef], entity_id: str
) -> tuple[int, tuple[str, ...]]:
    """Set the publication columns still NULL; return (updated, conflicts).

    ``refs`` is the already-fetched index: this runs under the corpus lock,
    which must never be held across a network call.
    """
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
        # Only a row ingested with this exact filing date is the filing the
        # index describes; anything else is reported and stays as it is.
        if row["filed_at"] != datetime.combine(ref.filed_on, time(0), tzinfo=UTC):
            conflicts.append(ref.accession)
            continue
        try:
            derived = derive_publication(ref.acceptance_datetime, ref.filed_on)
        except ValueError:
            # The raw acceptanceDateTime is untrusted and is not recorded.
            conflicts.append(ref.accession)
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
        # The predicate repeats both guards so the write itself can never
        # replace a stored publication time or touch a company-facts row.
        changed = conn.execute(
            "UPDATE documents SET accepted_at = %s, public_at = %s, public_at_basis = %s,"
            " timestamp_precision = %s"
            " WHERE id = %s AND accepted_at IS NULL AND form IS DISTINCT FROM %s RETURNING id",
            (
                derived.accepted_at,
                derived.public_at,
                derived.public_at_basis,
                derived.timestamp_precision,
                row["id"],
                COMPANY_FACTS_FORM,
            ),
        ).fetchall()
        reject_retained_pin_changes(conn, document_ids=tuple(str(item[0]) for item in changed))
        updated += len(changed)
    return updated, tuple(conflicts)


def run_publication_backfill_job(
    conn: psycopg.Connection[Any], client: SecClient, payload: dict[str, Any]
) -> BackfillReport:
    """Handle a ``sec_publication_backfill`` job for one issuer (``cik``).

    The submissions index comes from the injected client: the pinned fixture
    transport in every mock run. It is fetched before the corpus lock is
    requested; the lock then covers only the reads, writes and pin checks.
    That is safe because the writes fill only NULL columns and report any
    disagreement with stored values instead of overwriting them. All writes
    commit together or not at all.
    """
    cik = str(payload.get("cik", ""))
    entity_id = entity_id_for_cik(cik)
    refs = {ref.accession: ref for ref in discover_filings(client, cik)}
    with conn.transaction():
        lock_corpus_mutations(conn)
        updated, conflicts = _backfill_publication(conn, refs, entity_id)
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

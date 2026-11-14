"""Publication-time backfill and restatement-link repair (#393).

Interface only in this commit; the behaviour lands with its tests green.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import psycopg

from fel_providers.interfaces import SecClient

JOB_KIND_SEC_PUBLICATION_BACKFILL = "sec_publication_backfill"


@dataclass(frozen=True)
class RepairReport:
    """What one restatement repair changed. All zero means nothing was written."""

    linked: int = 0
    relinked: int = 0
    cleared: int = 0
    document_version_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackfillReport:
    """Outcome of one issuer's backfill job."""

    updated: int = 0
    unresolved: int = 0
    conflicts: tuple[str, ...] = ()
    repair: RepairReport = field(default_factory=RepairReport)


def repair_restatement_links(conn: psycopg.Connection[Any], *, entity_id: str) -> RepairReport:
    raise NotImplementedError


def run_publication_backfill_job(
    conn: psycopg.Connection[Any], client: SecClient, payload: dict[str, Any]
) -> BackfillReport:
    raise NotImplementedError

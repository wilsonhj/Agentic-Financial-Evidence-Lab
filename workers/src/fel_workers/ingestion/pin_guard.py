"""Serialization and retained corpus-pin protection for ingestion repairs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import psycopg


class PublishedPinMutationError(RuntimeError):
    """A proposed repair would change evidence in an active or superseded pin."""


class CorpusLockTimeoutError(RuntimeError):
    """The corpus mutation lock was not granted within the bound.

    Another publication or repair held it. Nothing was written: the error
    aborts the caller's transaction. It is transient, so the job is retried.
    """


# Upper bound on the wait for the corpus mutation lock, read at call time so a
# deployment or test can lower it. Only DB work runs under the lock (network
# fetches happen before it is taken), so a longer wait means a stuck holder.
CORPUS_LOCK_TIMEOUT_MS = 30_000


# One database-local key shared by every supported publisher and repair.
# A global lock avoids membership phantoms and lock-order deadlocks across
# issuers. Unlike a session lock, it remains held until the OUTERMOST commit
# or rollback, including when callers use nested transaction/savepoint scopes.
_CORPUS_MUTATION_LOCK = 0x46454C50494E21  # "FELPIN!"


def lock_corpus_mutations(conn: psycopg.Connection[Any], *, timeout_ms: int | None = None) -> None:
    """Serialize publish, publication backfill and direct restatement repair.

    Call inside a transaction, before reading or writing corpus state, and
    never across network I/O. The guard queries after waiting must see newly
    committed pins; a preexisting REPEATABLE READ/SERIALIZABLE snapshot cannot
    provide that guarantee. Advisory locking is cooperative: all three
    supported mutation entrypoints participate. This does not grant or enforce
    arbitrary direct SQL access.

    The wait is bounded by ``timeout_ms`` (default ``CORPUS_LOCK_TIMEOUT_MS``)
    through a transaction-local ``lock_timeout`` that applies to the lock
    request only: the caller's setting is restored once the lock is held, so
    the bound never reaches the caller's later statements. Raises
    ``CorpusLockTimeoutError`` when the bound is exceeded.
    """
    bound = CORPUS_LOCK_TIMEOUT_MS if timeout_ms is None else timeout_ms
    if bound <= 0:
        raise ValueError("the corpus lock timeout must be a positive number of milliseconds")
    isolation = conn.execute("SHOW transaction_isolation").fetchone()
    if isolation is None or isolation[0] != "read committed":
        raise ValueError("corpus publication and repair require READ COMMITTED isolation")
    row = conn.execute("SELECT current_setting('lock_timeout')").fetchone()
    previous = "0" if row is None else str(row[0])
    conn.execute("SELECT set_config('lock_timeout', %s, true)", (f"{bound}ms",))
    try:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_CORPUS_MUTATION_LOCK,))
    except psycopg.errors.LockNotAvailable as exc:
        raise CorpusLockTimeoutError(
            f"corpus mutation lock not granted within {bound} ms: another publication"
            " or repair holds it; nothing was written, retry later"
        ) from exc
    conn.execute("SELECT set_config('lock_timeout', %s, true)", (previous,))


def reject_retained_pin_changes(
    conn: psycopg.Connection[Any],
    *,
    document_ids: Sequence[str] = (),
    document_version_ids: Sequence[str] = (),
) -> None:
    """Reject actual changes to metadata or facts exposed by retained pins.

    Publication metadata is shared by every parse of a document, so check all
    versions for those changes. Fact edges are owned by the changed version.
    Call after UPDATE RETURNING, inside the mutation's transaction/savepoint.
    The rollback happens only when this error leaves that transaction block:
    callers must not catch it inside the block, or the writes stay pending.
    Both active and superseded corpora remain replayable under ADR-0034.
    """
    if not document_ids and not document_version_ids:
        return
    held = conn.execute(
        "SELECT cv.id FROM corpus_versions cv"
        " JOIN corpus_version_documents cd ON cd.corpus_version_id = cv.id"
        " JOIN document_versions dv ON dv.id = cd.document_version_id"
        " WHERE cv.status IN ('active', 'superseded')"
        " AND (dv.document_id = ANY(%s::uuid[]) OR dv.id = ANY(%s::uuid[]))"
        " LIMIT 1",
        (list(document_ids), list(document_version_ids)),
    ).fetchone()
    if held is not None:
        raise PublishedPinMutationError(
            f"repair would mutate retained corpus pin {held[0]}; "
            "publication metadata and restatement edges must be repaired before publication"
        )

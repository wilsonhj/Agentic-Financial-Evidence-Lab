"""Strict visibility and the read-only session (#395, MCP-401, MCP-407).

Every evidence read of the public surface goes through the two things defined
here, so no read can be written without them:

* ``VISIBLE_VERSIONS`` is the one FROM clause that yields evidence. A row
  exists only for a parsed version, listed in the pinned corpus version, of a
  filing whose verified ``public_at`` is at or before the cutoff (ADR-0034
  decision 4, Amendment 1). A reference to anything else finds no row, which
  is the same result as a reference to nothing: hidden and missing evidence
  cannot be told apart because they are not treated apart.
* ``public_read_session`` runs the read on ``fel_public_read`` in one
  read-only snapshot with a statement timeout (ADR-0034 decision 2).

The predicate, clause by clause:

* ``public_at IS NOT NULL`` with ``timestamp_precision = 'second'``: a record
  without a verified publication instant is invisible, however old its filing
  date.
* ``GREATEST(public_at, published_at) <= as_of``: ``public_at`` decides. The
  ingestion rule never derives a ``public_at`` before the filing date held in
  ``published_at``, so the two bounds agree for every row it writes; a row
  that breaks the rule is ambiguous and stays hidden until both have passed.
  The retrieval lanes' cutoff is never later than this one, so a search that
  is restricted to visible documents agrees with the reads.
* Company-facts snapshots are excluded by form and, with every other
  non-filing document, by the SEC accession shape (decision 5).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Final

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.limits import invalid_input
from fel_retrieval.index_build import DBConnection

STATEMENT_TIMEOUT_MS: Final = 2000
_QUERY_CANCELED: Final = "57014"

VISIBLE_DOCUMENT: Final = " ".join(
    [
        "d.public_at IS NOT NULL AND d.timestamp_precision = 'second'",
        "AND GREATEST(d.public_at, d.published_at) <= %(as_of)s",
        "AND d.form IS DISTINCT FROM 'COMPANYFACTS'",
        "AND d.accession ~ '^[0-9]{10}-[0-9]{2}-[0-9]{6}$'",
    ]
)
# Aliases: cvd (corpus membership), dv (parsed version), d (visible filing).
VISIBLE_VERSIONS: Final = " ".join(
    [
        "corpus_version_documents cvd",
        "JOIN document_versions dv ON dv.id = cvd.document_version_id",
        "AND dv.status = 'parsed' AND cvd.corpus_version_id = %(corpus)s",
        "JOIN documents d ON d.id = dv.document_id AND",
        VISIBLE_DOCUMENT,
    ]
)


def visibility_params(context: i.EvidenceContext) -> dict[str, Any]:
    """Bind parameters of ``VISIBLE_VERSIONS``. Strict contexts only."""
    if context.timestamp_mode != "strict":
        raise invalid_input("timestamp_mode", "must be strict; approximate mode is not served")
    return {"as_of": context.effective_as_of, "corpus": context.corpus_version_id}


@contextmanager
def public_read_session(
    conn: DBConnection, *, statement_timeout_ms: int = STATEMENT_TIMEOUT_MS
) -> Iterator[DBConnection]:
    """One read-only snapshot on ``fel_public_read`` with a statement timeout.

    The role and timeout are transaction-local, so a pooled connection carries
    neither into its next use. A cancelled statement surfaces as
    ``deadline_exceeded``; other database errors propagate to the adapter.
    """
    try:
        with conn.transaction():
            # Must be the first statement of the transaction.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            conn.execute("SET LOCAL ROLE fel_public_read")
            conn.execute(
                "SELECT set_config('statement_timeout', %s, true)", (str(statement_timeout_ms),)
            )
            yield conn
    except Exception as error:
        if getattr(error, "sqlstate", None) == _QUERY_CANCELED:
            raise i.EvidenceReadError(
                "deadline_exceeded",
                "The request exceeded its time limit.",
                retryable=True,
                recovery="Narrow the request, then retry.",
            ) from error
        raise

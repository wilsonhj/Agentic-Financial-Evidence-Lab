"""Evidence-context resolution (#395, MCP-402; design contract §6.1 and §6.3).

``resolve_context`` turns request-side inputs into the stable context every
result echoes. A supplied pin is validated and never replaced: an unknown,
unpublished or incompatible pin raises ``pin_unavailable`` naming it. Only an
omitted corpus pin resolves to the active corpus, and only search
(``require_index``) resolves an omitted index pin.

"Published" is ``active`` or ``superseded`` for a corpus version and ``ready``
or ``superseded`` for an index version. Superseded versions stay pinnable so
that a context replays across a corpus publish and an index rebuild. The
schema has no retired state yet; when one is added it belongs in the two
status lists below.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.limits import EARLIEST_AS_OF, check_uuid, invalid_input
from fel_retrieval.evidence.visibility import public_read_session
from fel_retrieval.index_build import DBConnection

VERIFIER_VERSIONS: Final = ("deterministic-v1",)
_NEW_YORK: Final = ZoneInfo("America/New_York")
_RETRY_AFTER_SECONDS: Final = 60

_PINNED_CORPUS: Final = (
    "SELECT id FROM corpus_versions WHERE id = %s AND status IN ('active', 'superseded')"
)
_ACTIVE_CORPUS: Final = "SELECT id FROM corpus_versions WHERE is_active"
_PINNED_INDEX: Final = (
    "SELECT id FROM retrieval_index_versions "
    "WHERE id = %s AND corpus_version_id = %s AND status IN ('ready', 'superseded')"
)
# The active index when it belongs to this corpus, else its latest published one.
_CORPUS_INDEX: Final = (
    "SELECT id FROM retrieval_index_versions "
    "WHERE corpus_version_id = %s AND status IN ('ready', 'superseded') "
    "ORDER BY is_active DESC, published_at DESC, id DESC LIMIT 1"
)


def _pin_unavailable(pin: str) -> i.EvidenceReadError:
    return i.EvidenceReadError(
        "pin_unavailable",
        f"The pinned {pin} is unknown, unpublished or incompatible.",
        retryable=False,
        recovery="Omit the pin to start a new context on active versions.",
        field=pin,
    )


def effective_as_of(as_of: datetime | date | None, request_time: datetime) -> datetime:
    """The cutoff instant actually used, in UTC (§6.1).

    A date means 00:00 America/New_York on that date, so filings made public
    that day are excluded. None means the request time. The result must lie
    between 1994-01-01T00:00:00Z and the request time.
    """
    if as_of is None:
        instant = request_time
    elif isinstance(as_of, datetime):
        instant = as_of
    else:
        instant = datetime.combine(as_of, time(0), tzinfo=_NEW_YORK)
    if not EARLIEST_AS_OF <= instant <= request_time:
        raise invalid_input("as_of", "must be between 1994-01-01T00:00:00Z and the request time")
    return instant.astimezone(UTC)


def resolve_context(
    conn: DBConnection,
    request: i.ContextRequest,
    *,
    verifier_versions: tuple[str, ...] = VERIFIER_VERSIONS,
) -> i.EvidenceContext:
    """Resolve the cutoff and pins. Everything checkable without the database is checked first."""
    cutoff = effective_as_of(request.as_of, request.request_time)
    if request.timestamp_mode != "strict":
        raise invalid_input("timestamp_mode", "must be strict; approximate mode is not served")
    for pin in ("corpus_version_id", "index_version_id"):
        if getattr(request, pin) is not None:
            check_uuid(pin, getattr(request, pin))
    verifier = (
        VERIFIER_VERSIONS[0] if request.verifier_version is None else request.verifier_version
    )
    if verifier not in verifier_versions:
        raise _pin_unavailable("verifier_version")

    with public_read_session(conn):
        if request.corpus_version_id is not None:
            corpus = conn.execute(_PINNED_CORPUS, (request.corpus_version_id,)).fetchone()
            if corpus is None:
                raise _pin_unavailable("corpus_version_id")
        else:
            corpus = conn.execute(_ACTIVE_CORPUS).fetchone()
            if corpus is None:
                raise i.EvidenceReadError(
                    "unavailable",
                    "No corpus version is published.",
                    retryable=True,
                    recovery="Wait, then retry.",
                    retry_after_seconds=_RETRY_AFTER_SECONDS,
                )
        index = None
        if request.index_version_id is not None:
            index = conn.execute(_PINNED_INDEX, (request.index_version_id, corpus[0])).fetchone()
        elif request.require_index:
            index = conn.execute(_CORPUS_INDEX, (corpus[0],)).fetchone()
        if index is None and (request.index_version_id is not None or request.require_index):
            raise _pin_unavailable("index_version_id")

    return i.EvidenceContext(
        effective_as_of=cutoff,
        timestamp_mode="strict",
        temporal_guarantee="strict",
        corpus_version_id=str(corpus[0]),
        index_version_id=None if index is None else str(index[0]),
        parser_version=None,
        verifier_version=verifier,
        document_version_id=None,
        filters=request.filters,
    )

"""When a filing became public (ADR-0034 decision 4, Amendment 1; #393).

Acceptance is not publication. EDGAR gives most submissions begun after
17:30 ET the next business day's filing date and does not disseminate them
until that day. :func:`derive_publication` is the only place that interprets
the SEC acceptance timestamp or applies the publication rule; ingest and the
backfill both call it and nothing else computes ``public_at``.

Timezone assumption (ADR-0034 owner input 4, OPEN and unverified): the UTC
offset written in ``acceptanceDateTime`` is taken at face value, so
``2024-03-06T21:14:09.000Z`` is 21:14:09 UTC. A value with no offset is
rejected, never assumed to be UTC or Eastern. If the lead's check against a
filing index page shows the digits are US Eastern wall-clock time under a
nominal ``Z``, :func:`_acceptance_instant` is the one function to change, and
stored rows must be re-derived. No hosted run may rely on this until then.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

__all__ = ["EDGAR_TIMEZONE", "UNKNOWN_PUBLICATION", "Publication", "derive_publication"]

EDGAR_TIMEZONE = ZoneInfo("America/New_York")
# EDGAR opens at 06:00 ET: the earliest an after-hours filing could be public.
_SESSION_OPEN = time(6, 0)


@dataclass(frozen=True)
class Publication:
    """The four ``documents`` publication columns of migration 0012."""

    accepted_at: datetime | None
    public_at: datetime | None
    public_at_basis: str | None
    timestamp_precision: str


# Only the filing date is known: no instant is stored and none is guessed.
UNKNOWN_PUBLICATION = Publication(None, None, None, "date")


def _acceptance_instant(acceptance_datetime: str) -> datetime:
    """Interpret the SEC string as an instant (see the module docstring)."""
    try:
        parsed = datetime.fromisoformat(acceptance_datetime)
    except ValueError:
        parsed = None
    if parsed is None or parsed.utcoffset() is None:
        # The value is untrusted job input: never echo it into the error.
        raise ValueError("acceptanceDateTime is not an ISO-8601 timestamp with a UTC offset")
    return parsed.astimezone(UTC)


def derive_publication(acceptance_datetime: str | None, filing_date: date) -> Publication:
    """Derive ``accepted_at``, ``public_at`` and its basis for one filing.

    If the filing date is later than the US Eastern calendar date of
    acceptance, the filing became public when EDGAR opened on the filing
    date: 06:00 America/New_York, basis ``next_session_open``. Otherwise it
    became public at acceptance, basis ``acceptance``. That second branch
    covers same-day filings, the forms EDGAR disseminates until 22:00 ET
    (they keep their transmission date) and adjusted filing dates.

    The rule uses no form list, clock threshold or holiday calendar: the
    SEC's own filing date already encodes them. A missing acceptance time
    yields :data:`UNKNOWN_PUBLICATION`.
    """
    if isinstance(filing_date, datetime) or not isinstance(filing_date, date):
        raise TypeError("filing_date must be a calendar date, not a datetime")
    if acceptance_datetime is None:
        return UNKNOWN_PUBLICATION
    if not isinstance(acceptance_datetime, str):
        raise TypeError("acceptanceDateTime must be the SEC string or None")
    accepted_at = _acceptance_instant(acceptance_datetime)
    if filing_date > accepted_at.astimezone(EDGAR_TIMEZONE).date():
        opened = datetime.combine(filing_date, _SESSION_OPEN, tzinfo=EDGAR_TIMEZONE)
        return Publication(accepted_at, opened.astimezone(UTC), "next_session_open", "second")
    return Publication(accepted_at, accepted_at, "acceptance", "second")

"""The one publication-time rule (ADR-0034 decision 4, Amendment 1; #393).

Pure tests, no database. Expected instants are written as literal UTC so a
wrong Eastern offset cannot cancel out against the implementation's own
timezone arithmetic.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from fel_workers.ingestion.publication import (
    UNKNOWN_PUBLICATION,
    Publication,
    derive_publication,
)

# case | acceptanceDateTime | filing date | expected. ``acceptance`` means public
# at accepted_at; an instant means basis next_session_open at that UTC instant.
# 2024: EST until 10 March 07:00Z, EDT until 3 November 06:00Z.
CASES = """
same day, 16:14 ET                 | 2024-03-06T21:14:09.000Z  | 2024-03-06 | acceptance
17:29:59 ET keeps its date         | 2024-03-06T22:29:59Z      | 2024-03-06 | acceptance
17:30:01 ET, next-day date         | 2024-03-06T22:30:01Z      | 2024-03-07 | 2024-03-07T11:00Z
20:00 ET is the next UTC day       | 2024-03-07T01:00:00Z      | 2024-03-07 | 2024-03-07T11:00Z
after-hours Form 4 keeps its date  | 2024-03-07T02:45:00Z      | 2024-03-06 | acceptance
time of day alone decides nothing  | 2024-03-06T22:45:00Z      | 2024-03-06 | acceptance
Friday evening to Monday           | 2024-03-01T23:05:00Z      | 2024-03-04 | 2024-03-04T11:00Z
Friday to Tuesday over a holiday   | 2024-05-24T22:05:00Z      | 2024-05-28 | 2024-05-28T10:00Z
weekend date is not rolled         | 2024-03-09T15:00:00Z      | 2024-03-09 | acceptance
filing date before acceptance      | 2024-03-06T15:00:00Z      | 2024-03-04 | acceptance
explicit offset is honoured        | 2024-03-06T16:14:09-05:00 | 2024-03-06 | acceptance
EST day before spring forward      | 2024-03-08T23:00:00Z      | 2024-03-09 | 2024-03-09T11:00Z
06:00 on spring-forward day is EDT | 2024-03-09T23:00:00Z      | 2024-03-10 | 2024-03-10T10:00Z
Friday EST to Monday EDT           | 2024-03-08T23:00:00Z      | 2024-03-11 | 2024-03-11T10:00Z
23:59:59 EST before spring forward | 2024-03-10T04:59:59Z      | 2024-03-10 | 2024-03-10T10:00Z
00:00 EST on spring-forward day    | 2024-03-10T05:00:00Z      | 2024-03-10 | acceptance
23:59:59 EDT after spring forward  | 2024-03-11T03:59:59Z      | 2024-03-11 | 2024-03-11T10:00Z
00:00 EDT after spring forward     | 2024-03-11T04:00:00Z      | 2024-03-11 | acceptance
EDT day before fall back           | 2024-11-01T22:00:00Z      | 2024-11-02 | 2024-11-02T10:00Z
06:00 on fall-back day is EST      | 2024-11-02T22:00:00Z      | 2024-11-03 | 2024-11-03T11:00Z
Friday EDT to Monday EST           | 2024-11-01T22:00:00Z      | 2024-11-04 | 2024-11-04T11:00Z
23:59:59 EDT before fall back      | 2024-11-03T03:59:59Z      | 2024-11-03 | 2024-11-03T11:00Z
00:00 EDT on fall-back day         | 2024-11-03T04:00:00Z      | 2024-11-03 | acceptance
23:59:59 EST after fall back       | 2024-11-04T04:59:59Z      | 2024-11-04 | 2024-11-04T11:00Z
00:00 EST after fall back          | 2024-11-04T05:00:00Z      | 2024-11-04 | acceptance
23:59:59 EDT in July               | 2024-07-02T03:59:59Z      | 2024-07-02 | 2024-07-02T10:00Z
00:00 EDT in July                  | 2024-07-02T04:00:00Z      | 2024-07-02 | acceptance
23:59:59 EST in January            | 2024-01-10T04:59:59Z      | 2024-01-10 | 2024-01-10T11:00Z
00:00 EST in January               | 2024-01-10T05:00:00Z      | 2024-01-10 | acceptance
"""
_ROWS = [[cell.strip() for cell in line.split("|")] for line in CASES.strip().splitlines()]


@pytest.mark.parametrize(
    ("accepted", "filed", "expected"), [r[1:] for r in _ROWS], ids=[r[0] for r in _ROWS]
)
def test_publication_rule(accepted: str, filed: str, expected: str) -> None:
    result = derive_publication(accepted, date.fromisoformat(filed))
    accepted_at = datetime.fromisoformat(accepted)
    if expected == "acceptance":
        assert result == Publication(accepted_at, accepted_at, "acceptance", "second")
    else:
        public_at = datetime.fromisoformat(expected)
        assert result == Publication(accepted_at, public_at, "next_session_open", "second")
    assert result.accepted_at is not None and result.public_at is not None
    assert result.accepted_at.utcoffset() == result.public_at.utcoffset() == timedelta(0)


def test_missing_acceptance_time_is_date_precision_with_no_instants() -> None:
    assert derive_publication(None, date(2024, 3, 6)) is UNKNOWN_PUBLICATION
    assert UNKNOWN_PUBLICATION == Publication(None, None, None, "date")


@pytest.mark.parametrize(
    "accepted",
    ["2024-03-06T16:14:09", "2024-03-06 16:14:09", "2024-03-06", "20240306161409", "", "soon"],
)
def test_timestamps_without_an_offset_are_rejected_not_assumed(accepted: str) -> None:
    with pytest.raises(ValueError, match="acceptanceDateTime") as excinfo:
        derive_publication(accepted, date(2024, 3, 6))
    assert not accepted or accepted not in str(excinfo.value), "untrusted input was echoed"


def test_wrong_argument_types_are_rejected() -> None:
    aware = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
    with pytest.raises(TypeError, match="filing_date"):
        derive_publication("2024-03-06T21:14:09Z", aware)
    with pytest.raises(TypeError, match="acceptanceDateTime"):
        derive_publication(aware, date(2024, 3, 6))  # type: ignore[arg-type]


def test_rule_invariants_hold_for_every_hour_of_a_year() -> None:
    """Never public before acceptance, never before the filing date began in
    New York, and the basis says exactly which branch produced the instant."""
    eastern = ZoneInfo("America/New_York")
    instant = datetime(2024, 1, 1, 0, 30, tzinfo=UTC)
    while instant.year == 2024:
        local_date = instant.astimezone(eastern).date()
        for offset in range(-3, 5):
            filed = local_date + timedelta(days=offset)
            result = derive_publication(instant.isoformat(), filed)
            assert result.accepted_at == instant and result.public_at is not None
            assert result.public_at >= instant
            public_local = result.public_at.astimezone(eastern)
            assert public_local.date() >= filed
            if offset > 0:
                assert result.public_at_basis == "next_session_open"
                assert (public_local.date(), public_local.hour, public_local.minute) == (
                    filed,
                    6,
                    0,
                )
                assert public_local.second == 0 and result.public_at > instant
            else:
                assert (result.public_at_basis, result.public_at) == ("acceptance", instant)
        instant += timedelta(hours=1)

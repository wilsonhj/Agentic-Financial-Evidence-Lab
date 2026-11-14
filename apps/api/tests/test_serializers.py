"""DocumentMeta serialization of the 0012 acceptance and publication columns.

``accepted_at``, ``public_at``, ``public_at_basis`` and ``timestamp_precision``
are optional in OpenAPI 0.10.0 (ADR-0034, Amendment 1). ``document_body``
passes them through when the row carries them, and leaves the body unchanged
for rows read with a pre-0012 explicit column list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from app.serializers import document_body


def _row(**extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.UUID("00000000-0000-4000-8000-000000000001"),
        "entity_id": uuid.UUID("00000000-0000-4000-8000-000000000002"),
        "accession": "0001108524-24-000012",
        "source_url": "https://www.sec.gov/Archives/edgar/data/1108524/x.htm",
        "content_hash": "sha256:" + "0" * 64,
        "published_at": datetime(2024, 3, 6, tzinfo=UTC),
        "ingested_at": datetime(2024, 3, 7, tzinfo=UTC),
        "form": "10-K",
        "filed_at": datetime(2024, 3, 6, tzinfo=UTC),
        "valid_from": None,
        "valid_to": None,
        "period_start": None,
        "period_end": date(2024, 1, 31),
    }
    row.update(extra)
    return row


def test_same_day_row_emits_acceptance_and_publication_instants() -> None:
    accepted = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
    body = document_body(
        _row(
            accepted_at=accepted,
            public_at=accepted,
            public_at_basis="acceptance",
            timestamp_precision="second",
        )
    )
    assert body["accepted_at"] == "2024-03-06T21:14:09+00:00"
    assert body["public_at"] == "2024-03-06T21:14:09+00:00"
    assert body["public_at_basis"] == "acceptance"
    assert body["timestamp_precision"] == "second"
    assert body["published_at"] == "2024-03-06T00:00:00+00:00"


def test_after_hours_row_emits_next_session_open() -> None:
    body = document_body(
        _row(
            accepted_at=datetime(2024, 3, 5, 23, 0, tzinfo=UTC),
            public_at=datetime(2024, 3, 6, 11, 0, tzinfo=UTC),
            public_at_basis="next_session_open",
            timestamp_precision="second",
        )
    )
    assert body["accepted_at"] == "2024-03-05T23:00:00+00:00"
    assert body["public_at"] == "2024-03-06T11:00:00+00:00"
    assert body["public_at_basis"] == "next_session_open"


def test_date_precision_row_omits_instants() -> None:
    body = document_body(
        _row(accepted_at=None, public_at=None, public_at_basis=None, timestamp_precision="date")
    )
    for key in ("accepted_at", "public_at", "public_at_basis"):
        assert key not in body
    assert body["timestamp_precision"] == "date"


def test_pre_0012_column_list_serializes_unchanged() -> None:
    body = document_body(_row())
    for key in ("accepted_at", "public_at", "public_at_basis", "timestamp_precision"):
        assert key not in body
    assert body == document_body(
        _row(accepted_at=None, public_at=None, public_at_basis=None, timestamp_precision=None)
    )

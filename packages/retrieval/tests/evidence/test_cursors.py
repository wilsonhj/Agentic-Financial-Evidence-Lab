"""Cursors (design contract §6.3, MCP-402): signed, context-bound, at most 15 minutes."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.cursors import MAX_LIFETIME, CursorCodec
from fel_retrieval.evidence.limits import MAX_CURSOR_CHARS

KEY = b"k" * 32
ISSUED = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
MICRO = timedelta(microseconds=1)
CORPUS = "a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8"
SCOPE = {"tool": "list_filings", "company": "CRM", "forms": ["10-K", "8-K"]}
POSITION = ["2024-03-06T21:14:09.000001+00:00", "5c2d4b3f-7a6e-4f9b-8c8d-2e3f40516273"]


class Clock:
    def __init__(self) -> None:
        self.now = ISSUED

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture()
def context(evidence_helpers: Any) -> i.EvidenceContext:
    made: i.EvidenceContext = evidence_helpers.make_context(
        datetime(2024, 3, 7, 14, 30, tzinfo=UTC), CORPUS
    )
    return made


def _error(code: str, field: str | None) -> Any:
    return pytest.raises(i.EvidenceReadError, check=lambda e: (e.code, e.field) == (code, field))


def test_a_cursor_round_trips_until_just_before_its_lifetime(context: i.EvidenceContext) -> None:
    clock = Clock()
    codec = CursorCodec(KEY, clock)
    token = codec.encode(context, SCOPE, POSITION)
    assert len(token) <= MAX_CURSOR_CHARS
    assert codec.decode(token, context, SCOPE) == POSITION
    clock.now = ISSUED + MAX_LIFETIME - MICRO
    assert codec.decode(token, context, SCOPE) == POSITION
    clock.now = ISSUED + MAX_LIFETIME
    with pytest.raises(i.EvidenceReadError) as raised:
        codec.decode(token, context, SCOPE)
    assert (raised.value.code, raised.value.retryable, raised.value.field) == (
        "cursor_expired",
        False,
        None,
    )


def test_token_bytes_change_with_issue_time_but_not_what_they_mean(
    context: i.EvidenceContext,
) -> None:
    clock = Clock()
    codec = CursorCodec(KEY, clock)
    first = codec.encode(context, SCOPE, POSITION)
    clock.now = ISSUED + timedelta(seconds=1)
    second = codec.encode(context, SCOPE, POSITION)
    assert first != second
    assert codec.decode(first, context, SCOPE) == codec.decode(second, context, SCOPE) == POSITION


CHANGED_CONTEXTS: dict[str, dict[str, Any]] = {
    "cutoff": {"effective_as_of": datetime(2024, 3, 7, 14, 30, 0, 1, tzinfo=UTC)},
    "corpus": {"corpus_version_id": "b18dab9f-3a2e-4f5b-8c4d-8495a6b7c8d9"},
    "index": {"index_version_id": "b18dab9f-3a2e-4f5b-8c4d-8495a6b7c8d9"},
    "verifier": {"verifier_version": "deterministic-v2"},
    "filters": {"filters": i.ContextFilters(company="CRM")},
}
CHANGED_SCOPES = [
    {**SCOPE, "tool": "get_financial_facts"},
    {**SCOPE, "company": "crm"},
    {**SCOPE, "forms": ["10-K"]},
    {**SCOPE, "forms": None},
]


@pytest.mark.parametrize("change", sorted(CHANGED_CONTEXTS))
def test_a_cursor_is_bound_to_every_field_of_its_context(
    context: i.EvidenceContext, change: str
) -> None:
    codec = CursorCodec(KEY, Clock())
    token = codec.encode(context, SCOPE, POSITION)
    with _error("invalid_input", "cursor"):
        codec.decode(token, dataclasses.replace(context, **CHANGED_CONTEXTS[change]), SCOPE)


@pytest.mark.parametrize("scope", CHANGED_SCOPES)
def test_a_cursor_is_bound_to_its_tool_and_filters(
    context: i.EvidenceContext, scope: dict[str, Any]
) -> None:
    clock = Clock()
    codec = CursorCodec(KEY, clock)
    token = codec.encode(context, SCOPE, POSITION)
    clock.now = ISSUED + MAX_LIFETIME  # a mismatch is reported as such even after expiry
    with _error("invalid_input", "cursor"):
        codec.decode(token, context, scope)


def test_the_same_instant_in_another_offset_is_the_same_context(
    context: i.EvidenceContext,
) -> None:
    codec = CursorCodec(KEY, Clock())
    token = codec.encode(context, SCOPE, POSITION)
    eastern = context.effective_as_of.astimezone(timezone(timedelta(hours=-5)))
    assert codec.decode(token, dataclasses.replace(context, effective_as_of=eastern), SCOPE)


def test_forged_and_malformed_tokens_are_invalid_input(context: i.EvidenceContext) -> None:
    codec = CursorCodec(KEY, Clock())
    token = codec.encode(context, SCOPE, POSITION)
    body, mac = token.split(".")
    swapped = "A" if body[5] != "A" else "B"
    forged = [
        body[:5] + swapped + body[6:] + "." + mac,  # payload changed, signature kept
        body + "." + mac[:-2] + ("AA" if mac[-2:] != "AA" else "BB"),
        CursorCodec(b"another key of thirty-two bytes!", Clock()).encode(context, SCOPE, POSITION),
        body,
        body + "." + mac + "." + mac,
        "not base64 é." + mac,
        ".",
    ]
    for candidate in forged:
        with _error("invalid_input", "cursor"):
            codec.decode(candidate, context, SCOPE)


def test_the_codec_refuses_unsafe_configuration(context: i.EvidenceContext) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        CursorCodec(b"short", Clock())
    with pytest.raises(ValueError, match="15 minutes"):
        CursorCodec(KEY, Clock(), lifetime=MAX_LIFETIME + MICRO)
    with pytest.raises(ValueError, match="15 minutes"):
        CursorCodec(KEY, Clock(), lifetime=timedelta(0))
    assert MAX_LIFETIME == timedelta(minutes=15)
    naive = CursorCodec(KEY, lambda: datetime(2026, 11, 14))
    with pytest.raises(ValueError, match="timezone-aware"):
        naive.encode(context, SCOPE, POSITION)

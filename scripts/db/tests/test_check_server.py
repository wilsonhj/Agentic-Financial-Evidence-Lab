"""Tests for the pre-migration server check.

The version logic is pure. The end-to-end case runs against the CI database
(PostgreSQL 18 with pgvector 0.8.6) and is gated on ``TEST_DATABASE_URL`` like
the other DB-backed suites.
"""

from __future__ import annotations

import os

import psycopg
import pytest

import check_server
from check_server import ServerFacts

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL not configured"
)


def facts(version_num: int = 180001, vector: str | None = "0.8.6") -> ServerFacts:
    return ServerFacts(
        version_num=version_num,
        version=f"{version_num // 10000}.{version_num % 100}",
        role="neondb_owner",
        vector_version=vector,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.8.6", (0, 8, 6)),
        ("0.8.2", (0, 8, 2)),
        ("0.10.0", (0, 10, 0)),
        ("0.8.2-dev", (0, 8, 2)),
        ("1", (1,)),
        ("", ()),
    ],
)
def test_parse_version(text: str, expected: tuple[int, ...]) -> None:
    assert check_server.parse_version(text) == expected


def test_postgres_18_with_pgvector_0_8_6_passes() -> None:
    assert check_server.problems(facts()) == []


def test_the_minimum_pgvector_passes() -> None:
    assert check_server.problems(facts(vector="0.8.2")) == []


def test_postgres_17_is_refused() -> None:
    found = check_server.problems(facts(version_num=170006))
    assert len(found) == 1
    assert "PostgreSQL 18 or later is required" in found[0]


def test_pgvector_0_8_0_is_refused() -> None:
    found = check_server.problems(facts(vector="0.8.0"))
    assert len(found) == 1
    assert "pgvector 0.8.2 or later is required; the server offers 0.8.0" in found[0]


def test_an_old_installed_pgvector_is_refused_even_if_the_server_offers_newer() -> None:
    old_install = ServerFacts(
        version_num=180001,
        version="18.1",
        role="neondb_owner",
        vector_version="0.8.0",
        vector_installed=True,
    )
    found = check_server.problems(old_install)
    assert found == ["pgvector 0.8.2 or later is required; the database has 0.8.0"]


class _Cursor:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...]:
        return self._row


class _Conn:
    def __init__(self, row: tuple[object, ...]) -> None:
        self._row = row

    def execute(self, _query: str) -> _Cursor:
        return _Cursor(self._row)


def test_read_facts_prefers_the_installed_pgvector_over_the_default() -> None:
    row = (180001, "18.1", "neondb_owner", "0.8.0", "0.8.6")
    live = check_server.read_facts(_Conn(row))  # type: ignore[arg-type]
    assert live.vector_version == "0.8.0"
    assert live.vector_installed is True


def test_read_facts_uses_the_default_when_pgvector_is_not_installed() -> None:
    row = (180001, "18.1", "neondb_owner", None, "0.8.6")
    live = check_server.read_facts(_Conn(row))  # type: ignore[arg-type]
    assert live.vector_version == "0.8.6"
    assert live.vector_installed is False


def test_a_server_without_pgvector_is_refused() -> None:
    found = check_server.problems(facts(vector=None))
    assert found == ["the server does not offer the pgvector extension (need 0.8.2 or later)"]


def test_both_problems_are_reported_together() -> None:
    assert len(check_server.problems(facts(version_num=170006, vector="0.8.0"))) == 2


def test_main_without_a_database_url_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("FEL_DATABASE_URL", "DATABASE_URL", "TEST_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert check_server.main([]) == check_server.EXIT_USAGE
    assert "no database URL" in capsys.readouterr().err


@requires_db
def test_main_reads_the_live_server_and_does_not_print_the_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        live = check_server.read_facts(conn)
    expected = check_server.EXIT_TOO_OLD if check_server.problems(live) else check_server.EXIT_OK

    assert check_server.main(["--database-url", TEST_DATABASE_URL]) == expected
    captured = capsys.readouterr()
    assert f"server: PostgreSQL {live.version}" in captured.out
    assert f"connected role: {live.role}" in captured.out
    assert TEST_DATABASE_URL not in captured.out + captured.err


@requires_db
def test_the_ci_database_meets_the_hosted_minimums() -> None:
    """CI runs the hosted major version (ADR-0035), so it must pass the check."""
    if not os.environ.get("CI"):
        pytest.skip("local databases may predate PostgreSQL 18")
    assert TEST_DATABASE_URL is not None
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        assert check_server.problems(check_server.read_facts(conn)) == []

#!/usr/bin/env python3
"""Refuse to migrate a database server that cannot hold the schema.

``db/migrations/0003_retrieval_core.sql`` needs pgvector 0.8.2 or later, and
the hosted database is PostgreSQL 18 (ADR-0035): Neon ships pgvector 0.8.6 on
18 but only 0.8.0 on 14 to 17. Migrations 0001 and 0002 would apply on an
older server before 0003 failed, leaving a half-migrated database, so the
hosted migration workflow runs this check first and stops before
``migrate.py`` touches anything.

The check only reads catalog views. It prints the server version, the
pgvector version (installed, or else the one the server would install) and the
connected role, never the URL.

Exit codes
----------
0   the server meets both minimums
1   usage error (no database URL)
5   could not connect to the database
6   the server or its pgvector is older than required
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

import migrate

EXIT_OK = migrate.EXIT_OK
EXIT_USAGE = migrate.EXIT_USAGE
EXIT_NO_CONNECTION = migrate.EXIT_NO_CONNECTION
EXIT_TOO_OLD = 6

#: ADR-0035: the hosted database and CI both run PostgreSQL 18.
MIN_SERVER_MAJOR = 18
#: ``0003_retrieval_core.sql`` refuses anything older (CVE-2026-3172 fix).
MIN_VECTOR = (0, 8, 2)

SERVER_QUERY = """
SELECT current_setting('server_version_num')::int,
       current_setting('server_version'),
       current_user,
       (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
       (SELECT default_version FROM pg_available_extensions WHERE name = 'vector')
"""


@dataclass(frozen=True)
class ServerFacts:
    version_num: int
    version: str
    role: str
    #: The installed pgvector if the database already has the extension, else
    #: the version ``CREATE EXTENSION`` would install. ``0003`` runs
    #: ``CREATE EXTENSION IF NOT EXISTS`` and then checks the installed
    #: version, so an old installed copy is what matters, not the default.
    vector_version: str | None
    vector_installed: bool = False


def parse_version(text: str) -> tuple[int, ...]:
    """``"0.8.6"`` -> ``(0, 8, 6)``; non-numeric suffixes end the tuple."""
    parts: list[int] = []
    for piece in text.split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def problems(
    facts: ServerFacts,
    min_major: int = MIN_SERVER_MAJOR,
    min_vector: tuple[int, ...] = MIN_VECTOR,
) -> list[str]:
    """Every reason this server cannot take the migrations; empty if none."""
    found: list[str] = []
    major = facts.version_num // 10000
    if major < min_major:
        found.append(f"PostgreSQL {min_major} or later is required; the server is {facts.version}")
    wanted = ".".join(str(part) for part in min_vector)
    if facts.vector_version is None:
        found.append(f"the server does not offer the pgvector extension (need {wanted} or later)")
    elif parse_version(facts.vector_version) < min_vector:
        where = "the database has" if facts.vector_installed else "the server offers"
        found.append(f"pgvector {wanted} or later is required; {where} {facts.vector_version}")
    return found


def read_facts(conn: psycopg.Connection[tuple[object, ...]]) -> ServerFacts:
    row = conn.execute(SERVER_QUERY).fetchone()
    if row is None:  # pragma: no cover - a SELECT without FROM always returns a row
        raise RuntimeError("the server returned no row for the version query")
    version_num, version, role, installed, offered = row
    vector_version = installed if installed is not None else offered
    return ServerFacts(
        version_num=int(str(version_num)),
        version=str(version),
        role=str(role),
        vector_version=None if vector_version is None else str(vector_version),
        vector_installed=installed is not None,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="check_server.py",
        description="Check that a database server can take db/migrations.",
    )
    parser.add_argument(
        "--database-url",
        help="Target database. Defaults to the same variables migrate.py reads.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = migrate.resolve_database_url(args.database_url)
    if not database_url:
        print(
            "error: no database URL; pass --database-url or set FEL_DATABASE_URL", file=sys.stderr
        )
        return EXIT_USAGE

    try:
        conn: psycopg.Connection[tuple[object, ...]] = psycopg.connect(
            database_url, autocommit=True, connect_timeout=30
        )
    except psycopg.OperationalError as exc:
        print(f"error: could not connect to the database: {exc}", file=sys.stderr)
        return EXIT_NO_CONNECTION

    with conn:
        facts = read_facts(conn)

    print(f"server: PostgreSQL {facts.version}")
    label = "pgvector installed" if facts.vector_installed else "pgvector offered"
    print(f"{label}: {facts.vector_version or 'none'}")
    print(f"connected role: {facts.role}")

    found = problems(facts)
    for problem in found:
        print(f"error: {problem}", file=sys.stderr)
    return EXIT_TOO_OLD if found else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

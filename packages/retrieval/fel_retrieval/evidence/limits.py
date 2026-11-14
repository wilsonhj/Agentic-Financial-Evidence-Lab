"""Request limits of the design contract §7.4 (#395, MCP-407).

Pure checks that run before any database work. Each bound equals the frozen
input schema in ``packages/contracts/schemas/mcp-*-input.schema.json``;
``tests/evidence/test_limits.py`` pins them to those files. A violation raises
``invalid_input`` naming the field. Identifiers are checked for shape as well,
so a malformed reference is rejected here and never becomes a database error.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from fel_retrieval.evidence import interfaces as i

MAX_QUERY_CHARS: Final = 500
MAX_NAME_CHARS: Final = 200  # company, companies[], concept
MAX_FORM_CHARS: Final = 20
MAX_PERIOD_CHARS: Final = 32
MAX_HEADING_CHARS: Final = 500
MAX_CURSOR_CHARS: Final = 2048
MAX_COMPANIES: Final = 10
MAX_FORMS: Final = 10
MAX_PERIODS: Final = 12
MAX_SECTION_PATH: Final = 10
MAX_TOP_K: Final = 20
MAX_LIMIT: Final = 50
MAX_OFFSET: Final = 2**31 - 1  # source_spans offsets are PostgreSQL integers
EARLIEST_AS_OF: Final = datetime(1994, 1, 1, tzinfo=UTC)
FORM_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ./-]*$")
ACCESSION_PATTERN: Final = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
_UUID: Final = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


def invalid_input(field: str, constraint: str) -> i.EvidenceReadError:
    return i.EvidenceReadError(
        "invalid_input",
        f"{field} {constraint}.",
        retryable=False,
        recovery="Correct the named field and send the request again.",
        field=field,
    )


def check_uuid(field: str, value: object) -> None:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise invalid_input(field, "must be a UUID")


def _text(field: str, value: object, maximum: int, pattern: re.Pattern[str] | None = None) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\x00" in value:
        raise invalid_input(field, f"must be 1 to {maximum} characters")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise invalid_input(field, "has an unsupported format")


def _items(
    field: str,
    values: Sequence[str] | None,
    maximum: int,
    item_chars: int,
    pattern: re.Pattern[str] | None = None,
    unique: bool = True,
) -> None:
    if values is None:
        return
    if not 1 <= len(values) <= maximum or (unique and len(set(values)) != len(values)):
        raise invalid_input(field, f"must hold 1 to {maximum} distinct items")
    for value in values:
        _text(field, value, item_chars, pattern)


def _count(field: str, value: object, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise invalid_input(field, f"must be an integer from 1 to {maximum}")


def _optional_text(field: str, value: str | None, maximum: int) -> None:
    if value is not None:
        _text(field, value, maximum)


def check_request(request: object) -> None:
    """Raise ``invalid_input`` unless ``request`` is within every §7.4 bound."""
    if isinstance(request, i.ResolveCompanyRequest):
        _text("query", request.query, MAX_QUERY_CHARS)
    elif isinstance(request, i.ListFilingsRequest):
        _text("company", request.company, MAX_NAME_CHARS)
        _count("limit", request.limit, MAX_LIMIT)
        _items("forms", request.forms, MAX_FORMS, MAX_FORM_CHARS, FORM_PATTERN)
        _optional_text("cursor", request.cursor, MAX_CURSOR_CHARS)
    elif isinstance(request, i.SearchRequest):
        _text("query", request.query, MAX_QUERY_CHARS)
        _count("top_k", request.top_k, MAX_TOP_K)
        _items("companies", request.companies, MAX_COMPANIES, MAX_NAME_CHARS)
        _items("forms", request.forms, MAX_FORMS, MAX_FORM_CHARS, FORM_PATTERN)
        _items("periods", request.periods, MAX_PERIODS, MAX_PERIOD_CHARS)
    elif isinstance(request, i.ReadFilingRequest):
        if request.document_id is not None:
            check_uuid("document_id", request.document_id)
        else:
            _text("accession", request.accession, len("0000000000-00-000000"), ACCESSION_PATTERN)
        if isinstance(request.section, str):
            check_uuid("section", request.section)
        else:
            _items("section", request.section, MAX_SECTION_PATH, MAX_HEADING_CHARS, unique=False)
        _optional_text("cursor", request.cursor, MAX_CURSOR_CHARS)
    elif isinstance(request, i.FactsRequest):
        _text("company", request.company, MAX_NAME_CHARS)
        _count("limit", request.limit, MAX_LIMIT)
        _optional_text("concept", request.concept, MAX_NAME_CHARS)
        _optional_text("period", request.period, MAX_PERIOD_CHARS)
        _optional_text("cursor", request.cursor, MAX_CURSOR_CHARS)
    elif isinstance(request, i.SpanIdRef):
        check_uuid("span_id", request.span_id)
    elif isinstance(request, i.SpanRangeRef):
        check_uuid("document_version_id", request.document_version_id)
        if request.end_char > MAX_OFFSET:
            raise invalid_input("end_char", f"must not exceed {MAX_OFFSET}")
    else:
        raise TypeError(f"no request limits are defined for {type(request).__name__}")

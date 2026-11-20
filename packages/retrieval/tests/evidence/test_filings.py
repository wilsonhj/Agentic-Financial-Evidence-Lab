"""Company resolver and filing listing (MCP-403), with a fake at the connection
boundary. ``test_filings_db.py`` proves the SQL on PostgreSQL.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from fel_retrieval import content_sha256
from fel_retrieval.evidence import interfaces as i
from fel_retrieval.evidence.cursors import MAX_LIFETIME, CursorCodec
from fel_retrieval.evidence.filings import list_filings, match_companies, resolve_company

AS_OF = datetime(2024, 3, 7, 14, 30, tzinfo=UTC)
EARLY = datetime(2023, 3, 8, 21, 5, 12, tzinfo=UTC)
LATE = datetime(2024, 3, 6, 21, 14, 9, tzinfo=UTC)
CORPUS = "a07c9a8e-2f1d-4e4a-9b3c-738495a6b7c8"
CRM = i.Company("4b1c3a2e-6f5d-4e8a-9b7c-1d2e3f405162", "0001108524", "CRM", "Salesforce, Inc.")
NOW = i.Company("5c2d4b3f-7a6e-4f9b-8c8d-2e3f40516273", "0001373715", "NOW", "ServiceNow, Inc.")
TWIN = i.Company("6d3e5c4a-8b7f-4a0c-9d9e-3f4051627384", "0000000042", None, "Salesforce, Inc.")
COHORT = {company.entity_id: company for company in (CRM, NOW, TWIN)}
DOCS = [f"00000000-0000-4000-8000-00000000000{n}" for n in range(4)]


def _ref(company: i.Company, serial: int, public_at: datetime, form: str = "10-K") -> Any:
    accession = f"{company.cik}-24-{serial:06d}"
    return (
        company.entity_id,
        accession,
        form,
        public_at.date(),
        public_at,
        public_at,
        "acceptance",
    )


def _page_row(serial: int, public_at: datetime, versions: int = 1) -> tuple[Any, ...]:
    return (
        *_ref(CRM, serial, public_at),
        date(2024, 1, 31),
        DOCS[serial],
        f"11111111-0000-4000-8000-00000000000{serial}",
        "https://www.sec.gov/Archives/edgar/data/1108524/crm.htm",
        content_sha256("raw"),
        versions,
    )


def _stats(*companies: i.Company) -> list[tuple[Any, ...]]:
    return [(c.entity_id, form, 1, EARLY, LATE) for c in companies for form in ("10-K", "8-K")]


class Clock:
    now = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture()
def world(fake_conn: Any, evidence_helpers: Any) -> Any:
    class World:
        clock = Clock()
        cursors = CursorCodec(b"k" * 32, clock)
        context = evidence_helpers.make_context(AS_OF, CORPUS)
        conn: Any = None

        def listing(self, answers: dict[str, Any], **request: Any) -> i.ListFilingsResult:
            self.conn = fake_conn(answers)
            asked = i.ListFilingsRequest(**{"company": "CRM", "limit": 2, **request})
            return list_filings(
                self.conn, asked, self.context, companies=COHORT, cursors=self.cursors
            )

        def resolve(self, answers: dict[str, Any], query: str) -> i.ResolveCompanyResult:
            self.conn = fake_conn(answers)
            asked = i.ResolveCompanyRequest(query=query)
            return resolve_company(self.conn, asked, self.context, companies=COHORT)

    return World()


@pytest.mark.parametrize(
    ("text", "partial", "expected"),
    [
        ("crm", False, [CRM]),
        (" 1108524 ", False, [CRM]),
        ("0001108524", False, [CRM]),
        (CRM.entity_id.upper(), False, [CRM]),
        ("servicenow, inc.", False, [NOW]),
        ("salesforce, inc.", False, [TWIN, CRM]),  # two issuers share the name: ordered by CIK
        ("service", False, []),
        ("service", True, [NOW]),
        ("inc", True, [TWIN, CRM, NOW]),
        ("now", True, [NOW]),  # the ticker, exactly; not also a fragment hit
        ("42", True, [TWIN]),
        ("   ", True, []),
        ("unknown", True, []),
    ],
)
def test_match_companies(text: str, partial: bool, expected: list[i.Company]) -> None:
    assert match_companies(COHORT, text, partial=partial) == expected


def test_resolve_company_reports_coverage_of_visible_filings_only(world: Any) -> None:
    answers = {
        "GROUP BY": [
            (CRM.entity_id, "8-K", 3, EARLY, EARLY),
            (CRM.entity_id, "10-K", 2, LATE, LATE),
        ],
        "d.public_at ASC": [_ref(CRM, 1, EARLY, "8-K")],
        "d.public_at DESC": [_ref(CRM, 2, LATE)],
    }
    result = world.resolve(answers, "inc")  # NOW and TWIN match too, with nothing visible
    assert result.evidence_context is world.context
    assert result.matches == (
        i.CompanyMatch(
            company=CRM,
            coverage=i.CompanyCoverage(
                first_visible_filing=i.FilingRef(
                    "0001108524-24-000001", "8-K", EARLY.date(), EARLY, EARLY, "acceptance"
                ),
                last_visible_filing=i.FilingRef(
                    "0001108524-24-000002", "10-K", LATE.date(), LATE, LATE, "acceptance"
                ),
                visible_forms=("10-K", "8-K"),
                visible_filing_count=5,
            ),
        ),
    )
    assert result.coverage_note == i.CoverageNote(
        text=(
            "Searched 10-K, 8-K filings of Salesforce, Inc. (CIK 0001108524) public from "
            "2023-03-08T21:05:12Z to 2024-03-06T21:14:09Z, visible at 2024-03-07T14:30:00Z."
        ),
        issuers=("0001108524",),
        forms=("10-K", "8-K"),
        date_range=i.DateRange(from_=EARLY, to=LATE),
    )
    stats_sql, stats_params = next(s for s in world.conn.statements if "GROUP BY" in s[0])
    assert stats_params["entities"] == [TWIN.entity_id, CRM.entity_id, NOW.entity_id]
    assert (stats_params["as_of"], stats_params["corpus"]) == (AS_OF, CORPUS)
    assert world.conn.sql.index("SET LOCAL ROLE fel_public_read") < world.conn.sql.index(stats_sql)


def test_a_company_with_nothing_visible_is_resolved_like_an_unknown_one(world: Any) -> None:
    hidden = world.resolve({}, "CRM")
    hidden_sql = world.conn.sql
    unknown = world.resolve({}, "no such company")
    assert hidden == unknown
    assert hidden_sql == world.conn.sql  # one code path: the same statements either way
    assert hidden.matches == ()
    assert hidden.coverage_note == i.CoverageNote(
        text="No matching evidence in the visible indexed corpus at 2024-03-07T14:30:00Z.",
        issuers=(),
        forms=(),
        date_range=i.DateRange(from_=None, to=None),
    )


def test_list_filings_pages_newest_first_with_a_bound_cursor(world: Any) -> None:
    rows = [_page_row(3, LATE), _page_row(2, LATE - timedelta(days=1)), _page_row(1, EARLY)]
    first = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}, forms=("8-K", "10-K"))
    assert [filing.document_id for filing in first.filings] == [DOCS[3], DOCS[2]]
    assert first.filings[0] == i.FilingMeta(
        entity_id=CRM.entity_id,
        accession="0001108524-24-000003",
        form="10-K",
        filing_date=LATE.date(),
        accepted_at=LATE,
        public_at=LATE,
        public_at_basis="acceptance",
        timestamp_precision="second",
        period_end=date(2024, 1, 31),
        document_id=DOCS[3],
        document_version_id="11111111-0000-4000-8000-000000000003",
        source_url="https://www.sec.gov/Archives/edgar/data/1108524/crm.htm",
        content_hash=content_sha256("raw"),
        amends=None,
    )
    assert first.coverage_note.forms == ("10-K", "8-K")
    assert first.coverage_note.date_range == i.DateRange(from_=EARLY, to=LATE)
    page = next(params for sql, params in world.conn.statements if "LIMIT" in sql)
    assert (page["take"], page["forms"], page["after_id"]) == (3, ["10-K", "8-K"], None)

    assert first.next_cursor is not None
    last = world.listing(
        {"GROUP BY": _stats(CRM), "LIMIT": rows[2:]},
        forms=("10-K", "8-K"),
        cursor=first.next_cursor,
    )
    page = next(params for sql, params in world.conn.statements if "LIMIT" in sql)
    assert (page["after_public"], page["after_id"]) == (
        (LATE - timedelta(days=1)).isoformat(),
        DOCS[2],
    )
    assert ([filing.document_id for filing in last.filings], last.next_cursor) == ([DOCS[1]], None)
    exact = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows[:2]})
    assert (len(exact.filings), exact.next_cursor) == (2, None)  # a full last page ends the listing


def test_a_cursor_is_rejected_before_any_database_work(world: Any) -> None:
    forged = "not-a-signed-cursor"
    # A bad signature is the same refusal for a cohort member with nothing visible
    # and for a name that is not served, and neither consults the database.
    for company in (NOW.cik, NOW.ticker, NOW.entity_id, NOW.name, "no such company"):
        with pytest.raises(
            i.EvidenceReadError,
            check=lambda e: (e.code, e.field) == ("invalid_input", "cursor"),
        ):
            world.listing({}, company=company, cursor=forged)
        assert world.conn.statements == []
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.field == "limit"):
        world.listing({}, limit=51)
    assert world.conn.statements == []


def test_a_signed_cursor_for_a_hidden_company_is_not_found_like_an_unknown_name(
    world: Any,
) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    cursor = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}, forms=("10-K",)).next_cursor

    def outcome(**request: Any) -> tuple[dict[str, Any], list[str]]:
        with pytest.raises(i.EvidenceReadError) as raised:
            world.listing({}, **{"forms": ("10-K",), "cursor": cursor, **request})
        error = vars(raised.value)
        assert error == vars(i.EvidenceReadError.not_found())
        sql = world.conn.sql
        assert any("GROUP BY" in statement for statement in sql)
        assert not any("LIMIT" in statement for statement in sql)
        return error, sql

    unknown = outcome(company="no such company")
    for company in (NOW.cik, NOW.ticker, NOW.entity_id, NOW.name):
        assert outcome(company=company) == unknown
    # The issuer is in the cohort, but nothing is visible, so scope mismatches
    # and expiry stay behind not_found. The form-stats query may run; the page must not.
    assert outcome(company="CRM", forms=("8-K",)) == unknown
    assert outcome(company="CRM", forms=None) == unknown
    original = world.context
    world.context = dataclasses.replace(original, effective_as_of=AS_OF + timedelta(microseconds=1))
    assert outcome(company="CRM") == unknown
    world.context = original
    world.clock.now += MAX_LIFETIME
    assert outcome(company="CRM") == outcome(company="no such company")


def test_an_expired_cursor_is_cursor_expired(world: Any) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    cursor = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}).next_cursor
    world.clock.now += MAX_LIFETIME
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.code == "cursor_expired"):
        world.listing({"GROUP BY": _stats(CRM)}, cursor=cursor)
    assert any("GROUP BY" in statement for statement in world.conn.sql)
    assert not any("LIMIT" in statement for statement in world.conn.sql)


def test_a_visible_company_rejects_a_cursor_for_another_scope_after_the_stats_query(
    world: Any,
) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    cursor = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}, forms=("10-K",)).next_cursor
    visible = {"GROUP BY": _stats(CRM, NOW)}

    def rejected(**request: Any) -> i.EvidenceReadError:
        with pytest.raises(i.EvidenceReadError) as raised:
            world.listing(visible, **{"forms": ("10-K",), "cursor": cursor, **request})
        assert any("GROUP BY" in statement for statement in world.conn.sql)
        assert not any("LIMIT" in statement for statement in world.conn.sql)
        return raised.value

    for request in ({"forms": ("8-K",)}, {"forms": None}, {"company": NOW.cik}):
        error = rejected(**request)
        assert (error.code, error.field) == ("invalid_input", "cursor")
    original = world.context
    world.context = dataclasses.replace(original, effective_as_of=AS_OF + timedelta(microseconds=1))
    error = rejected()
    world.context = original
    assert (error.code, error.field) == ("invalid_input", "cursor")


def test_a_binding_mismatch_is_reported_before_expiry(world: Any) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    cursor = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}, forms=("10-K",)).next_cursor
    world.clock.now += MAX_LIFETIME
    visible = {"GROUP BY": _stats(CRM, NOW)}

    def rejected(**request: Any) -> None:
        with pytest.raises(i.EvidenceReadError) as raised:
            world.listing(visible, **{"forms": ("10-K",), "cursor": cursor, **request})
        assert (raised.value.code, raised.value.field) == ("invalid_input", "cursor")
        assert any("GROUP BY" in statement for statement in world.conn.sql)
        assert not any("LIMIT" in statement for statement in world.conn.sql)

    rejected(forms=("8-K",))
    rejected(forms=None)
    rejected(company=NOW.cik)
    original = world.context
    world.context = dataclasses.replace(original, effective_as_of=AS_OF + timedelta(microseconds=1))
    rejected()
    world.context = original


def test_a_hidden_company_lists_like_an_unknown_one(world: Any) -> None:
    outcomes = []
    for company in ("CRM", "no such company"):
        with pytest.raises(i.EvidenceReadError) as raised:
            world.listing({}, company=company)
        outcomes.append((vars(raised.value), world.conn.sql))
    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0] == vars(i.EvidenceReadError.not_found())
    assert not any("LIMIT" in sql for sql in outcomes[0][1])


def test_ambiguity_is_judged_among_visible_companies_only(world: Any) -> None:
    name = "Salesforce, Inc."  # CRM and TWIN share it
    only_one = world.listing({"GROUP BY": _stats(CRM), "LIMIT": [_page_row(1, LATE)]}, company=name)
    assert only_one.coverage_note.issuers == (CRM.cik,)
    with pytest.raises(i.EvidenceReadError) as raised:
        world.listing({"GROUP BY": _stats(CRM, TWIN)}, company=name)
    assert (raised.value.code, raised.value.field) == ("invalid_input", "company")


def test_a_form_filter_with_no_visible_filing_is_an_empty_page_not_an_error(world: Any) -> None:
    result = world.listing({"GROUP BY": _stats(CRM)}, forms=("S-1",))
    assert (result.filings, result.next_cursor) == ((), None)
    assert result.coverage_note == i.CoverageNote(
        text="No matching evidence in the visible indexed corpus at 2024-03-07T14:30:00Z.",
        issuers=(CRM.cik,),
        forms=("S-1",),
        date_range=i.DateRange(from_=None, to=None),
    )


def test_two_parsed_versions_of_one_document_fail_closed(world: Any) -> None:
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.code == "integrity_error"):
        world.listing({"GROUP BY": _stats(CRM), "LIMIT": [_page_row(1, LATE, versions=2)]})


SCHEMAS = Path(__file__).resolve().parents[3] / "contracts" / "schemas"


def _json(value: Any) -> Any:
    """The interface value as the MCP JSON the schemas describe."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name.rstrip("_"): _json(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_json(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json(item) for key, item in value.items()}
    return value


def _validate(result: Any, schema: str) -> None:
    resources = []
    for path in SCHEMAS.glob("*.schema.json"):
        contents = json.loads(path.read_text())
        resources.append((contents["$id"], Resource.from_contents(contents)))
    document = json.loads((SCHEMAS / f"{schema}.schema.json").read_text())
    payload = _json(result)
    payload["evidence_context"]["filters"] = {
        key: item
        for key, item in payload["evidence_context"]["filters"].items()
        if item is not None
    }
    Draft202012Validator(document, registry=Registry().with_resources(resources)).validate(payload)


@pytest.mark.parametrize(
    ("form_chars", "form_count", "summary"),
    [
        (8, 21, "F00XXXXX, F01XXXXX"),  # names are counted, forms still listed
        (20, 60, "Searched filings of 60 forms of 20 issuers public from"),  # both counted
    ],
)
def test_a_coverage_note_stays_within_the_schema_at_twenty_matches(
    fake_conn: Any, evidence_helpers: Any, form_chars: int, form_count: int, summary: str
) -> None:
    cohort = {}
    for n in range(20):
        name = f"Northern {n:02d} Holdings International Incorporated".ljust(60, "n")
        company = i.Company(f"00000000-0000-4000-8000-{n:012d}", f"{n:010d}", None, name)
        cohort[company.entity_id] = company
    forms = [f"F{n:02d}".ljust(form_chars, "X") for n in range(form_count)]
    stats = [(entity, form, 1, EARLY, LATE) for entity in cohort for form in forms]
    edge = [
        (entity, f"{n:010d}-24-000001", forms[0], LATE.date(), LATE, LATE, "acceptance")
        for n, entity in enumerate(cohort)
    ]
    conn = fake_conn({"GROUP BY": stats, "d.public_at ASC": edge, "d.public_at DESC": edge})
    context = evidence_helpers.make_context(AS_OF, CORPUS)
    result = resolve_company(conn, i.ResolveCompanyRequest(query="n"), context, companies=cohort)
    assert len(result.matches) == 20
    assert len(result.coverage_note.text) <= 1000
    assert summary in result.coverage_note.text
    assert "of 20 issuers public from" in result.coverage_note.text
    assert result.coverage_note.issuers == tuple(c.cik for c in cohort.values())
    assert len(result.coverage_note.forms) == form_count  # counted in the text, listed here
    _validate(result, "mcp-resolve-company-output")


def test_the_match_cap_applies_after_visibility(fake_conn: Any, evidence_helpers: Any) -> None:
    # 25 candidates; the 20 that sort first have nothing visible.
    cohort = {}
    for n in range(25):
        company = i.Company(f"00000000-0000-4000-8000-{n:012d}", f"{n:010d}", None, f"Co {n:02d}")
        cohort[company.entity_id] = company
    visible = list(cohort)[20:]
    stats = [(entity, "10-K", 1, EARLY, LATE) for entity in visible]
    edge = [
        (entity, f"{n:010d}-24-000001", "10-K", LATE.date(), LATE, LATE, "acceptance")
        for n, entity in enumerate(visible, start=20)
    ]
    conn = fake_conn({"GROUP BY": stats, "d.public_at ASC": edge, "d.public_at DESC": edge})
    context = evidence_helpers.make_context(AS_OF, CORPUS)
    result = resolve_company(conn, i.ResolveCompanyRequest(query="co"), context, companies=cohort)
    assert [match.company.entity_id for match in result.matches] == visible
    queried = [params["entities"] for sql, params in conn.statements if "GROUP BY" in sql]
    assert all(len(batch) <= 20 for batch in queried)
    assert [entity for batch in queried for entity in batch] == list(cohort)


def test_list_filings_takes_no_name_fragment(world: Any) -> None:
    with pytest.raises(i.EvidenceReadError) as raised:
        world.listing({"GROUP BY": _stats(CRM), "LIMIT": [_page_row(1, LATE)]}, company="Salesf")
    assert vars(raised.value) == vars(i.EvidenceReadError.not_found())


def test_forms_are_upper_cased_and_cursors_bind_the_resolved_company(world: Any) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    answers = {"GROUP BY": _stats(CRM), "LIMIT": rows}
    first = world.listing(answers, company="CRM", forms=("10-k", "8-K"))
    page = next(params for sql, params in world.conn.statements if "LIMIT" in sql)
    assert page["forms"] == ["10-K", "8-K"]
    assert first.coverage_note.forms == ("10-K", "8-K")
    # The same company and forms, spelled differently, continue the listing.
    for spelling in ("crm", "1108524", CRM.entity_id):
        world.listing(answers, company=spelling, forms=("8-k", "10-K"), cursor=first.next_cursor)
    # NOW is in the cohort and has no visible filing, so a foreign cursor is not_found.
    with pytest.raises(i.EvidenceReadError) as raised:
        world.listing(answers, company="NOW", forms=("10-K", "8-K"), cursor=first.next_cursor)
    assert vars(raised.value) == vars(i.EvidenceReadError.not_found())
    assert not any("LIMIT" in sql for sql in world.conn.sql)


def test_shared_name_cursor_continues_by_each_identifier_of_the_visible_company(world: Any) -> None:
    rows = [_page_row(3, LATE), _page_row(2, EARLY), _page_row(1, EARLY)]
    first = world.listing({"GROUP BY": _stats(CRM), "LIMIT": rows}, company=CRM.name)
    assert first.next_cursor is not None
    for spelling in (CRM.entity_id, CRM.ticker, CRM.cik, CRM.name):
        page = world.listing(
            {"GROUP BY": _stats(CRM), "LIMIT": rows[2:]},
            company=spelling,
            cursor=first.next_cursor,
        )
        assert ([f.document_id for f in page.filings], page.next_cursor) == ([DOCS[1]], None)


@pytest.mark.parametrize("company", ["CRM", CRM.name])
def test_forged_cursors_do_no_database_work_even_for_a_shared_name(
    world: Any, company: str
) -> None:
    with pytest.raises(i.EvidenceReadError, check=lambda e: e.code == "invalid_input"):
        world.listing({}, company=company, cursor="not-a-signed-cursor")
    assert world.conn.statements == []


@pytest.mark.parametrize(
    "position",
    [
        [],
        [LATE.isoformat()],
        [LATE.isoformat(), DOCS[0], "extra"],
        [None, None],
        ["not-a-time", DOCS[0]],
        ["2024-03-06T21:14:09", DOCS[0]],
        ["0001-01-01T00:00:00+01:00", DOCS[0]],
        [LATE.isoformat(), "not-a-uuid"],
        [LATE.isoformat(), None],
    ],
)
def test_signed_invalid_keyset_positions_fail_before_the_page_query(
    world: Any, position: list[Any]
) -> None:
    binding = {"tool": "list_filings", "entities": [CRM.entity_id], "forms": None}
    token = world.cursors.encode(world.context, binding, position)
    with pytest.raises(
        i.EvidenceReadError, check=lambda e: (e.code, e.field) == ("invalid_input", "cursor")
    ):
        world.listing({"GROUP BY": _stats(CRM)}, cursor=token)
    assert not any("LIMIT" in sql for sql in world.conn.sql)

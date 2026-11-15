"""Publication time at ingest, the backfill job and restatement repair (#393).

Runs against a real Postgres through the repo's manifest-pinned
``FixtureSecClient`` over committed fixtures: nothing here can reach sec.gov.

The pinned index (``sec_submissions_acceptance.json``) holds an original 10-Q
(A), an amendment accepted later the same day (B), a second amendment
accepted on a Friday evening and dated Monday (C), an 8-K with no acceptance
time (D) and an 8-K dated between B and C (E). Each amendment restates
revenue, which the 10-Q fixture tags twice (a canonical fact and a duplicate).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import pathlib
import threading
import time
import uuid
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import psycopg
import pytest

from fel_providers.mocks import MockStorageProvider
from fel_workers import queue
from fel_workers.consumer import entity_id_for_cik, handle_sec_filing_fetch, run_worker
from fel_workers.ingestion import pipeline
from fel_workers.ingestion.backfill import (
    JOB_KIND_SEC_PUBLICATION_BACKFILL,
    RepairReport,
    repair_restatement_links,
    run_publication_backfill_job,
)
from fel_workers.ingestion.discovery import discover_filings, fetch_job_payload
from fel_workers.ingestion.fixture_sec_client import FixtureSecClient
from fel_workers.ingestion.pipeline import create_corpus_version, publish_corpus_version
from fel_workers.ingestion.publication import derive_publication
from fel_workers.ingestion.raw_store import store_raw_document

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_DATABASE_URL") is None, reason="TEST_DATABASE_URL not configured"
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CIK = "9999997"
ENTITY = entity_id_for_cik(CIK)
A, B, C, D, E = (f"0009999997-26-00000{n}" for n in range(1, 6))
UNLISTED = "0009999997-26-000099"
REVENUE = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
_t = datetime.fromisoformat

# accepted_at, public_at, public_at_basis, timestamp_precision.
KNOWN = {
    A: (_t("2026-05-05T12:05:11Z"), _t("2026-05-05T12:05:11Z"), "acceptance", "second"),
    B: (_t("2026-05-05T19:40:02Z"), _t("2026-05-05T19:40:02Z"), "acceptance", "second"),
    # Accepted Friday 18:10 ET, dated Monday: public when EDGAR opened, 06:00 EDT.
    C: (_t("2026-05-08T22:10:45Z"), _t("2026-05-11T10:00:00Z"), "next_session_open", "second"),
}
UNKNOWN = (None, None, None, "date")
# (restating filing, restated filing, facts): B restates A, C restates B.
LINKS = [(B, A, 2), (C, B, 2)]


@pytest.fixture()
def sec(tmp_path: pathlib.Path) -> FixtureSecClient:
    submissions = (FIXTURES / "sec_submissions_acceptance.json").read_bytes()
    original = (FIXTURES / "synthetic_10q.html").read_bytes()
    narrative = (FIXTURES / "synthetic_8k_narrative.html").read_bytes()
    bodies = {
        A: original,
        B: original.replace(b">1,250<", b">1,300<"),
        C: original.replace(b">1,250<", b">1,350<"),
        D: narrative,
        E: narrative,
    }
    recent = json.loads(submissions)["filings"]["recent"]
    documents = []
    for accession, name in zip(recent["accessionNumber"], recent["primaryDocument"], strict=True):
        (tmp_path / name).write_bytes(bodies[accession])
        url = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{accession.replace('-', '')}"
        digest = hashlib.sha256(bodies[accession]).hexdigest()
        documents.append({"url": f"{url}/{name}", "path": name, "sha256": digest})
    (tmp_path / "submissions.json").write_bytes(submissions)
    index = {
        "cik": CIK,
        "path": "submissions.json",
        "sha256": hashlib.sha256(submissions).hexdigest(),
    }
    manifest = {
        "schema_version": "sec-fixture-transport/v1",
        "documents": documents,
        "submissions": [index],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return FixtureSecClient(tmp_path)


def _ingest(
    conn: psycopg.Connection,
    sec: FixtureSecClient,
    accessions: tuple[str, ...] | list[str],
    *,
    legacy: bool = False,
    **override: Any,
) -> None:
    """Fetch and ingest filings in the given order, through the job handler.

    ``legacy`` drops the acceptance time, as jobs enqueued before #393 did.
    """
    payloads = {ref.accession: fetch_job_payload(ref) for ref in discover_filings(sec, CIK)}
    for accession in accessions:
        payload = {**payloads[accession], **override}
        if legacy:
            del payload["acceptance_datetime"]
        outcome = handle_sec_filing_fetch(conn, MockStorageProvider(), sec, payload)
        assert outcome.status == "succeeded"


def _publication(conn: psycopg.Connection) -> dict[str, tuple[Any, ...]]:
    rows = conn.execute(
        "SELECT accession, accepted_at, public_at, public_at_basis, timestamp_precision"
        " FROM documents"
    ).fetchall()
    return {row[0]: tuple(row[1:]) for row in rows}


def _links(conn: psycopg.Connection) -> list[tuple[Any, ...]]:
    return conn.execute(
        "SELECT d.accession, td.accession, count(*)::int"
        " FROM financial_facts f"
        " JOIN document_versions v ON v.id = f.document_version_id"
        " JOIN documents d ON d.id = v.document_id"
        " JOIN financial_facts t ON t.id = f.restates"
        " JOIN document_versions tv ON tv.id = t.document_version_id"
        " JOIN documents td ON td.id = tv.document_id"
        " GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()


def _row_versions(conn: psycopg.Connection) -> dict[str, str]:
    """xmin of every document and fact row: any rewrite, even a no-op, changes it."""
    return dict(
        conn.execute(
            "SELECT 'document ' || id::text, xmin::text FROM documents"
            " UNION ALL SELECT 'fact ' || id::text, xmin::text FROM financial_facts"
        ).fetchall()
    )


def _add_parse(conn: psycopg.Connection, document_id: Any, value: str) -> None:
    """A parsed version of a stored document with one canonical revenue fact
    under the key the 10-Q fixtures restate."""
    key = conn.execute(
        "SELECT fact_key FROM financial_facts WHERE concept = %s AND dimensions = '{}'::jsonb"
        " LIMIT 1",
        (REVENUE,),
    ).fetchone()
    assert key is not None
    version, section, span, fact = (str(uuid.uuid4()) for _ in range(4))
    conn.execute(
        "INSERT INTO document_versions (id, document_id, parser_version,"
        " normalizer_version, canonical_text_key) VALUES (%s, %s, 'seeded', 'n', 'text/seeded')",
        (version, document_id),
    )
    conn.execute(
        "INSERT INTO sections (id, document_version_id, heading, heading_path, ord,"
        " start_char, end_char) VALUES (%s, %s, 'facts', %s, 0, 0, 10)",
        (section, version, ["facts"]),
    )
    conn.execute(
        "INSERT INTO source_spans (id, document_version_id, section_id, start_char,"
        " end_char, text_hash) VALUES (%s, %s, %s, 0, 5, %s)",
        (span, version, section, "sha256:" + "ab" * 32),
    )
    conn.execute(
        "INSERT INTO financial_facts (id, entity_id, document_version_id, concept, value,"
        " unit, period_type, period_start, period_end, source_span_id, fact_key)"
        " VALUES (%s, %s, %s, %s, %s, 'USD', 'duration', '2026-01-01', '2026-03-31', %s, %s)",
        (fact, ENTITY, version, REVENUE, value, span, key[0]),
    )


def _seed_company_facts_snapshot(conn: psycopg.Connection) -> None:
    """A COMPANYFACTS snapshot under listed accession E, dated between B and
    C, with a different value for the restated revenue key. Only its form
    marks it: every other backfill and repair check would accept it."""
    document_id, when = str(uuid.uuid4()), _t("2026-05-06T00:00:00Z")
    conn.execute(
        "INSERT INTO documents (id, entity_id, accession, form, source_url, content_hash,"
        " storage_key, published_at, filed_at) VALUES (%s, %s, %s, 'COMPANYFACTS',"
        " 'https://example.invalid/companyfacts', %s, 'raw/companyfacts', %s, %s)",
        (document_id, ENTITY, E, "sha256:" + "cf" * 32, when, when),
    )
    _add_parse(conn, document_id, "999")


class _EditedIndex:
    """The pinned transport with its submissions index edited for one test."""

    def __init__(self, inner: FixtureSecClient, edit: Callable[[dict[str, list[Any]]], None]):
        self._inner, self._edit = inner, edit

    def submissions(self, cik: str) -> dict[str, object]:
        payload: Any = self._inner.submissions(cik)
        self._edit(payload["filings"]["recent"])
        return payload

    def fetch_document(self, url: str) -> bytes:
        return self._inner.fetch_document(url)


def _newest_two_only(recent: dict[str, list[Any]]) -> None:
    """A partial first pass: only D (no acceptance time) and C are listed."""
    for rows in recent.values():
        del rows[2:]


def _offsetless_time_for_d(recent: dict[str, list[Any]]) -> None:
    recent["acceptanceDateTime"][0] = "2026-05-12T09:00:00"


def test_fetch_stores_acceptance_and_derived_publication_time(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    _ingest(corpus_conn, sec, [A, C, D])
    assert _publication(corpus_conn) == {A: KNOWN[A], C: KNOWN[C], D: UNKNOWN}
    # filed_at stays the filing date and published_at is unchanged: midnight UTC.
    dates = corpus_conn.execute(
        "SELECT accession, published_at, filed_at FROM documents ORDER BY accession"
    ).fetchall()
    assert dates == [
        (A, _t("2026-05-05T00:00:00Z"), _t("2026-05-05T00:00:00Z")),
        (C, _t("2026-05-11T00:00:00Z"), _t("2026-05-11T00:00:00Z")),
        (D, _t("2026-05-12T00:00:00Z"), _t("2026-05-12T00:00:00Z")),
    ]


@pytest.mark.parametrize(
    "override",
    [
        {"acceptance_datetime": "2026-05-05T08:05:11"},  # no offset: never assumed
        {"acceptance_datetime": 20260505080511},
        {"filed_on": "2026-05-05T00:00:00+00:00"},  # an instant is not a filing date
    ],
)
def test_unusable_acceptance_input_fails_before_fetch_without_echo(
    corpus_conn: psycopg.Connection,
    sec: FixtureSecClient,
    override: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_fetch(url: str) -> bytes:
        pytest.fail("an unusable acceptance time reached the transport")

    monkeypatch.setattr(sec, "fetch_document", no_fetch)
    payloads = {ref.accession: fetch_job_payload(ref) for ref in discover_filings(sec, CIK)}
    with pytest.raises(ValueError) as excinfo:
        handle_sec_filing_fetch(
            corpus_conn, MockStorageProvider(), sec, {**payloads[A], **override}
        )
    assert "2026" not in str(excinfo.value), "the untrusted payload was echoed"
    assert corpus_conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)


@pytest.mark.parametrize(
    "order", list(itertools.permutations((A, B, C))), ids=lambda o: "".join(x[-1] for x in o)
)
def test_restatement_links_do_not_depend_on_ingestion_order(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient, order: tuple[str, ...]
) -> None:
    chronological = order == (A, B, C)
    _ingest(corpus_conn, sec, order)
    if chronological:
        # A and its amendment B share a filing date. Ordering by publication
        # time links them at ingest; date-only ordering never did.
        assert _links(corpus_conn) == LINKS
    report = repair_restatement_links(corpus_conn, entity_id=ENTITY)
    assert _links(corpus_conn) == LINKS
    assert (report == RepairReport()) == chronological
    if order == (C, B, A):  # EDGAR's own listing order: every link was missed
        assert (report.linked, report.relinked, report.cleared) == (4, 0, 0)
    if order == (A, C, B):  # C was linked to A before B existed
        assert (report.linked, report.relinked, report.cleared) == (0, 2, 0)
    settled = _row_versions(corpus_conn)
    assert repair_restatement_links(corpus_conn, entity_id=ENTITY) == RepairReport()
    assert _row_versions(corpus_conn) == settled


@pytest.mark.parametrize("resolved", [A, B], ids=["original resolved", "amendment resolved"])
@pytest.mark.parametrize("order", [(A, B), (B, A)], ids=["original first", "amendment first"])
def test_same_day_pair_with_one_side_unresolved_never_links(
    corpus_conn: psycopg.Connection,
    sec: FixtureSecClient,
    resolved: str,
    order: tuple[str, str],
) -> None:
    """A missing public_at is unknown, not midnight. Sorting it at midnight
    made a resolved original restate its unresolved same-day amendment."""
    for accession in order:
        _ingest(corpus_conn, sec, [accession], legacy=accession != resolved)
    assert _publication(corpus_conn)[resolved] == KNOWN[resolved]
    assert _links(corpus_conn) == []
    assert repair_restatement_links(corpus_conn, entity_id=ENTITY) == RepairReport()
    assert _links(corpus_conn) == []


def test_repair_keeps_a_link_to_an_older_parse_of_the_right_filing(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """Re-parsing the original must not move the amendment's link: the edge
    to that filing is already right, and corpus pins may expose it."""
    _ingest(corpus_conn, sec, [A, B])
    original = corpus_conn.execute("SELECT id FROM documents WHERE accession = %s", (A,)).fetchone()
    assert original is not None
    _add_parse(corpus_conn, original[0], "1249000000")  # a newer parse, still not B's value
    before = _row_versions(corpus_conn)
    assert repair_restatement_links(corpus_conn, entity_id=ENTITY) == RepairReport()
    assert _row_versions(corpus_conn) == before
    assert _links(corpus_conn) == [(B, A, 2)]


def test_backfill_as_fel_worker_fills_repairs_and_never_rewrites(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """The whole job under the real least-privilege role (migration 0013)."""
    corpus_conn.execute("SET ROLE fel_worker")
    _ingest(corpus_conn, sec, [A, B], legacy=True)
    _seed_company_facts_snapshot(corpus_conn)
    _ingest(corpus_conn, sec, [C, D], legacy=True)
    _ingest(corpus_conn, sec, [D], legacy=True, accession=UNLISTED)
    # Date-only rows: the same-day amendment B never linked to A.
    assert _links(corpus_conn) == [(C, B, 2)]
    assert set(_publication(corpus_conn).values()) == {UNKNOWN}

    first = run_publication_backfill_job(
        corpus_conn, _EditedIndex(sec, _newest_two_only), {"cik": CIK}
    )
    assert (first.updated, first.conflicts, first.repair) == (1, (), RepairReport())
    after_first = _row_versions(corpus_conn)

    second = run_publication_backfill_job(corpus_conn, sec, {"cik": CIK})
    assert (second.updated, second.unresolved, second.conflicts) == (2, 2, ())
    assert _publication(corpus_conn) == {
        **KNOWN,
        D: UNKNOWN,  # no acceptance time in the index
        UNLISTED: UNKNOWN,  # not in the index at all
        E: UNKNOWN,  # the company-facts snapshot, never touched
    }
    assert _links(corpus_conn) == LINKS
    assert (second.repair.linked, second.repair.relinked, second.repair.cleared) == (2, 0, 0)
    assert len(second.repair.document_version_ids) == 1
    after_second = _row_versions(corpus_conn)
    # Resumed, not redone: only documents A and B and B's two revenue facts were
    # written. C, set by the first pass, kept its row version.
    assert len({key for key, xmin in after_second.items() if after_first[key] != xmin}) == 4

    third = run_publication_backfill_job(corpus_conn, sec, {"cik": CIK})
    assert (third.updated, third.unresolved, third.conflicts) == (0, 2, ())
    assert third.repair == RepairReport()
    assert _row_versions(corpus_conn) == after_second

    assert corpus_conn.execute("SELECT current_user").fetchone() == ("fel_worker",)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        corpus_conn.execute("UPDATE documents SET form = form")


def test_backfill_keeps_set_values_and_leaves_unverifiable_rows_null(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    _ingest(corpus_conn, sec, [A], legacy=True)
    # Stored filing date disagrees with the pinned index: not verifiable, so
    # it stays NULL, and the disagreement is reported for an operator.
    _ingest(corpus_conn, sec, [B], legacy=True, filed_on="2026-05-04")
    _ingest(corpus_conn, sec, [C])  # set at ingest, and correct
    # Set at ingest to something the index does not say: reported, never overwritten.
    _ingest(corpus_conn, sec, [E], acceptance_datetime="2026-05-06T12:00:00.000Z")
    _ingest(corpus_conn, sec, [D], legacy=True)  # its index entry has no UTC offset
    index = _EditedIndex(sec, _offsetless_time_for_d)
    report = run_publication_backfill_job(corpus_conn, index, {"cik": CIK})
    assert (report.updated, report.unresolved, report.conflicts) == (1, 2, (B, E))
    noon = _t("2026-05-06T12:00:00Z")
    assert _publication(corpus_conn) == {
        A: KNOWN[A],
        B: UNKNOWN,
        C: KNOWN[C],
        D: UNKNOWN,
        E: (noon, noon, "acceptance", "second"),
    }


def test_worker_runs_the_backfill_job_from_the_queue(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    _ingest(corpus_conn, sec, [A, B], legacy=True)
    queue.enqueue(
        corpus_conn,
        kind=JOB_KIND_SEC_PUBLICATION_BACKFILL,
        payload={"cik": CIK},
        queue="ingestion",
    )
    completed = run_worker(
        corpus_conn, MockStorageProvider(), sec, queue_name="ingestion", max_iterations=2
    )
    assert completed == 1
    assert _publication(corpus_conn) == {A: KNOWN[A], B: KNOWN[B]}
    assert _links(corpus_conn) == [(B, A, 2)]


def test_company_facts_snapshot_can_never_be_given_a_publication_time(
    corpus_conn: psycopg.Connection,
) -> None:
    with pytest.raises(ValueError, match="COMPANYFACTS"):
        store_raw_document(
            corpus_conn,
            MockStorageProvider(),
            entity_id=ENTITY,
            accession="COMPANYFACTS-0009999997-2026-05-06-00000000",
            source_url="https://example.invalid/companyfacts",
            raw=b"{}",
            published_at=_t("2026-05-06T00:00:00Z"),
            form="COMPANYFACTS",
            publication=derive_publication("2026-05-06T13:00:00Z", date(2026, 5, 6)),
        )
    assert corpus_conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)


# --- Review round 2 (#417): published pins, publication-time order, reparse ---


def _version(conn: psycopg.Connection, accession: str) -> str:
    row = conn.execute(
        "SELECT v.id FROM document_versions v JOIN documents d ON d.id = v.document_id"
        " WHERE d.accession = %s ORDER BY v.created_at DESC, v.id DESC LIMIT 1",
        (accession,),
    ).fetchone()
    assert row is not None
    return str(row[0])


def _publish(conn: psycopg.Connection, *accessions: str) -> str:
    corpus = create_corpus_version(
        conn, label="pin", document_version_ids=[_version(conn, a) for a in accessions]
    )
    publish_corpus_version(conn, corpus)
    return corpus


def _strictly_visible(conn: psycopg.Connection, corpus: str, cutoff: datetime) -> int:
    """Documents of a pin visible under the strict MCP rule at a cutoff."""
    row = conn.execute(
        "SELECT count(DISTINCT d.id) FROM corpus_version_documents c"
        " JOIN document_versions v ON v.id = c.document_version_id"
        " JOIN documents d ON d.id = v.document_id"
        " WHERE c.corpus_version_id = %s AND d.public_at <= %s",
        (corpus, cutoff),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _other_connection() -> psycopg.Connection:
    url = os.environ.get("TEST_DATABASE_URL")
    assert url is not None
    return psycopg.connect(url, autocommit=True)


def _blocked_on_advisory_lock(observer: psycopg.Connection, worker: threading.Thread) -> bool:
    """True once another backend waits on an advisory lock while ``worker`` runs."""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and worker.is_alive():
        row = observer.execute(
            "SELECT count(*) FROM pg_locks l JOIN pg_database db ON db.oid = l.database"
            " WHERE l.locktype = 'advisory' AND NOT l.granted"
            " AND db.datname = current_database()"
        ).fetchone()
        if row is not None and row[0] > 0:
            return True
        worker.join(timeout=0.05)
    return False


def test_backfill_never_changes_a_published_pin(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """Active and superseded pins keep their publication metadata; only the
    unpinned filing is backfilled, and the rejected ones are reported."""
    _ingest(corpus_conn, sec, [A, B, C], legacy=True)
    superseded = _publish(corpus_conn, A)
    active = _publish(corpus_conn, C)
    cutoff = _t("2026-06-01T00:00:00Z")
    assert (
        _strictly_visible(corpus_conn, superseded, cutoff),
        _strictly_visible(corpus_conn, active, cutoff),
    ) == (0, 0)

    report = run_publication_backfill_job(corpus_conn, sec, {"cik": CIK})

    assert _publication(corpus_conn) == {A: UNKNOWN, B: KNOWN[B], C: UNKNOWN}
    assert (
        _strictly_visible(corpus_conn, superseded, cutoff),
        _strictly_visible(corpus_conn, active, cutoff),
    ) == (0, 0)
    assert (report.updated, report.rejected) == (1, (A, C))


def test_repair_preserves_restates_edges_inside_a_published_pin(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """C -> A is published; B arriving later between them must not move it."""
    _ingest(corpus_conn, sec, [A, C])
    assert _links(corpus_conn) == [(C, A, 2)]
    _publish(corpus_conn, A, C)
    _ingest(corpus_conn, sec, [B])  # unpinned; restates A at ingest

    report = repair_restatement_links(corpus_conn, entity_id=ENTITY)

    assert _links(corpus_conn) == [(B, A, 2), (C, A, 2)]
    assert (report.relinked, report.rejected_versions) == (0, (_version(corpus_conn, C),))


def test_publication_waits_for_an_uncommitted_backfill(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """Publishing during an uncommitted backfill must wait for it, so the pin is
    published over the backfilled rows and is never changed afterwards."""
    _ingest(corpus_conn, sec, [A], legacy=True)
    draft = create_corpus_version(
        corpus_conn, label="race", document_version_ids=[_version(corpus_conn, A)]
    )
    errors: list[BaseException] = []

    def publish() -> None:
        try:
            with _other_connection() as conn:
                publish_corpus_version(conn, draft)
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            errors.append(exc)

    publisher = threading.Thread(target=publish)
    with _other_connection() as observer:
        with corpus_conn.transaction():
            run_publication_backfill_job(corpus_conn, sec, {"cik": CIK})
            publisher.start()
            blocked = _blocked_on_advisory_lock(observer, publisher)
            still_waiting = publisher.is_alive()
        publisher.join(timeout=30)
    assert not errors
    assert blocked and still_waiting, "publication did not wait for the uncommitted backfill"
    status = corpus_conn.execute(
        "SELECT status FROM corpus_versions WHERE id = %s", (draft,)
    ).fetchone()
    assert status == ("active",)
    assert _publication(corpus_conn) == {A: KNOWN[A]}
    after = run_publication_backfill_job(corpus_conn, sec, {"cik": CIK})
    assert (after.updated, after.rejected, after.repair) == (0, (), RepairReport())


def test_backfill_waits_for_an_uncommitted_publication_then_rejects_it(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient
) -> None:
    """The other order: a backfill that starts while a publication is
    uncommitted must see the new pin once it commits, and leave it alone."""
    _ingest(corpus_conn, sec, [A], legacy=True)
    draft = create_corpus_version(
        corpus_conn, label="race", document_version_ids=[_version(corpus_conn, A)]
    )
    reports: list[Any] = []

    def backfill() -> None:
        try:
            reports.append(run_publication_backfill_job(corpus_conn, sec, {"cik": CIK}))
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            reports.append(exc)

    worker = threading.Thread(target=backfill)
    with _other_connection() as publisher:
        with publisher.transaction():
            publish_corpus_version(publisher, draft)
            worker.start()
            blocked = _blocked_on_advisory_lock(publisher, worker)
            still_waiting = worker.is_alive()
        worker.join(timeout=30)
    assert blocked and still_waiting, "the backfill did not wait for the uncommitted publication"
    assert _publication(corpus_conn) == {A: UNKNOWN}
    assert len(reports) == 1 and not isinstance(reports[0], BaseException), reports
    assert (reports[0].updated, reports[0].rejected) == (0, (A,))


@pytest.mark.parametrize("order", [(A, B, C), (B, A, C)], ids=["ABC", "BAC"])
def test_publication_time_not_filing_date_orders_restatements(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient, order: tuple[str, ...]
) -> None:
    """A filed May 4 but public May 7; B filed and public May 5; C public May 11.
    By publication B < A < C, so A restates B and C restates A. Ordering by
    filing date made B restate the not-yet-public A and C restate B."""
    overrides = {
        A: {"filed_on": "2026-05-04", "acceptance_datetime": "2026-05-07T14:00:00.000Z"},
        B: {"filed_on": "2026-05-05", "acceptance_datetime": "2026-05-05T14:00:00.000Z"},
        C: {},
    }
    for accession in order:
        _ingest(corpus_conn, sec, [accession], **overrides[accession])
    may7, may5 = _t("2026-05-07T14:00:00Z"), _t("2026-05-05T14:00:00Z")
    assert _publication(corpus_conn)[A] == (may7, may7, "acceptance", "second")
    assert _publication(corpus_conn)[B] == (may5, may5, "acceptance", "second")
    repair_restatement_links(corpus_conn, entity_id=ENTITY)
    assert _links(corpus_conn) == [(A, B, 2), (C, A, 2)]
    assert repair_restatement_links(corpus_conn, entity_id=ENTITY) == RepairReport()


def test_reparse_orders_by_stored_publication_time(
    corpus_conn: psycopg.Connection, sec: FixtureSecClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parser-version bump re-parses B through a legacy payload with no
    acceptance time. The stored document keeps its public_at, and the new parse
    must be ordered by it: B still restates A."""
    _ingest(corpus_conn, sec, [A, B])
    monkeypatch.setattr(pipeline, "PARSER_VERSION", "fel-parser/reparse-test")
    _ingest(corpus_conn, sec, [B], legacy=True)
    reparsed = _version(corpus_conn, B)
    targets = corpus_conn.execute(
        "SELECT td.accession, count(*)::int FROM financial_facts f"
        " JOIN financial_facts t ON t.id = f.restates"
        " JOIN document_versions tv ON tv.id = t.document_version_id"
        " JOIN documents td ON td.id = tv.document_id"
        " WHERE f.document_version_id = %s GROUP BY 1",
        (reparsed,),
    ).fetchall()
    assert _publication(corpus_conn)[B] == KNOWN[B]
    assert targets == [(A, 2)]

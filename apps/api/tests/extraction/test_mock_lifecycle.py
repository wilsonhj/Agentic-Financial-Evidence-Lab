"""Created jobs enter the real durable worker using explicitly scoped mock replies."""

from dataclasses import replace

import psycopg
from psycopg.rows import dict_row

from fel_providers.mocks import MockStructuredLLMProvider
from fel_workers.extraction.handler import handle_extraction_run
from tests.extraction.test_run_creation import _create


class ScopedMock(MockStructuredLLMProvider):
    """Keep committed mock financial data, bind only this test's real source IDs."""

    def __init__(self, tenant, source):
        super().__init__()
        self.identities = {
            "source_span_id": source["span"],
            "document_version_id": source["version"],
            "entity_id": tenant["entity"],
        }

    def generate_structured(self, request):
        result = super().generate_structured(request)

        def scoped(value):
            if isinstance(value, dict):
                return {key: self.identities.get(key, scoped(item)) for key, item in value.items()}
            if isinstance(value, list):
                return [scoped(item) for item in value]
            return value

        return replace(result, parsed=scoped(result.parsed))


def asserting_span_hash(parsed, text_hash):
    """Make every proposal citation assert the content address of its span."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("proposals"), list):
        return parsed
    return {
        **parsed,
        "proposals": [
            {**item, "evidence": [{**edge, "text_hash": text_hash} for edge in item["evidence"]]}
            for item in parsed["proposals"]
        ],
    }


class HashAssertingMock(ScopedMock):
    """A role that opened the span it cites: each citation asserts its text_hash.

    The committed mock cites by membership only, which the worker grades
    ``partial`` and blocks. Asserting the pinned span's content address is the
    only citation the worker grades ``verified``.
    """

    def __init__(self, tenant, source):
        super().__init__(tenant, source)
        self.text_hash = source["hash"]

    def generate_structured(self, request):
        result = super().generate_structured(request)
        return replace(result, parsed=asserting_span_hash(result.parsed, self.text_hash))


def test_created_job_reaches_durable_waiting_review_with_bound_source_pins(
    extraction_client, extraction_tenant, extraction_url, source_fixture
):
    response = _create(extraction_client, extraction_tenant, source_fixture)
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    with psycopg.connect(extraction_url, row_factory=dict_row) as conn:
        job = conn.execute("SELECT org_id,payload FROM jobs WHERE id=%s", (run_id,)).fetchone()
    with psycopg.connect(extraction_url, autocommit=True) as conn:
        conn.execute("SET ROLE fel_worker")
        state = handle_extraction_run(
            conn,
            ScopedMock(extraction_tenant, source_fixture),
            job["payload"],
            job_org_id=str(job["org_id"]),
        )
    assert state.status == "waiting_review"
    with psycopg.connect(extraction_url, row_factory=dict_row) as conn:
        run = conn.execute(
            "SELECT status,policy_id FROM extraction_runs WHERE id=%s", (run_id,)
        ).fetchone()
        drafts = conn.execute(
            "SELECT id,record_confidence FROM extraction_proposals WHERE run_id=%s", (run_id,)
        ).fetchall()
        edges = conn.execute(
            "SELECT e.source_span_id,e.document_version_id FROM extraction_proposal_evidence e "
            "JOIN extraction_proposals p ON p.id=e.proposal_id WHERE p.run_id=%s",
            (run_id,),
        ).fetchall()
    assert (
        run["status"] == "waiting_review" and str(run["policy_id"]) == extraction_tenant["policy"]
    )
    assert len(drafts) == 1 and drafts[0]["record_confidence"] is None
    assert {(str(edge["source_span_id"]), str(edge["document_version_id"])) for edge in edges} == {
        (source_fixture["span"], source_fixture["version"])
    }

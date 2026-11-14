"""A proposal without a verified citation cannot be promoted by accept or merge."""

import uuid

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from fel_workers.extraction.hashing import hash_json
from tests.extraction.test_conflicts import alternative, decision
from tests.extraction.test_mock_lifecycle import HashAssertingMock, ScopedMock
from tests.extraction.test_review_atomicity import command

WORKER_BLOCKER = "no verified citation: no cited span asserts a matching text_hash"
PROMOTION_TABLES = ("approved_extraction_records", "approved_extraction_versions")


def _review(client, tenant, body):
    return client.post(
        "/v1/extractions/review",
        json=body,
        headers={**tenant["headers"], "Idempotency-Key": str(uuid.uuid4())},
    )


def _persisted(url, proposal):
    with psycopg.connect(url, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT state,version,payload,validation_summary FROM extraction_proposals WHERE id=%s",
            (proposal,),
        ).fetchone()
        row["grades"] = [
            edge["citation_status"]
            for edge in conn.execute(
                "SELECT citation_status FROM extraction_proposal_evidence WHERE proposal_id=%s",
                (proposal,),
            ).fetchall()
        ]
    return row


def _assert_blocked(response, url, tenant, proposals):
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    with psycopg.connect(url) as conn:
        for table in (*PROMOTION_TABLES, "extraction_reviews"):
            count = conn.execute(
                psycopg.sql.SQL("SELECT count(*) FROM {} WHERE org_id=%s").format(
                    psycopg.sql.Identifier(table)
                ),
                (tenant["org"],),
            ).fetchone()[0]
            assert count == 0, table
    for proposal in proposals:
        row = _persisted(url, proposal)
        assert (row["state"], row["version"]) == ("needs_review", 1)


def _manifests(url, tenant):
    with psycopg.connect(url) as conn:
        return [
            row[0]
            for row in conn.execute(
                "SELECT evidence_manifest FROM approved_extraction_versions WHERE org_id=%s",
                (tenant["org"],),
            ).fetchall()
        ]


def _seed(url, base, source, citation, value="100"):
    """Persist one same-run candidate with an explicit, self-consistent citation state.

    A separate reporting period keeps it independent of the base proposal, so
    the review outcome depends on this row's own citation alone.
    """
    edge = {
        "source_span_id": source["span"],
        "document_version_id": source["version"],
        "role": "supports",
    }
    asserted, grade = {
        "string_form": ([source["span"]], "partial"),
        "without_text_hash": ([edge], "partial"),
        "verified": ([{**edge, "text_hash": source["hash"]}], "verified"),
    }[citation]
    blockers = [] if grade == "verified" else [WORKER_BLOCKER]
    payload = {
        **base["payload"],
        "value": value,
        "raw_value": "$" + value + " million",
        "period": {**base["payload"]["period"], "instant": "2025-09-30"},
        "evidence": asserted,
    }
    proposal = str(uuid.uuid4())
    with psycopg.connect(url, row_factory=dict_row) as conn:
        summary = conn.execute(
            "SELECT validation_summary FROM extraction_proposals WHERE id=%s", (base["proposal"],)
        ).fetchone()["validation_summary"]
        conn.execute(
            "INSERT INTO extraction_proposals(id,org_id,workspace_id,run_id,kind,metric_id,"
            "payload,raw_payload_hash,definition_hash,comparability_key,validation_summary,state) "
            "SELECT %s,org_id,workspace_id,run_id,kind,metric_id,%s,%s,definition_hash,"
            "comparability_key,%s,'needs_review' FROM extraction_proposals WHERE id=%s",
            (
                proposal,
                Jsonb(payload),
                hash_json(payload),
                Jsonb({**summary, "ok": not blockers, "blockers": blockers}),
                base["proposal"],
            ),
        )
        conn.execute(
            "INSERT INTO extraction_proposal_evidence(proposal_id,org_id,source_span_id,"
            "document_version_id,role,citation_status) SELECT %s,org_id,source_span_id,"
            "document_version_id,role,%s FROM extraction_proposal_evidence WHERE proposal_id=%s",
            (proposal, grade, base["proposal"]),
        )
    return proposal


def _group(url, tenant, run, members):
    group = str(uuid.uuid4())
    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO extraction_conflicts(id,org_id,workspace_id,conflict_key,reason_codes,"
            "occurrence_run_id) VALUES (%s,%s,%s,%s,ARRAY['value_disagreement'],%s)",
            (group, tenant["org"], tenant["workspace"], hash_json({"fixture": group}), run),
        )
        for member in members:
            conn.execute(
                "INSERT INTO extraction_conflict_members(conflict_id,org_id,proposal_id) "
                "VALUES (%s,%s,%s)",
                (group, tenant["org"], member),
            )
    return group


def _merge(client, tenant, ids, source_id, group):
    return _review(
        client,
        tenant,
        {
            "action": "merge",
            "extraction_ids": ids,
            "expected_versions": dict.fromkeys(ids, 1),
            "reason": "Merge source evidence.",
            "patch": {"payload_source_id": source_id},
            "conflict_resolution": [decision(client, tenant, group, [source_id])],
        },
    )


def test_worker_blocked_membership_only_proposal_is_not_accepted(
    extraction_client, extraction_tenant, extraction_url, worker_proposal
):
    fixture = worker_proposal(ScopedMock)
    persisted = _persisted(extraction_url, fixture["proposal"])
    assert persisted["grades"] == ["partial"]
    assert all("text_hash" not in edge for edge in persisted["payload"]["evidence"])
    assert persisted["validation_summary"]["blockers"] == [WORKER_BLOCKER]
    response = _review(extraction_client, extraction_tenant, command(fixture["proposal"]))
    _assert_blocked(response, extraction_url, extraction_tenant, [fixture["proposal"]])
    with psycopg.connect(extraction_url) as conn:
        assert conn.execute(
            "SELECT status FROM extraction_runs WHERE id=%s", (fixture["run"],)
        ).fetchone() == ("waiting_review",)


def test_worker_blocked_membership_only_proposals_are_not_merged(
    extraction_client, extraction_tenant, extraction_url, worker_proposal
):
    fixture = worker_proposal(ScopedMock)
    other, group = alternative(extraction_url, extraction_tenant, fixture)
    for proposal in (fixture["proposal"], other):
        persisted = _persisted(extraction_url, proposal)
        assert persisted["grades"] == ["partial"]
        assert persisted["validation_summary"]["blockers"] == [WORKER_BLOCKER]
    ids = [fixture["proposal"], other]
    response = _merge(extraction_client, extraction_tenant, ids, fixture["proposal"], group)
    _assert_blocked(response, extraction_url, extraction_tenant, ids)


def test_worker_verified_proposal_is_still_accepted(
    extraction_client, extraction_tenant, extraction_url, worker_proposal, source_fixture
):
    fixture = worker_proposal(HashAssertingMock)
    persisted = _persisted(extraction_url, fixture["proposal"])
    assert persisted["grades"] == ["verified"]
    assert [edge["text_hash"] for edge in persisted["payload"]["evidence"]] == [
        source_fixture["hash"]
    ]
    assert persisted["validation_summary"]["blockers"] == []
    response = _review(extraction_client, extraction_tenant, command(fixture["proposal"]))
    assert response.status_code == 200, response.text
    assert len(response.json()["approved_record_ids"]) == 1
    manifests = _manifests(extraction_url, extraction_tenant)
    assert [[edge["citation_status"] for edge in manifest] for manifest in manifests] == [
        ["verified"]
    ]


@pytest.mark.parametrize("citation", ["string_form", "without_text_hash", "verified"])
def test_accept_follows_the_citation_the_proposal_asserted(
    extraction_client,
    extraction_tenant,
    extraction_url,
    waiting_review_fixture,
    source_fixture,
    citation,
):
    proposal = _seed(extraction_url, waiting_review_fixture, source_fixture, citation)
    response = _review(extraction_client, extraction_tenant, command(proposal))
    if citation != "verified":
        _assert_blocked(response, extraction_url, extraction_tenant, [proposal])
        return
    assert response.status_code == 200, response.text
    manifests = _manifests(extraction_url, extraction_tenant)
    assert [[edge["citation_status"] for edge in manifest] for manifest in manifests] == [
        ["verified"]
    ]


@pytest.mark.parametrize(
    "payload_source,other",
    [
        ("without_text_hash", "without_text_hash"),
        ("string_form", "string_form"),
        ("verified", "without_text_hash"),
        ("without_text_hash", "verified"),
        ("verified", "verified"),
    ],
)
def test_merge_needs_a_verified_citation_on_every_input(
    extraction_client,
    extraction_tenant,
    extraction_url,
    waiting_review_fixture,
    source_fixture,
    payload_source,
    other,
):
    base = waiting_review_fixture
    source_id = _seed(extraction_url, base, source_fixture, payload_source)
    other_id = _seed(extraction_url, base, source_fixture, other, value="110")
    ids = [source_id, other_id]
    group = _group(extraction_url, extraction_tenant, base["run"], ids)
    response = _merge(extraction_client, extraction_tenant, ids, source_id, group)
    if (payload_source, other) != ("verified", "verified"):
        _assert_blocked(response, extraction_url, extraction_tenant, ids)
        return
    assert response.status_code == 200, response.text
    assert len(response.json()["approved_record_ids"]) == 1
    manifests = _manifests(extraction_url, extraction_tenant)
    assert [[edge["citation_status"] for edge in manifest] for manifest in manifests] == [
        ["verified"]
    ]

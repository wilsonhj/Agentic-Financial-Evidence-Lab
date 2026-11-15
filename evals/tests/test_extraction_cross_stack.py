"""The acceptance provider changes source identity, never financial fixture data."""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.auth import make_mock_token
from app.db import pool_for
from app.main import app
from fel_providers.interfaces import StructuredGenerationRequest
from fel_providers.mocks import MockStructuredLLMProvider
from harness.extraction_cross_stack import (
    DIGEST,
    ScopedMock,
    main,
    seeded_span_hashes,
    verify,
)
from migrate import main as migrate


def _request(schema_name):
    return StructuredGenerationRequest(
        messages=[{"role": "user", "content": "Synthetic acceptance evidence"}],
        json_schema={},
        schema_name=schema_name,
        schema_version="acceptance/v1",
        max_output_tokens=1000,
    )


def _changed_only_identity_and_asserted_hash(baseline, actual, manifest, span_hashes):
    """Fail on any difference except scoped identities and a seeded-span hash.

    Returns the span ids whose citations gained a ``text_hash``.
    """
    identities = {
        "source_span_id": manifest["span"],
        "document_version_id": manifest["version"],
        "entity_id": manifest["entity"],
    }
    asserted = []

    def compare(left, right, *, citation=False):
        if isinstance(left, dict):
            # The one permitted addition: a proposal citation asserts the
            # content address of the seeded span it cites. Nothing is removed
            # and every other key and value must match exactly.
            added = right.keys() - left.keys()
            if citation and added == {"text_hash"}:
                assert right["text_hash"] == span_hashes[right["source_span_id"]]
                asserted.append(right["source_span_id"])
            else:
                assert left.keys() == right.keys()
            for key, value in left.items():
                if key in identities:
                    assert right[key] == identities[key]
                else:
                    compare(value, right[key], citation=key == "evidence")
        elif isinstance(left, list):
            assert len(left) == len(right)
            for before, after in zip(left, right, strict=True):
                compare(before, after, citation=citation)
        else:
            assert left == right

    compare(baseline, actual)
    return asserted


@pytest.mark.parametrize("schema_name", ["classifier", "candidates", "kpi"])
def test_scoped_model_changes_only_identity_and_preserves_financial_values(schema_name):
    manifest = {key: str(uuid4()) for key in ("span", "version", "entity")}
    span_hashes = seeded_span_hashes(manifest)
    request = _request(schema_name)
    baseline = MockStructuredLLMProvider().generate_structured(request)
    actual = ScopedMock(manifest, span_hashes).generate_structured(request)
    asserted = _changed_only_identity_and_asserted_hash(
        baseline.parsed, actual.parsed, manifest, span_hashes
    )
    # Only proposal envelopes cite evidence; classifier sections and fact-table
    # candidates name spans but are not citations and stay unchanged.
    assert asserted == ([manifest["span"]] if schema_name == "kpi" else [])
    assert actual.input_tokens == baseline.input_tokens
    assert actual.output_tokens == baseline.output_tokens
    assert actual.estimated_cost_usd == baseline.estimated_cost_usd


@pytest.mark.parametrize("tamper", ["value", "wrong_hash", "extra_key"])
def test_scoped_model_comparison_still_fails_on_any_other_change(tamper):
    manifest = {key: str(uuid4()) for key in ("span", "version", "entity")}
    span_hashes = seeded_span_hashes(manifest)
    baseline = MockStructuredLLMProvider().generate_structured(_request("kpi"))
    actual = ScopedMock(manifest, span_hashes).generate_structured(_request("kpi"))
    proposal = actual.parsed["proposals"][0]
    if tamper == "value":
        proposal["value"] = str(int(proposal["value"]) + 1)
    elif tamper == "wrong_hash":
        proposal["evidence"][0]["text_hash"] = "sha256:" + "0" * 64
    else:
        proposal["evidence"][0]["citation_status"] = "verified"
    with pytest.raises(AssertionError):
        _changed_only_identity_and_asserted_hash(
            baseline.parsed, actual.parsed, manifest, span_hashes
        )


def test_scoped_model_refuses_to_assert_a_hash_for_an_unseeded_span():
    manifest = {key: str(uuid4()) for key in ("span", "version", "entity")}
    with pytest.raises(KeyError):
        ScopedMock(manifest, {str(uuid4()): DIGEST}).generate_structured(_request("kpi"))


@pytest.fixture
def acceptance_database(monkeypatch, tmp_path):
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        if os.environ.get("FEL_REQUIRE_DB") == "1":
            pytest.fail("FEL_REQUIRE_DB=1 requires TEST_DATABASE_URL for acceptance regression")
        pytest.skip("TEST_DATABASE_URL not configured")
    name = "fel_extraction_acceptance_" + uuid4().hex
    parsed = urlsplit(base)
    url = urlunsplit(parsed._replace(path="/" + name))
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        assert migrate(["--database-url", url]) == 0
        monkeypatch.setenv("FEL_DATABASE_URL", url)
        monkeypatch.setenv("FEL_STORAGE_DIR", str(tmp_path / "storage"))
        monkeypatch.setenv("FEL_DEPLOYMENT_MODE", "synthetic-http")
        monkeypatch.setenv("FEL_SYNTHETIC_HTTP_TARGET", "extraction-cross-stack-tests")
        monkeypatch.delenv("PGHOSTADDR", raising=False)
        monkeypatch.delenv("PGSERVICE", raising=False)
        monkeypatch.setenv("FEL_AUTH_MODE", "mock")
        monkeypatch.setenv("FEL_ALLOW_MOCK_LLM", "1")
        monkeypatch.setenv("FEL_WORKER_DB_ROLE", "fel_worker")
        yield url
    finally:
        pool_for(url).close()
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_harness_seeds_source_runs_worker_and_verifies_real_immutable_rows(
    acceptance_database, monkeypatch, tmp_path
):
    """Exercise harness internals with PG; separate Playwright uses real sockets."""
    manifest_path = tmp_path / "manifest.json"

    def command(action, *args):
        monkeypatch.setattr(
            sys, "argv", ["acceptance", action, "--manifest", str(manifest_path), *args]
        )
        main()

    command("seed")
    manifest = json.loads(manifest_path.read_text())
    headers = {
        "Authorization": f"Bearer {make_mock_token(manifest['org'], manifest['user'], 'owner')}",
    }
    client = TestClient(app)
    created = client.post(
        f"/v1/workspaces/{manifest['workspace']}/extraction-runs",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "entity_id": manifest["entity"],
            "modes": ["kpi"],
            "source_span_ids": [manifest["span"]],
            "corpus_version_id": manifest["corpus"],
            "as_of": "2026-12-31T00:00:00Z",
        },
    )
    assert created.status_code == 202, created.text
    run = created.json()["id"]
    command("work")
    with pytest.raises(RuntimeError, match="exactly one successfully processed"):
        command("work")
    # The worker graded the citation itself: the proposal asserted the seeded
    # span's text_hash, so it is reviewable without anything review supplies.
    with psycopg.connect(acceptance_database) as conn:
        assert conn.execute(
            "SELECT e.source_span_id::text,e.citation_status FROM extraction_proposal_evidence e "
            "JOIN extraction_proposals p ON p.id=e.proposal_id WHERE p.run_id=%s",
            (run,),
        ).fetchall() == [(manifest["span"], "verified")]
    proposals = client.get(f"/v1/workspaces/{manifest['workspace']}/extractions", headers=headers)
    assert proposals.status_code == 200, proposals.text
    assert len(proposals.json()["items"]) == 1
    proposal = proposals.json()["items"][0]
    result = client.post(
        "/v1/extractions/review",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "action": "accept",
            "extraction_ids": [proposal["id"]],
            "expected_versions": {proposal["id"]: proposal["version"]},
            "reason": "Canonical evidence verified",
        },
    )
    assert result.status_code == 200, result.text
    record = result.json()["approved_record_ids"][0]
    with psycopg.connect(acceptance_database) as conn:
        approved = conn.execute(
            "SELECT evidence_manifest FROM approved_extraction_versions WHERE record_id=%s",
            (record,),
        ).fetchone()[0]
    assert [(edge["source_span_id"], edge["citation_status"]) for edge in approved] == [
        (manifest["span"], "verified")
    ]
    with pytest.raises(RuntimeError, match="one immutable correction"):
        verify(acceptance_database, manifest, run, record)
    old = client.get(f"/v1/approved-extractions/{record}", headers=headers)
    corrected = client.post(
        f"/v1/approved-extractions/{record}/corrections",
        headers={**headers, "Idempotency-Key": str(uuid4()), "If-Match": old.headers["etag"]},
        json={
            "reason": "Second review of pinned evidence",
            "payload": old.json()["payload"],
            "evidence": old.json()["evidence"],
        },
    )
    assert corrected.status_code == 201, corrected.text
    command("verify", "--run", run, "--record", record)
    previous = client.get(
        f"/v1/approved-extractions/{record}/versions/{old.json()['version_id']}",
        headers=headers,
    )
    assert previous.json() == old.json()
    with pytest.raises(RuntimeError, match="actual source span"):
        verify(acceptance_database, {**manifest, "span": str(uuid4())}, run, record)

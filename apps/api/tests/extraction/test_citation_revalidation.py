"""Revalidation cannot verify a citation the proposal never asserted (database-free).

Rows are built by the worker's own validators, so they carry exactly what a
worker run persists: the payload with its evidence assertions, the graded
citation edges and the validation summary. Only the canonical byte read is
faked; the pin checks and every deterministic rule are the production ones.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.extraction import evidence, validation
from fel_ontology import load_saas_metrics
from fel_providers.interfaces import StructuredGenerationRequest
from fel_providers.mocks import MockStructuredLLMProvider
from fel_workers.extraction.hashing import hash_json, sha256_hex
from fel_workers.extraction.normalize.pipeline import normalize_payload
from fel_workers.extraction.types import WORKFLOW_VERSION
from fel_workers.extraction.validate.pipeline import validate_proposals
from fel_workers.extraction.validate.schema import WORKER_EXTENSION_KEYS

WORKER_BLOCKER = "no verified citation: no cited span asserts a matching text_hash"
TEXT = "Annual recurring revenue was $100 million at June 30, 2026."


@pytest.fixture
def scope(monkeypatch):
    ids = {name: str(uuid4()) for name in ("run", "entity", "span", "version", "corpus", "policy")}
    block = {
        "source_span_id": ids["span"],
        "document_version_id": ids["version"],
        "text": TEXT,
        "text_hash": sha256_hex(TEXT),
        "published_at": "2026-02-01T00:00:00+00:00",
    }
    manifest = {
        "evidence": [{key: value for key, value in block.items() if key != "text"}],
        "conflict_occurrence_policy": "run/v1",
    }
    run = {
        "entity_id": ids["entity"],
        "corpus_version_id": ids["corpus"],
        "policy_id": ids["policy"],
        "as_of": datetime(2026, 6, 30, tzinfo=UTC),
        "workflow_version": WORKFLOW_VERSION,
        "ontology_version": load_saas_metrics().schema_version,
        "input_manifest": manifest,
        "input_hash": hash_json(manifest),
    }
    monkeypatch.setattr(
        evidence, "verify_spans", lambda conn, spans, *pinned: [block] if spans else []
    )
    return {**ids, "block": block, "runs": {ids["run"]: run}}


def _worker_row(scope, citation):
    """The committed mock reply, validated and graded as the worker persists it."""
    reply = MockStructuredLLMProvider().generate_structured(
        StructuredGenerationRequest(
            messages=[{"role": "user", "content": "Synthetic evidence"}],
            json_schema={},
            schema_name="kpi",
            schema_version="test/v1",
            max_output_tokens=1000,
        )
    )
    edge = {
        "source_span_id": scope["span"],
        "document_version_id": scope["version"],
        "role": "supports",
    }
    cited = {
        "string_form": [scope["span"]],
        "without_text_hash": [edge],
        "matching_text_hash": [{**edge, "text_hash": scope["block"]["text_hash"]}],
    }[citation]
    payload = {**reply.parsed["proposals"][0], "entity_id": scope["entity"], "evidence": cited}
    normalized, blockers = normalize_payload(payload)
    assert not blockers
    draft = validate_proposals(
        run_id=scope["run"],
        payloads=[normalized],
        evidence_by_span={scope["span"]: scope["block"]},
    ).proposals[0]
    return {
        "id": "source-row",
        "run_id": scope["run"],
        "payload": draft.payload,
        "evidence": [
            {key: edge[key] for key in ("source_span_id", "document_version_id", "role")}
            | {"citation_status": edge["citation_status"]}
            for edge in draft.evidence
        ],
        "validation_summary": draft.validation_summary,
    }


def _revalidated(scope, row):
    return validation.evaluate(None, [row], scope["runs"]).drafts[row["id"]]


@pytest.mark.parametrize("summary", ["persisted", "lost"])
@pytest.mark.parametrize("citation", ["string_form", "without_text_hash"])
def test_membership_only_citation_stays_blocked(scope, citation, summary):
    row = _worker_row(scope, citation)
    assert row["validation_summary"]["blockers"] == [WORKER_BLOCKER]
    assert [edge["citation_status"] for edge in row["evidence"]] == ["partial"]
    if summary == "lost":
        row["validation_summary"] = {}
    draft = _revalidated(scope, row)
    assert WORKER_BLOCKER in draft.validation_summary["blockers"], draft.validation_summary
    assert draft.validation_summary["ok"] is False
    assert [edge["citation_status"] for edge in draft.evidence] == ["partial"]


def test_asserted_matching_hash_remains_acceptable(scope):
    row = _worker_row(scope, "matching_text_hash")
    assert row["validation_summary"]["blockers"] == []
    assert [edge["citation_status"] for edge in row["evidence"]] == ["verified"]
    draft = _revalidated(scope, row)
    assert draft.validation_summary == {**draft.validation_summary, "ok": True, "blockers": []}
    assert [edge["citation_status"] for edge in draft.evidence] == ["verified"]


def test_persisted_citation_blocker_is_not_repaired_by_a_verified_grade(scope):
    row = _worker_row(scope, "without_text_hash")
    row["evidence"] = [{**edge, "citation_status": "verified"} for edge in row["evidence"]]
    draft = _revalidated(scope, row)
    assert WORKER_BLOCKER in draft.validation_summary["blockers"], draft.validation_summary


@pytest.mark.parametrize("grade,blocked", [("verified", False), ("partial", True)])
def test_current_approved_head_keeps_its_manifest_grade(scope, grade, blocked):
    row = _worker_row(scope, "matching_text_hash")
    row["payload"] = {k: v for k, v in row["payload"].items() if k not in WORKER_EXTENSION_KEYS}
    row["evidence"] = [{**edge, "citation_status": grade} for edge in row["evidence"]]
    row["validation_summary"] = {}
    draft = _revalidated(scope, row)
    assert (WORKER_BLOCKER in draft.validation_summary["blockers"]) is blocked
    assert [edge["citation_status"] for edge in draft.evidence] == [grade]


def test_reviewer_replacement_is_validated_on_its_own_terms(scope):
    row = _worker_row(scope, "without_text_hash")
    row["payload"] = {k: v for k, v in row["payload"].items() if k not in WORKER_EXTENSION_KEYS}
    row["evidence"] = [{**edge, "citation_status": "invalid"} for edge in row["evidence"]]
    row["validation_summary"] = {}
    row["reviewer_evidence"] = True
    draft = _revalidated(scope, row)
    assert draft.validation_summary["blockers"] == []
    assert [edge["citation_status"] for edge in draft.evidence] == ["verified"]

"""Restore checkpoint outputs to extraction workflow state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fel_workers.extraction.errors import CutoffViolation, IntegrityError
from fel_workers.extraction.hashing import sha256_hex
from fel_workers.extraction.types import MODE_STAGES, EvidenceBlock, WorkflowState
from fel_workers.extraction.validate import validate_proposals


def _utc_aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _assert_restored_cutoff(span_id: str, published_at: datetime | None, as_of: datetime) -> None:
    """Fail closed when restored evidence has no cutoff-verifiable publication time."""
    if published_at is None:
        raise CutoffViolation(
            f"restored evidence for span {span_id} is missing published_at "
            "and cannot be verified against the run's as_of cutoff"
        )
    if _utc_aware(published_at) > _utc_aware(as_of):
        raise CutoffViolation(
            f"restored evidence for span {span_id} has published_at "
            f"{published_at.isoformat()} after the run's as_of cutoff {as_of.isoformat()}"
        )


def _restore_output(state: WorkflowState, step_name: str, output: Any) -> None:
    if output is None:
        return
    if step_name == "assemble_evidence" and isinstance(output, list):
        restored: list[EvidenceBlock] = []
        for block in output:
            if isinstance(block, EvidenceBlock):
                if sha256_hex(block.text) != block.text_hash:
                    raise IntegrityError(
                        f"restored evidence for span {block.source_span_id} does not "
                        "match its checkpointed text_hash"
                    )
                _assert_restored_cutoff(
                    block.source_span_id, block.published_at, state.request.as_of
                )
                restored.append(block)
                continue
            if not isinstance(block, dict):
                continue
            span_id = str(block["source_span_id"])
            text = str(block.get("text") or "")
            text_hash = str(block["text_hash"])
            if sha256_hex(text) != text_hash:
                # Fail closed: re-extracting from altered text under the original
                # hash would emit proposals whose citations do not describe them.
                raise IntegrityError(
                    f"restored evidence for span {span_id} does not "
                    "match its checkpointed text_hash"
                )
            published = block.get("published_at")
            published_at: datetime | None = None
            if isinstance(published, datetime):
                published_at = published
            elif isinstance(published, str) and published:
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise CutoffViolation(
                        f"restored evidence for span {span_id} has unparseable "
                        f"published_at {published!r}"
                    ) from exc
            _assert_restored_cutoff(span_id, published_at, state.request.as_of)
            restored.append(
                EvidenceBlock(
                    source_span_id=span_id,
                    document_version_id=str(block["document_version_id"]),
                    text=text,
                    text_hash=text_hash,
                    published_at=published_at,
                )
            )
        state.evidence = restored
    elif step_name == "classify" and isinstance(output, dict):
        state.classification = output
    elif step_name == "collect_candidates" and isinstance(output, dict):
        state.candidates = list(output.get("candidates") or [])
    elif step_name in MODE_STAGES.values() and isinstance(output, dict):
        proposals = output.get("proposals") or []
        if isinstance(proposals, list):
            state.raw_proposals.extend(proposals)
    elif step_name == "normalize" and isinstance(output, dict):
        state.normalized = list(output.get("normalized") or [])
    elif step_name == "validate" and isinstance(output, dict):
        state.normalized = list(output.get("normalized") or state.normalized)
        # Rebuild drafts so resume after validate does not lose proposals.
        rebuilt = validate_proposals(
            run_id=state.request.run_id,
            payloads=state.normalized,
            evidence_by_span=dict(evidence_map(state.evidence)),
        )
        state.validated = rebuilt.proposals
        state.conflicts = rebuilt.conflicts
    elif step_name == "detect_conflicts" and isinstance(output, dict):
        if not state.validated and state.normalized:
            rebuilt = validate_proposals(
                run_id=state.request.run_id,
                payloads=state.normalized,
                evidence_by_span=dict(evidence_map(state.evidence)),
            )
            state.validated = rebuilt.proposals
            state.conflicts = rebuilt.conflicts


def evidence_map(blocks: list[EvidenceBlock]) -> Mapping[str, dict[str, Any]]:
    return {
        b.source_span_id: {
            "document_version_id": b.document_version_id,
            "text": b.text,
            "text_hash": b.text_hash,
        }
        for b in blocks
    }

"""Run-level error text is redacted before it is stored or emitted (#412).

``run_extraction_workflow`` persists ``state.error`` on the run row and in the
``run_failed``/``run_cancelled`` event payload on three paths: cancellation, a
typed failure, and an untyped internal error. Each must pass through
``redact_error_text`` while keeping the code callers rely on.
"""

from __future__ import annotations

from typing import Any

import pytest

from fel_providers.mocks import MockStructuredLLMProvider
from fel_workers.extraction import workflow
from fel_workers.extraction.errors import Cancelled, StepFailed
from fel_workers.extraction.events import MemoryEventStore
from fel_workers.extraction.handler import _evidence_from_payload, request_from_payload
from fel_workers.extraction.persist import MemoryPersistStore
from fel_workers.extraction.types import WorkflowState
from fel_workers.extraction.workflow import WorkflowDeps, run_extraction_workflow

from .conftest import sample_payload

_DSN = "postgres://svc:FAKE-DB-PASSWORD-412@db.internal.invalid:5432/fel"
_LEAKY = f"boom {_DSN} Authorization: Token FAKE-TOKEN-412"
_SECRETS = ("FAKE-DB-PASSWORD-412", "FAKE-TOKEN-412")


class _RecordingPersist(MemoryPersistStore):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[dict[str, Any]] = []

    def set_run_status(self, **kwargs: Any) -> None:
        self.errors.append(dict(kwargs.get("error") or {}))
        super().set_run_status(**kwargs)


def _run(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> tuple[WorkflowState, _RecordingPersist, MemoryEventStore, BaseException | None]:
    payload = sample_payload(modes=["kpi"])
    request = request_from_payload(payload)
    evidence = _evidence_from_payload(payload)
    events = MemoryEventStore()
    persist = _RecordingPersist()
    deps = WorkflowDeps(
        structured_llm=MockStructuredLLMProvider(),
        events=events,
        persist=persist,
        evidence_loader=lambda _r: list(evidence),
    )
    state = WorkflowState(request=request, evidence=list(evidence))

    def _boom(_ctx: Any) -> None:
        raise exc

    monkeypatch.setattr(workflow, "_boundary", _boom)
    raised: BaseException | None = None
    try:
        run_extraction_workflow(state, deps)
    except BaseException as caught:  # the internal path re-raises by design
        raised = caught
    return state, persist, events, raised


@pytest.mark.parametrize(
    ("exc", "event_type", "code", "status"),
    [
        (Cancelled(_LEAKY), "run_cancelled", "cancelled", "cancelled"),
        (StepFailed(_LEAKY), "run_failed", "step_failed", "failed"),
        (RuntimeError(_LEAKY), "run_failed", "internal_error", "failed"),
    ],
    ids=["cancel", "typed-failure", "internal"],
)
def test_run_error_is_redacted_on_every_terminal_path(
    monkeypatch: pytest.MonkeyPatch,
    exc: BaseException,
    event_type: str,
    code: str,
    status: str,
) -> None:
    state, persist, events, _raised = _run(monkeypatch, exc)

    assert state.status == status
    assert state.error is not None
    assert state.error["code"] == code
    stored = [state.error, *persist.errors]
    emitted = [e.payload for e in events.events if e.event_type == event_type]
    assert persist.errors and emitted
    for record in [*stored, *emitted]:
        for secret in _SECRETS:
            assert secret not in str(record)
        assert "db.internal.invalid" not in str(record)

"""Smoke test for the API health contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.auth import TenantContext
from app.dependencies import get_tenant_context
from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "fel-api"
    assert body["version"] == __version__


def test_validation_error_omits_raw_input() -> None:
    sentinel = "FIXTURE-SENSITIVE-INPUT-SENTINEL"
    fake_ctx = TenantContext(
        org_id="00000000-0000-0000-0000-000000000001",
        user_id="00000000-0000-0000-0000-000000000002",
        role="viewer",
    )
    app.dependency_overrides[get_tenant_context] = lambda: fake_ctx
    try:
        response = client.get(f"/v1/extraction-runs/{sentinel}")
    finally:
        app.dependency_overrides.pop(get_tenant_context, None)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
    assert body["error"]["details"]
    for item in body["error"]["details"]:
        assert "input" not in item
    assert sentinel not in response.text

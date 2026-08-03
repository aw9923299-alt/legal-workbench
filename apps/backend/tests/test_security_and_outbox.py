from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from legal_workbench.api.dependencies import get_actor_id
from legal_workbench.config import Settings, get_settings
from legal_workbench.domain.entities import AuditEvent, AuthenticatedActorId
from legal_workbench.infrastructure.outbox import ClaimedOutboxEvent, OutboxDispatcher


@pytest.mark.asyncio
async def test_unknown_outbox_event_is_not_acknowledged() -> None:
    dispatcher = object.__new__(OutboxDispatcher)
    event = ClaimedOutboxEvent(
        id=uuid4(),
        event_type="UnknownEvent",
        aggregate_type="test",
        aggregate_id=uuid4(),
        payload={},
        correlation_id="corr-unknown",
        attempts=0,
    )

    with pytest.raises(RuntimeError, match="UNSUPPORTED_OUTBOX_EVENT"):
        await dispatcher._dispatch(event)


def test_real_feishu_requires_verification_configuration() -> None:
    with pytest.raises(ValidationError, match="verification"):
        Settings(
            enable_real_feishu=True,
            feishu_event_source="webhook",
            feishu_verification_token=None,
            feishu_encrypt_key=None,
            _env_file=None,
        )


def test_encrypt_key_alone_does_not_replace_webhook_verification_token() -> None:
    with pytest.raises(ValidationError, match="verification token"):
        Settings(
            enable_real_feishu=True,
            feishu_event_source="webhook",
            feishu_verification_token=None,
            feishu_encrypt_key="configured-but-not-implemented",
            _env_file=None,
        )


def test_production_rejects_actor_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEGAL_WORKBENCH_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "LEGAL_WORKBENCH_SESSION_SECRET", "test-production-secret-at-least-32-chars"
    )
    monkeypatch.setenv("LEGAL_WORKBENCH_ALLOW_DEVELOPMENT_ACTOR_HEADER", "false")
    get_settings.cache_clear()
    test_app = FastAPI()

    @test_app.get("/protected")
    async def protected(actor_id: str = Depends(get_actor_id)) -> dict[str, str]:
        return {"actorId": actor_id}

    try:
        response = TestClient(test_app).get(
            "/protected", headers={"X-Actor-ID": "browser-controlled-user"}
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 401


def test_local_session_endpoint_sets_httponly_cookie() -> None:
    from legal_workbench.main import app

    response = TestClient(app).post("/api/v1/auth/local-session")

    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["actorId"] == "local-legal-user"
    assert response.json()["identitySource"] == "local_session"


def test_local_supervisor_session_uses_dedicated_machine_identity() -> None:
    from legal_workbench.main import app

    response = TestClient(app).post("/api/v1/auth/local-supervisor-session")

    assert response.status_code == 201
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json() == {
        "actorId": "mac-supervisor",
        "identitySource": "local_supervisor",
    }


def test_local_session_is_fail_closed_for_staging(monkeypatch: pytest.MonkeyPatch) -> None:
    from legal_workbench.main import app

    monkeypatch.setenv("LEGAL_WORKBENCH_ENVIRONMENT", "staging")
    monkeypatch.setenv(
        "LEGAL_WORKBENCH_SESSION_SECRET", "staging-test-secret-at-least-32-chars"
    )
    get_settings.cache_clear()
    try:
        response = TestClient(app).post("/api/v1/auth/local-session")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="environment"):
        Settings(environment="prod", _env_file=None)  # type: ignore[arg-type]


def test_optional_codex_sandbox_ids_can_be_omitted() -> None:
    settings = Settings(
        codex_sandbox_uid="",  # type: ignore[arg-type]
        codex_sandbox_gid="",  # type: ignore[arg-type]
        _env_file=None,
    )

    assert settings.codex_sandbox_uid is None
    assert settings.codex_sandbox_gid is None


@pytest.mark.parametrize("secret", ["", "short", "development-only-change-me"])
def test_non_local_environment_rejects_weak_session_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(environment="staging", session_secret=secret, _env_file=None)


def test_audit_event_records_authenticated_identity_source() -> None:
    event = AuditEvent(
        id=uuid4(),
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="test",
        actor_id=AuthenticatedActorId("local-user", identity_source="local_session"),
        payload={},
        correlation_id="corr-auth",
    )

    assert event.actor_source == "local_session"


def test_business_api_requires_authenticated_session() -> None:
    from legal_workbench.main import app

    response = TestClient(app).get("/api/v1/agent-runs")

    assert response.status_code == 401


def test_feishu_webhook_is_disabled_when_real_integration_is_off() -> None:
    from legal_workbench.main import app

    response = TestClient(app).post(
        "/api/v1/integrations/feishu/events",
        json={
            "schema": "2.0",
            "header": {
                "event_id": "evt-forged",
                "event_type": "im.message.receive_v1",
            },
        },
    )

    assert response.status_code == 503


def test_feishu_webhook_rejects_invalid_verification_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from legal_workbench.main import app

    monkeypatch.setenv("LEGAL_WORKBENCH_ENABLE_REAL_FEISHU", "true")
    monkeypatch.setenv("LEGAL_WORKBENCH_FEISHU_EVENT_SOURCE", "webhook")
    monkeypatch.setenv("LEGAL_WORKBENCH_FEISHU_VERIFICATION_TOKEN", "expected-token")
    get_settings.cache_clear()
    try:
        response = TestClient(app).post(
            "/api/v1/integrations/feishu/events",
            json={
                "schema": "2.0",
                "header": {
                    "event_id": "evt-forged",
                    "event_type": "im.message.receive_v1",
                    "token": "wrong-token",
                },
            },
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 403


def test_message_analysis_api_contracts_are_registered() -> None:
    from legal_workbench.main import app

    paths = app.openapi()["paths"]

    assert "/api/v1/agent-runs" in paths
    assert "/api/v1/agent-runs/{run_id}" in paths
    assert "/api/v1/feishu/messages/{message_id}/analyse" in paths
    assert "/api/v1/feishu/messages/{message_id}/retry-analysis" in paths
    assert "/api/v1/feishu/messages/{message_id}/analysis" in paths
    assert "/api/v1/integrations/feishu/status" in paths
    assert "/api/v1/integrations/feishu/reconnect" in paths
    assert "/api/v1/integrations/feishu/reconcile" in paths
    assert "/api/v1/system/health" in paths
    assert "/api/v1/system/metrics" in paths
    assert "/api/v1/system/recover-pending-jobs" in paths
    assert "/api/v1/events/stream" in paths
    assert "/api/v1/feishu/messages" in paths
    assert "/api/v1/feishu/messages/{message_id}" in paths
    assert "/api/v1/agent-runs/{run_id}/retry" in paths
    assert "/api/v1/agent-runs/{run_id}/cancel" in paths


def test_agent_runtime_output_masks_common_secret_formats() -> None:
    from legal_workbench.api.routes.agents import _redact_runtime_text

    value = _redact_runtime_text(
        "Authorization: Bearer sensitive-token API_KEY=secret-value sk-abcdefghijklmnop"
    )

    assert value is not None
    assert "sensitive-token" not in value
    assert "secret-value" not in value
    assert "sk-abcdefghijklmnop" not in value
    assert value.count("[REDACTED]") == 3


def test_outbox_requeue_requires_idempotency_key() -> None:
    from legal_workbench.main import app

    with TestClient(app) as client:
        assert client.post("/api/v1/auth/local-session").status_code == 201
        response = client.post(
            f"/api/v1/system/outbox/dead-letters/{uuid4()}/requeue"
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Idempotency-Key header is required."

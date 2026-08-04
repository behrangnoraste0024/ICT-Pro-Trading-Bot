from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.live_control_plane_routes import get_live_execution_permit_status_service
from api.live_execution_permit_status_service import LiveExecutionPermitStatusService
from api.main import create_app
from infrastructure.persistence.live_execution_permit_persistence import LiveExecutionPermitPersistenceError
from models.live_execution_authorization import LiveExecutionOperation
from models.live_execution_permit import PERMIT_ENVIRONMENT, PERMIT_SYMBOL, LiveExecutionPermitState


PERMIT_ID = "permit-00000000000000000000000000000001"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakePermitPersistence:
    instances: list["FakePermitPersistence"] = []
    permit = None
    effective_expired = False
    error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[str] = []
        FakePermitPersistence.instances.append(self)

    def ensure_available(self) -> None:
        self.calls.append("ensure_available")
        if isinstance(self.error, LiveExecutionPermitPersistenceError) and self.error.code == "PERMIT_UNAVAILABLE":
            raise self.error

    def show(self, permit_id: str):
        self.calls.append(f"show:{permit_id}")
        if self.error is not None and not (
            isinstance(self.error, LiveExecutionPermitPersistenceError) and self.error.code == "PERMIT_UNAVAILABLE"
        ):
            raise self.error
        return self.permit, self.effective_expired

    def close(self) -> None:
        self.calls.append("close")

    def issue(self, *args, **kwargs):
        self.calls.append("issue")
        raise AssertionError("status endpoint must not issue permits")

    def consume(self, *args, **kwargs):
        self.calls.append("consume")
        raise AssertionError("status endpoint must not consume permits")

    def revoke(self, *args, **kwargs):
        self.calls.append("revoke")
        raise AssertionError("status endpoint must not revoke permits")

    def expire(self, *args, **kwargs):
        self.calls.append("expire")
        raise AssertionError("status endpoint must not persist expiration")

    def commit(self, *args, **kwargs):
        self.calls.append("commit")
        raise AssertionError("status endpoint must not commit")

    def flush(self, *args, **kwargs):
        self.calls.append("flush")
        raise AssertionError("status endpoint must not flush")

    def rollback(self, *args, **kwargs):
        self.calls.append("rollback")
        raise AssertionError("status endpoint must not rollback as business behavior")


class RaisingFactory:
    called = False

    def __call__(self, *args, **kwargs):
        self.called = True
        raise AssertionError("invalid permit id must fail before persistence access")


@pytest.fixture(autouse=True)
def reset_fake_persistence() -> None:
    FakePermitPersistence.instances = []
    FakePermitPersistence.permit = None
    FakePermitPersistence.effective_expired = False
    FakePermitPersistence.error = None


def _permit(**overrides):
    values = {
        "permit_id": PERMIT_ID,
        "operation": LiveExecutionOperation.PROTECTIVE_CREATE,
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "state": LiveExecutionPermitState.ISSUED,
        "issued_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "consumed_at": None,
        "revoked_at": None,
        "revocation_reason_code": None,
        "updated_at": NOW,
        "version": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client_with_service(service: LiveExecutionPermitStatusService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_live_execution_permit_status_service] = lambda: service
    return TestClient(app)


def _fake_client() -> TestClient:
    return _client_with_service(LiveExecutionPermitStatusService(persistence_factory=FakePermitPersistence))


def _body_text(response) -> str:
    return json.dumps(response.json())


def test_route_is_registered_as_get_only() -> None:
    client = _fake_client()

    paths = client.get("/openapi.json").json()["paths"]

    assert paths["/api/v1/live/execution-permits/{permit_id}"].keys() == {"get"}
    path = f"/api/v1/live/execution-permits/{PERMIT_ID}"
    for method in (client.post, client.put, client.patch, client.delete):
        assert method(path).status_code == 405


def test_issued_permit_future_expiration_returns_required_fields_without_mutation() -> None:
    FakePermitPersistence.permit = _permit()
    client = _fake_client()

    response = client.get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 200
    assert response.json() == {
        "permit_id": PERMIT_ID,
        "operation": "PROTECTIVE_CREATE",
        "environment": PERMIT_ENVIRONMENT,
        "symbol": PERMIT_SYMBOL,
        "state": "ISSUED",
        "effective_expired": False,
        "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        "issued_at": NOW.isoformat(),
        "consumed_at": None,
        "revoked_at": None,
        "revocation_reason": None,
        "version": 1,
        "updated_at": NOW.isoformat(),
    }
    assert FakePermitPersistence.instances[0].calls == ["ensure_available", f"show:{PERMIT_ID}", "close"]


def test_issued_permit_past_expiration_is_derived_read_only() -> None:
    FakePermitPersistence.permit = _permit(expires_at=NOW - timedelta(seconds=1))
    FakePermitPersistence.effective_expired = True
    client = _fake_client()

    response = client.get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 200
    assert response.json()["state"] == "EXPIRED"
    assert response.json()["effective_expired"] is True
    assert FakePermitPersistence.instances[0].calls == ["ensure_available", f"show:{PERMIT_ID}", "close"]


def test_consumed_and_revoked_permits_are_not_reclassified_after_expiration() -> None:
    for state, timestamp_field, reason in (
        (LiveExecutionPermitState.CONSUMED, "consumed_at", None),
        (LiveExecutionPermitState.REVOKED, "revoked_at", "OPERATOR_REQUESTED"),
    ):
        FakePermitPersistence.instances = []
        FakePermitPersistence.permit = _permit(
            state=state,
            expires_at=NOW - timedelta(minutes=1),
            **{timestamp_field: NOW + timedelta(seconds=1)},
            revocation_reason_code=reason,
        )
        FakePermitPersistence.effective_expired = True

        response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

        assert response.status_code == 200
        assert response.json()["state"] == state.value


def test_persisted_expired_permit_reports_effective_expired() -> None:
    FakePermitPersistence.permit = _permit(
        state=LiveExecutionPermitState.EXPIRED,
        expires_at=NOW - timedelta(seconds=1),
    )

    response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 200
    assert response.json()["state"] == "EXPIRED"
    assert response.json()["effective_expired"] is True


@pytest.mark.parametrize("bad_id", ["   ", "permit-abc", "permit-" + "0" * 33, "permit-0000000000000000000000000000000%0A"])
def test_invalid_permit_id_fails_before_persistence_access_and_is_sanitized(bad_id: str) -> None:
    factory = RaisingFactory()
    client = _client_with_service(LiveExecutionPermitStatusService(persistence_factory=factory))

    response = client.get(f"/api/v1/live/execution-permits/{bad_id}")

    assert response.status_code == 400
    assert response.json()["detail"] == {"code": "INVALID_PERMIT_ID", "message": "Permit identifier is invalid.", "details": {}}
    assert factory.called is False
    stripped = bad_id.strip()
    if stripped:
        assert stripped not in _body_text(response)


def test_empty_permit_id_is_rejected_by_service_before_persistence_access() -> None:
    factory = RaisingFactory()
    service = LiveExecutionPermitStatusService(persistence_factory=factory)

    with pytest.raises(Exception) as exc:
        service.status("")

    assert getattr(exc.value, "status_code") == 400
    assert getattr(exc.value, "code") == "INVALID_PERMIT_ID"
    assert factory.called is False


def test_missing_permit_returns_sanitized_404() -> None:
    client = _fake_client()

    response = client.get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "PERMIT_NOT_FOUND", "message": "Live execution permit was not found.", "details": {}}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", "PRODUCTION"),
        ("symbol", "ETHUSDT"),
    ],
)
def test_valid_but_unsupported_scope_returns_sanitized_403(field: str, value: str) -> None:
    FakePermitPersistence.permit = _permit(**{field: value})

    response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "PERMIT_SCOPE_FORBIDDEN"
    assert value not in _body_text(response)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("environment", None),
        ("environment", "TESTNET\nrawResponse"),
        ("symbol", None),
        ("symbol", "BTCUSDT\napiSecret"),
        ("state", "ACTIVE"),
        ("state", None),
        ("operation", "DELETE_ALL"),
        ("expires_at", "2026-01-01"),
        ("issued_at", None),
        ("updated_at", "traceback"),
        ("version", 0),
        ("version", True),
        ("revocation_reason_code", "rawResponse"),
    ],
)
def test_malformed_persisted_record_fails_closed_without_leaking_value(field: str, value) -> None:
    overrides = {
        "state": LiveExecutionPermitState.REVOKED if field == "revocation_reason_code" else LiveExecutionPermitState.ISSUED,
        "revoked_at": NOW if field == "revocation_reason_code" else None,
    }
    overrides[field] = value
    FakePermitPersistence.permit = _permit(**overrides)

    response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "PERMIT_STATUS_UNAVAILABLE",
        "message": "Live execution permit status is unavailable.",
        "details": {},
    }
    body = _body_text(response).lower()
    for marker in ("rawresponse", "apisecret", "traceback", "delete_all"):
        assert marker not in body
    assert FakePermitPersistence.instances[0].calls == ["ensure_available", f"show:{PERMIT_ID}", "close"]


@pytest.mark.parametrize(
    "error",
    [
        LiveExecutionPermitPersistenceError("PERMIT_UNAVAILABLE"),
        RuntimeError("postgresql://user:secret@db rawResponse SELECT * FROM traceback"),
    ],
)
def test_persistence_unavailable_and_provider_exceptions_are_sanitized(error: Exception) -> None:
    FakePermitPersistence.error = error

    response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 503
    body = _body_text(response)
    assert response.json()["detail"]["code"] == "PERMIT_STATUS_UNAVAILABLE"
    for marker in ("postgresql://", "secret", "rawResponse", "SELECT * FROM", "traceback"):
        assert marker not in body


def test_service_uses_show_only_and_does_not_touch_network_or_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePermitPersistence.permit = _permit()
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_KEY", "unit-test-secret-key")
    monkeypatch.setenv("BINANCE_FUTURES_TESTNET_API_SECRET", "unit-test-secret-secret")

    response = _fake_client().get(f"/api/v1/live/execution-permits/{PERMIT_ID}")

    assert response.status_code == 200
    body = _body_text(response)
    assert "unit-test-secret" not in body
    assert "signature" not in body.lower()
    assert "X-MBX-APIKEY" not in body
    assert FakePermitPersistence.instances[0].calls == ["ensure_available", f"show:{PERMIT_ID}", "close"]

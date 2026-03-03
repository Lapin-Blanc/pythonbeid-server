from __future__ import annotations

from fastapi.testclient import TestClient

from eid_agent.app import create_app
from eid_agent.config import Settings
from eid_agent.errors import AgentError


class DummyReaderBackend:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    def status(self) -> dict[str, object]:
        if self.mode == "no_reader":
            return {"has_reader": False, "has_card": False, "readers": []}
        if self.mode == "no_card":
            return {"has_reader": True, "has_card": False, "readers": ["Reader 1"]}
        return {"has_reader": True, "has_card": True, "readers": ["Reader 1"]}

    def read(self, include_photo: bool = False) -> dict[str, object]:
        if self.mode == "no_reader":
            raise AgentError(503, "NO_READER", "No smart card reader detected.")
        if self.mode == "no_card":
            raise AgentError(503, "NO_CARD", "No eID card detected.")
        payload = {
            "first_name": "Ada",
            "first_names": "Ada Augusta",
            "last_name": "Lovelace",
            "birth_date": "1815-12-10",
            "birth_place": "London",
            "national_number": "12345678901",
            "nationality": "British",
            "sex": "F",
            "card_number": "ABC12345",
            "issuing_municipality": "Brussels",
            "validity_start": "2021-06-21",
            "validity_end": "2031-06-21",
            "address_street": "Main Street 1",
            "address_zip": "1000",
            "address_city": "Brussels",
            "photo_base64": "ZmFrZS1waG90bw==" if include_photo else None,
        }
        if include_photo:
            payload["photo_mime"] = "image/jpeg"
        return payload


def build_client(mode: str = "ok", rate_limit: int = 10) -> TestClient:
    settings = Settings(
        port=8765,
        allowed_origins=[],
        session_ttl_seconds=120,
        rate_limit_per_minute=rate_limit,
        log_level="INFO",
        https_enabled=False,
        tls_cert_path=None,
        tls_key_path=None,
    )
    app = create_app(settings=settings, reader_backend=DummyReaderBackend(mode=mode))
    return TestClient(app)


def create_token(client: TestClient) -> str:
    response = client.post("/v1/session")
    assert response.status_code == 200
    payload = response.json()
    return payload["token"]


def test_healthcheck() -> None:
    client = build_client()
    response = client.get("/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["service"] == "eid-agent"
    assert payload["version"] == "1.0.0"


def test_read_requires_token() -> None:
    client = build_client()
    response = client.post("/v1/read", json={})
    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_read_returns_data_with_valid_token() -> None:
    client = build_client()
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["first_name"] == "Ada"
    assert payload["data"]["first_names"] == "Ada Augusta"
    assert payload["data"]["card_number"] == "ABC12345"
    assert payload["data"]["photo_base64"] is None


def test_read_with_photo() -> None:
    client = build_client()
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"include_photo": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["photo_base64"] == "ZmFrZS1waG90bw=="
    assert payload["data"]["photo_mime"] == "image/jpeg"


def test_unknown_field_returns_bad_request() -> None:
    client = build_client()
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"fields": ["first_name", "unknown_field"]},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_invalid_payload_returns_bad_request() -> None:
    client = build_client()
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={"include_photo": "not-a-bool"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == "BAD_REQUEST"


def test_rate_limit() -> None:
    client = build_client(rate_limit=1)
    token = create_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/v1/read", headers=headers, json={})
    second = client.post("/v1/read", headers=headers, json={})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_read_returns_no_reader() -> None:
    client = build_client(mode="no_reader")
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NO_READER"


def test_read_returns_no_card() -> None:
    client = build_client(mode="no_card")
    token = create_token(client)
    response = client.post(
        "/v1/read",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NO_CARD"


def test_logout_invalidates_token() -> None:
    client = build_client()
    token = create_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = client.post("/v1/logout", headers=headers)
    assert logout_response.status_code == 200

    read_after_logout = client.post("/v1/read", headers=headers, json={})
    assert read_after_logout.status_code == 401
    assert read_after_logout.json()["error"]["code"] == "UNAUTHORIZED"

"""Register confirm pack line API tests."""

from __future__ import annotations

import importlib
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

AUTH_ENV = {
    "OIDC_ISSUER": "https://auth.example.com/application/o/scanner/",
    "OIDC_CLIENT_ID": "scanner-bff-test",
    "OIDC_CLIENT_SECRET": "test-client-secret",
    "SCANNER_SESSION_SECRET": "test-session-secret-32-chars-minimum!",
    "ELAB_INTEGRATION_LIVE": "false",
}

MOCK_OIDC_METADATA = {
    "authorization_endpoint": "https://auth.example.com/o/authorize/",
    "end_session_endpoint": "https://auth.example.com/o/end-session/",
    "token_endpoint": "https://auth.example.com/o/token/",
    "userinfo_endpoint": "https://auth.example.com/o/userinfo/",
}


def _prime_oidc_metadata(auth_module) -> None:
    auth_module._metadata = dict(MOCK_OIDC_METADATA)


@pytest.fixture
def authed_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    web_dist = os.environ.get("SCANNER_WEB_DIR", "")
    for key, value in AUTH_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("SCANNER_ALLOW_DEV_LOGIN", "true")
    monkeypatch.setenv("SCANNER_SESSION_HTTPS_ONLY", "false")
    if web_dist:
        monkeypatch.setenv("SCANNER_WEB_DIR", web_dist)

    import inventory_scanner.app as app_module
    import inventory_scanner.auth as auth_module

    importlib.reload(auth_module)
    _prime_oidc_metadata(auth_module)
    importlib.reload(app_module)

    client = TestClient(app_module.create_app())
    client.get("/auth/dev-login", follow_redirects=True)
    yield client


def _valid_payload(**overrides) -> dict:
    payload = {
        "manufacturer": "Test",
        "catalogue_number": "T1",
        "product_name": "Probe",
        "category_id": 25,
        "storage_id": 4,
        "lines": [{"amount_per_container": 300, "unit": "ml"}],
    }
    payload.update(overrides)
    return payload


def test_register_confirm_valid_lines_still_gated_403(authed_client: TestClient) -> None:
    r = authed_client.post("/api/register/confirm", json=_valid_payload())
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/json")


def test_register_confirm_rejects_missing_lines_400(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/api/register/confirm",
        json=_valid_payload(lines=[]),
    )
    assert r.status_code == 400
    assert "container line" in r.json()["detail"].lower()


def test_register_confirm_rejects_empty_unit_400(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/api/register/confirm",
        json=_valid_payload(lines=[{"amount_per_container": 1, "unit": ""}]),
    )
    assert r.status_code == 400
    assert "Unit required" in r.json()["detail"] or "unit" in r.json()["detail"].lower()


def test_register_confirm_two_lines_one_container_each_403(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/api/register/confirm",
        json=_valid_payload(
            lines=[
                {"amount_per_container": 300, "unit": "ml"},
                {"amount_per_container": 50, "unit": "g"},
            ]
        ),
    )
    assert r.status_code == 403

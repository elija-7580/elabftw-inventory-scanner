"""Server-side authentication enforcement tests."""

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
def auth_client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    web_dist = os.environ.get("SCANNER_WEB_DIR", "")
    for key, value in AUTH_ENV.items():
        monkeypatch.setenv(key, value)
    if web_dist:
        monkeypatch.setenv("SCANNER_WEB_DIR", web_dist)
    monkeypatch.delenv("SCANNER_ALLOW_DEV_LOGIN", raising=False)
    monkeypatch.setenv("SCANNER_SESSION_HTTPS_ONLY", "false")

    import inventory_scanner.app as app_module
    import inventory_scanner.auth as auth_module

    importlib.reload(auth_module)
    _prime_oidc_metadata(auth_module)
    importlib.reload(app_module)

    client = TestClient(app_module.create_app())
    yield client


@pytest.fixture
def auth_client_dev(monkeypatch) -> Iterator[TestClient]:
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
    yield client


@pytest.fixture
def authed_client(auth_client_dev: TestClient) -> TestClient:
    r = auth_client_dev.get("/auth/dev-login", follow_redirects=True)
    assert r.status_code == 200
    return auth_client_dev


def test_unauthenticated_root_redirects_to_login(auth_client: TestClient) -> None:
    r = auth_client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/auth/login")


def test_unauthenticated_index_redirects_to_login(auth_client: TestClient) -> None:
    r = auth_client.get("/index.html", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]


def test_unauthenticated_lookup_api_returns_401(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/api/register/lookup",
        json={
            "manufacturer": "Test",
            "catalogue_number": "T1",
            "product_name": "Probe",
        },
    )
    assert r.status_code == 401


def test_unauthenticated_mutation_returns_401_before_write_gate(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/api/register/confirm",
        json={
            "manufacturer": "Test",
            "catalogue_number": "T1",
            "product_name": "Probe",
        },
    )
    assert r.status_code == 401


def test_authenticated_can_load_scanner_page(authed_client: TestClient) -> None:
    r = authed_client.get("/", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "Start scanner" in r.text


def test_authenticated_api_allowed(authed_client: TestClient) -> None:
    r = authed_client.post("/api/scan/parse", json={"raw_value": "4006381333931"})
    assert r.status_code == 200
    assert r.json()["raw"] == "4006381333931"


def test_authenticated_mutation_still_gated_403(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/api/register/confirm",
        json={
            "manufacturer": "Test",
            "catalogue_number": "T1",
            "product_name": "Probe",
            "category_id": 25,
            "storage_id": 4,
            "lines": [
                {"amount_per_container": 50, "unit": "ml"},
                {"amount_per_container": 25, "unit": "g"},
            ],
        },
    )
    assert r.status_code == 403


def test_authenticated_confirm_rejects_missing_category(authed_client: TestClient) -> None:
    r = authed_client.post(
        "/api/register/confirm",
        json={
            "manufacturer": "Test",
            "catalogue_number": "T1",
            "product_name": "Probe",
            "storage_id": 4,
        },
    )
    assert r.status_code == 400
    assert "category_id" in r.json()["detail"]


def test_unauthenticated_api_returns_json_not_redirect(auth_client: TestClient) -> None:
    r = auth_client.get(
        "/api/inventory/options",
        headers={"Accept": "text/html,application/xhtml+xml"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["detail"] == "Authentication required"


def test_expired_session_cannot_access_app(auth_client_dev: TestClient) -> None:
    auth_client_dev.get("/auth/dev-login", follow_redirects=False)
    auth_client_dev.cookies.clear()
    r = auth_client_dev.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302


def test_logout_invalidates_access(authed_client: TestClient) -> None:
    r = authed_client.get("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    assert "scanner_session" not in r.cookies or r.cookies.get("scanner_session") == ""
    r2 = authed_client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r2.status_code == 302
    assert "/auth/login" in r2.headers["location"]


def test_logout_redirects_to_oidc_end_session(auth_client_dev: TestClient) -> None:
    auth_client_dev.get("/auth/dev-login", follow_redirects=False)
    r = auth_client_dev.get("/auth/logout", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith("https://auth.example.com/o/end-session/")
    assert "post_logout_redirect_uri=" in location
    assert "prompt%3Dlogin" in location or "prompt=login" in location
    assert "client_id=scanner-bff-test" in location


def test_login_forces_reauth_when_prompt_login(auth_client: TestClient) -> None:
    r = auth_client.get("/auth/login?prompt=login", follow_redirects=False)
    assert r.status_code == 302
    assert "prompt=login" in r.headers["location"]


def test_forged_cookie_rejected(auth_client: TestClient) -> None:
    auth_client.cookies.set("scanner_session", "forged.invalid.cookie")
    r = auth_client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]


def test_callback_rejects_missing_code(auth_client: TestClient) -> None:
    r = auth_client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 400


def test_callback_rejects_invalid_state(auth_client: TestClient) -> None:
    r = auth_client.get(
        "/auth/callback?code=fake-code&state=wrong-state",
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_health_public_no_secrets(auth_client: TestClient) -> None:
    r = auth_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "commit" in body
    assert "secret" not in r.text.lower()
    assert "password" not in r.text.lower()


def test_session_endpoint_requires_auth(auth_client: TestClient) -> None:
    r = auth_client.get("/auth/session")
    assert r.status_code == 401


def test_static_bundle_is_public(auth_client: TestClient) -> None:
    import json
    from pathlib import Path

    web = Path(os.environ["SCANNER_WEB_DIR"])
    manifest = json.loads((web / "build-manifest.json").read_text(encoding="utf-8"))
    r = auth_client.get(manifest["bundle"])
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "")


def test_public_config_without_auth(auth_client: TestClient) -> None:
    r = auth_client.get("/api/config/public")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "writes_enabled" in r.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalog/lookup",
        "/api/catalog/save",
        "/api/catalog/stats",
        "/api/catalog/import/preview",
        "/api/catalog/import/commit",
        "/api/catalog/import/error-report",
    ],
)
def test_catalog_apis_require_auth(auth_client: TestClient, path: str) -> None:
    if path.endswith("/stats"):
        r = auth_client.get(path)
    elif "import" in path:
        r = auth_client.post(
            path,
            files={"file": ("t.csv", b"Product,Barcode\nA,1\n", "text/csv")},
        )
    else:
        r = auth_client.post(path, json={"code": "X", "confirm": True})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json")


def test_catalog_import_ui_requires_auth(auth_client: TestClient) -> None:
    r = auth_client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/auth/login" in r.headers["location"]


def test_authenticated_catalog_lookup_allowed(authed_client: TestClient) -> None:
    r = authed_client.post("/api/catalog/lookup", json={"code": "MISSING"})
    assert r.status_code == 200
    assert r.json()["status"] == "no_match"

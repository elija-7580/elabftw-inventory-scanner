"""Route and static asset tests for scanner BFF."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from inventory_scanner.app import _web, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_web_dist_exists() -> None:
    assert _web.is_dir(), f"missing web dist at {_web}"
    assert (_web / "index.html").is_file()
    assert (_web / "build-manifest.json").is_file()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "commit" in body


def test_root_serves_index(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Inventory Scanner for eLabFTW" in r.text


def test_index_html_explicit(client: TestClient) -> None:
    r = client.get("/index.html")
    assert r.status_code == 200
    assert "Register new product" in r.text
    assert "eLabFTW" in r.text
    assert "Inventory" in r.text
    assert "Read-only test mode" in r.text


def test_public_config(client: TestClient) -> None:
    r = client.get("/api/config/public")
    assert r.status_code == 200
    body = r.json()
    assert body["modes"] == ["register", "manage"]
    assert "elab_public_url" in body


def test_oidc_login_not_configured(client: TestClient) -> None:
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503


def test_oidc_callback_rejects_missing_code(client: TestClient) -> None:
    r = client.get("/auth/callback", follow_redirects=False)
    assert r.status_code == 400


def test_container_route_registered(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]
    assert "/api/container/{container_id}" in paths


def test_index_references_bundled_scanner(client: TestClient) -> None:
    manifest = json.loads((_web / "build-manifest.json").read_text(encoding="utf-8"))
    r = client.get("/")
    assert r.status_code == 200
    text = r.text
    assert "Start scanner" in text
    assert manifest["bundle"] in text
    assert 'type="importmap"' not in text


def test_scanner_prefix_simulation(client: TestClient) -> None:
    """Caddy handle_path strips /scanner — backend sees bare paths."""
    for path in ("/", "/health", "/index.html", "/api/config/public"):
        assert client.get(path).status_code in (200, 400, 503)

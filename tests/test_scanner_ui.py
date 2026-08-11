"""Scanner UI wiring tests — no camera hardware required."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from inventory_scanner.app import _web, app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _bundle_path() -> str:
    manifest = _web / "build-manifest.json"
    assert manifest.is_file(), "run scripts/build_web.sh first"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data["bundle"]


def test_no_import_map(client: TestClient) -> None:
    r = client.get("/")
    assert 'type="importmap"' not in r.text


def test_no_camera_scanner_global_in_html(client: TestClient) -> None:
    html = (_web / "index.html").read_text(encoding="utf-8")
    assert "CameraScanner" not in html
    assert "new CameraScanner" not in html


def test_no_camera_scanner_global_in_bundle() -> None:
    bundle = _web / _bundle_path().lstrip("/")
    text = bundle.read_text(encoding="utf-8")
    assert "window.CameraScanner" not in text


def test_bundled_asset_exists_and_served(client: TestClient) -> None:
    path = _bundle_path()
    assert (_web / path.lstrip("/")).is_file()
    r = client.get(path)
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "")


def test_bundle_has_no_bare_imports() -> None:
    bundle = (_web / _bundle_path().lstrip("/")).read_text(encoding="utf-8")
    assert re.search(r'from\s+["\']@[^"\']+["\']', bundle) is None
    assert re.search(r'import\s*\(\s*["\']@[^"\']+["\']', bundle) is None


def test_bundle_no_runtime_cdn() -> None:
    bundle = (_web / _bundle_path().lstrip("/")).read_text(encoding="utf-8")
    for token in ("cdn.jsdelivr", "unpkg.com", "esm.sh", "skypack"):
        assert token not in bundle


def test_scanner_api_base_uses_scanner_prefix() -> None:
    html = (_web / "index.html").read_text(encoding="utf-8")
    assert 'data-scanner-api-base="/scanner"' in html
    src = (_web.parent / "src" / "scanner-app.js").read_text(encoding="utf-8")
    assert "scannerApiBase" in src
    assert 'fetch("/api/' not in src
    assert 'fetch(`/api/' not in src


def test_inventory_options_route_on_bff() -> None:
    """Caddy strips /scanner; BFF sees bare /api/inventory/options."""
    client = TestClient(app)
    r = client.get("/api/inventory/options")
    assert r.status_code in (200, 502)


def test_html_references_same_commit_bundle(client: TestClient) -> None:
    manifest = json.loads((_web / "build-manifest.json").read_text(encoding="utf-8"))
    r = client.get("/")
    assert manifest["bundle"] in r.text


def test_scan_app_does_not_auto_mutate() -> None:
    src = (_web.parent / "src" / "scanner-app.js").read_text(encoding="utf-8")
    onresult = src.split("onResult:", 1)[1].split("},", 1)[0]
    assert "fetch" not in onresult
    assert "reg-confirm" not in onresult
    assert "mgr-apply" not in onresult
    assert "input.value" in onresult


def test_scanner_controls_present(client: TestClient) -> None:
    r = client.get("/index.html")
    text = r.text
    for token in (
        "Start scanner",
        "Stop",
        "reg-scan-detected",
        "scanner-retry",
        "Camera inactive",
        "Hold the code inside the frame.",
        "readonly-bar",
    ):
        assert token in text


def test_html_cache_control(client: TestClient) -> None:
    r = client.get("/")
    assert "no-cache" in r.headers.get("cache-control", "")


def test_bundle_cache_control(client: TestClient) -> None:
    r = client.get(_bundle_path())
    assert "immutable" in r.headers.get("cache-control", "")


def test_mutation_endpoints_still_gated(client: TestClient) -> None:
    reg = client.post(
        "/api/register/confirm",
        json={
            "manufacturer": "Test",
            "catalogue_number": "T1",
            "product_name": "Probe",
            "category_id": 25,
            "storage_id": 4,
            "lines": [{"amount_per_container": 100, "unit": "g"}],
        },
    )
    assert reg.status_code == 403
    assert "ELAB_INTEGRATION_LIVE" in reg.text
    action = client.post(
        "/api/container/1/action",
        json={"operation": "consume", "qty": 1},
    )
    assert action.status_code == 403

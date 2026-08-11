"""Inventory options API tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from inventory_scanner.app import app


def test_inventory_options_returns_locations_and_categories() -> None:
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.get.side_effect = [
        [
            {"id": 3, "name": "Building", "full_path": "Building", "parent_id": None, "children": []},
            {
                "id": 4,
                "name": "Unassigned Location",
                "full_path": "Building > Unassigned Location",
                "parent_id": 3,
                "children": [],
            },
        ],
        [{"id": 25, "title": "Untitled", "color": "29aeb9"}, {"id": 99, "title": "Junk", "color": "000000"}],
    ]
    with patch("inventory_scanner.app._client", return_value=mock_client):
        r = client.get("/api/inventory/options")
    assert r.status_code == 200
    body = r.json()
    assert body["default_storage_id"] == 4
    assert len(body["locations"]) == 2
    assert len(body["categories"]) == 1
    assert body["categories"][0]["title"] == "Chemical Product"


def test_inventory_options_falls_back_to_inline_categories() -> None:
    client = TestClient(app)
    mock_client = MagicMock()
    mock_client.get.side_effect = [
        [{"id": 4, "name": "Unassigned Location", "full_path": "Lab > Unassigned", "children": []}],
        [{"id": 99, "title": "Other", "color": "000000"}],
    ]
    with patch("inventory_scanner.app._client", return_value=mock_client):
        r = client.get("/api/inventory/options")
    assert r.status_code == 200
    body = r.json()
    assert len(body["categories"]) == 8
    assert body["categories"][0]["id"] == 24
    assert body["categories"][0]["title"] == "Pure Chemical"


def test_public_config_exposes_writes_flag() -> None:
    client = TestClient(app)
    r = client.get("/api/config/public")
    assert r.status_code == 200
    assert "writes_enabled" in r.json()
    assert r.json()["beta"] is True

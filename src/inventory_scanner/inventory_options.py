"""Load eLabFTW inventory pickers (locations, categories)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .elab_client import ElabApiClient
from .inventory_validation import ALLOWED_CATEGORY_IDS, POC_CATEGORY_LABELS


def _poc_category_labels() -> dict[int, str]:
    labels = dict(POC_CATEGORY_LABELS)
    manifest = Path(__file__).resolve().parents[2] / "poc_manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for cat in data.get("categories", []):
            labels[int(cat["id"])] = str(cat["name"])
    return labels


def flatten_locations(nodes: list[dict[str, Any]], *, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        out.append(
            {
                "id": int(node["id"]),
                "name": node.get("name") or "",
                "full_path": node.get("full_path") or node.get("name") or "",
                "parent_id": node.get("parent_id"),
                "depth": depth,
            }
        )
        children = node.get("children") or []
        if isinstance(children, list) and children:
            out.extend(flatten_locations(children, depth=depth + 1))
    return out


def load_inventory_options(client: ElabApiClient, *, team_id: int = 1) -> dict[str, Any]:
    labels = _poc_category_labels()
    hierarchy = client.get("/storage_units", hierarchy=True)
    locations = flatten_locations(hierarchy if isinstance(hierarchy, list) else [])
    default_storage_id = 4
    for loc in locations:
        if loc["name"] == "Unassigned Location":
            default_storage_id = loc["id"]
            break

    raw_categories = client.get(f"/teams/{team_id}/resources_categories")
    categories: list[dict[str, Any]] = []
    for cat in raw_categories if isinstance(raw_categories, list) else []:
        cid = int(cat["id"])
        if cid not in ALLOWED_CATEGORY_IDS:
            continue
        title = str(cat.get("title") or "").strip()
        if not title or title.lower() == "untitled":
            title = labels[cid]
        categories.append({"id": cid, "title": title, "color": cat.get("color")})
    categories.sort(key=lambda c: c["id"])
    if not categories:
        categories = [
            {"id": cid, "title": labels[cid], "color": None} for cid in sorted(ALLOWED_CATEGORY_IDS)
        ]

    return {
        "locations": locations,
        "categories": categories,
        "default_storage_id": default_storage_id,
        "default_category_id": 25,
        "pack_units": ["g", "mg", "µg", "kg", "ml", "µl", "L", "pcs"],
        "units": ["g", "mg", "µg", "kg", "ml", "µl", "L", "pcs"],
    }

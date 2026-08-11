"""Server-side eLabFTW API client (BFF only — never expose key to browser)."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from .extra_fields import inventory_item_fields


class ElabApiClient:
    def __init__(self, base_url: str, api_key: str, *, verify_ssl: bool = True) -> None:
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": api_key, "Content-Type": "application/json"}
        self.verify = verify_ssl

    @classmethod
    def from_env(cls) -> "ElabApiClient":
        base = os.environ.get("ELABFTW_API_URL") or os.environ.get("ELAB_API_URL", "")
        key = os.environ.get("ELABFTW_API_KEY") or os.environ.get("ELAB_API_KEY", "")
        if not base or not key:
            raise RuntimeError("ELABFTW API credentials not configured")
        verify = os.environ.get("ELAB_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
        return cls(base, key, verify_ssl=verify)

    def get(self, path: str, **params: Any) -> Any:
        r = requests.get(f"{self.base}{path}", headers=self.headers, params=params, timeout=120, verify=self.verify)
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, body: dict[str, Any]) -> None:
        r = requests.patch(f"{self.base}{path}", headers=self.headers, json=body, timeout=120, verify=self.verify)
        if r.status_code not in (200, 204):
            raise RuntimeError(f"PATCH {path}: {r.status_code} {r.text[:300]}")

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(f"{self.base}{path}", headers=self.headers, json=body, timeout=120, verify=self.verify)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"POST {path}: {r.status_code} {r.text[:300]}")
        if r.text.strip():
            try:
                return r.json()
            except json.JSONDecodeError:
                pass
        loc = r.headers.get("Location", "")
        out: dict[str, Any] = {}
        if loc:
            out["id"] = int(loc.rstrip("/").split("/")[-1])
            out["location"] = loc
        return out

    def get_item(self, item_id: int) -> dict[str, Any]:
        return self.get(f"/items/{item_id}")

    def get_container(self, item_id: int, container_id: int) -> dict[str, Any]:
        return self.get(f"/items/{item_id}/containers/{container_id}")

    def list_item_containers(self, item_id: int) -> list[dict[str, Any]]:
        return self.get(f"/items/{item_id}/containers")

    def find_container_by_id(self, container_id: int) -> dict[str, Any] | None:
        """Resolve container by paginating items (falls back to legacy POC range)."""
        offset = 0
        limit = 100
        while offset < 2000:
            batch = self.get("/items", limit=limit, offset=offset)
            if not isinstance(batch, list) or not batch:
                break
            for row in batch:
                iid = int(row["id"])
                try:
                    for c in self.list_item_containers(iid):
                        if int(c["id"]) == container_id:
                            return {"container": c, "item": self.get_item(iid)}
                except Exception:
                    continue
            if len(batch) < limit:
                break
            offset += limit
        for iid in range(230, 240):
            try:
                for c in self.list_item_containers(iid):
                    if int(c["id"]) == container_id:
                        item = self.get_item(iid)
                        return {"container": c, "item": item}
            except Exception:
                continue
        return None

    def create_item(
        self,
        title: str,
        category_id: int,
        manufacturer: str,
        catalogue_number: str,
        original_barcode: str = "",
        body: str = "",
        lot_batch: str = "",
        expiry_date: str = "",
    ) -> int:
        meta = {
            "extra_fields": inventory_item_fields(
                manufacturer=manufacturer,
                catalogue_number=catalogue_number,
                original_barcode=original_barcode,
                lot_batch=lot_batch,
                expiry_date=expiry_date,
            ),
            "elabftw": {"source": "inventory-scanner"},
        }
        res = self.post(
            "/items",
            {"title": title, "category": category_id, "body": body, "metadata": meta},
        )
        return int(res["id"])

    def create_container(self, item_id: int, storage_id: int, qty: float, unit: str) -> int:
        self.post(f"/items/{item_id}/containers/{storage_id}", {"qty_stored": qty, "qty_unit": unit})
        containers = self.list_item_containers(item_id)
        return int(containers[-1]["id"])

    def update_container_qty(self, item_id: int, container_id: int, qty: float, unit: str) -> None:
        self.patch(f"/items/{item_id}/containers/{container_id}", {"qty_stored": qty, "qty_unit": unit})

    def update_item_metadata(self, item_id: int, metadata: dict[str, Any]) -> None:
        self.patch(f"/items/{item_id}", {"metadata": metadata})

    def link_compound(self, item_id: int, compound_id: int) -> None:
        self.post(f"/items/{item_id}/compounds_links/{compound_id}", {})

    def container_qr_url(self, container_id: int, public_base: str) -> str:
        return f"{public_base.rstrip('/')}/scanner/container/{container_id}"

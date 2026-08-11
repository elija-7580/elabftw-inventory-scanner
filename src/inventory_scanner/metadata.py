"""Parse and merge eLabFTW item metadata without data loss."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


def parse_metadata(raw: Any) -> dict[str, Any]:
    """Return metadata as a dict with optional extra_fields and elabftw keys."""
    if raw is None:
        return {"extra_fields": {}, "elabftw": {}}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"extra_fields": {}, "elabftw": {}}
        return normalize_metadata(parsed)
    if isinstance(raw, dict):
        return normalize_metadata(deepcopy(raw))
    return {"extra_fields": {}, "elabftw": {}}


def normalize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Move misplaced extra_fields from elabftw.* to top-level extra_fields."""
    out = deepcopy(meta)
    elabftw = out.setdefault("elabftw", {})
    if not isinstance(elabftw, dict):
        elabftw = {}
        out["elabftw"] = elabftw

    nested = elabftw.pop("extra_fields", None)
    top = out.setdefault("extra_fields", {})
    if not isinstance(top, dict):
        top = {}
        out["extra_fields"] = top

    if isinstance(nested, dict):
        for key, field in nested.items():
            if key not in top:
                top[key] = field

    if not isinstance(out.get("extra_fields"), dict):
        out["extra_fields"] = {}
    if not isinstance(out.get("elabftw"), dict):
        out["elabftw"] = {}

    return out


def metadata_to_api_payload(meta: dict[str, Any]) -> str:
    """Serialize metadata for PATCH (eLabFTW expects JSON string on update)."""
    return json.dumps(normalize_metadata(meta), ensure_ascii=False)


def merge_metadata(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge patch into existing metadata; patch wins on field conflicts."""
    base = normalize_metadata(existing)
    upd = normalize_metadata(patch)

    for key, value in upd.get("elabftw", {}).items():
        base.setdefault("elabftw", {})[key] = value

    for key, value in upd.get("extra_fields", {}).items():
        base.setdefault("extra_fields", {})[key] = value

    return base

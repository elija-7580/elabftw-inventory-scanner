"""Validate inventory IDs before any eLab write."""

from __future__ import annotations

from fastapi import HTTPException

POC_CATEGORY_LABELS: dict[int, str] = {
    24: "Pure Chemical",
    25: "Chemical Product",
    26: "Commercial Mixture",
    27: "Prepared Solution",
    28: "Buffer",
    29: "Growth Medium",
    30: "Standard",
    31: "General Laboratory Consumable",
}

ALLOWED_CATEGORY_IDS = frozenset(POC_CATEGORY_LABELS)


def validate_category_id(category_id: int | None) -> int:
    if category_id is None:
        raise HTTPException(400, "category_id is required")
    if category_id not in ALLOWED_CATEGORY_IDS:
        raise HTTPException(
            400,
            f"Invalid category_id {category_id}; allowed: {sorted(ALLOWED_CATEGORY_IDS)}",
        )
    return category_id


def validate_storage_id(storage_id: int | None) -> int:
    if storage_id is None:
        raise HTTPException(400, "storage_id is required")
    if storage_id <= 0:
        raise HTTPException(400, "storage_id must be a positive integer")
    return storage_id

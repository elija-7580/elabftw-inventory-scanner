"""Canonical eLabFTW rendered extra-field serializer (items/resources)."""

from __future__ import annotations

from typing import Any, Literal

ExtraFieldType = Literal["text", "date", "number", "select", "url"]

ALLOWED_TYPES: set[str] = {"text", "date", "number", "select", "url"}

# Rendered inventory fields (UI-visible on items)
INVENTORY_RENDERED_FIELDS = (
    "Manufacturer",
    "Catalogue Number",
    "Original Barcode",
    "Lot/Batch Number",
    "Expiry Date",
)

# Machine-only keys stored under metadata.elabftw (not rendered as extra fields)
MACHINE_KEYS = frozenset({"poc_tag", "source", "scanner_version", "idempotency_key"})


def text_field(value: str, *, description: str = "") -> dict[str, Any]:
    field: dict[str, Any] = {"type": "text", "value": str(value)}
    if description:
        field["description"] = description
    return field


def date_field(value: str, *, description: str = "") -> dict[str, Any]:
    field: dict[str, Any] = {"type": "date", "value": str(value)}
    if description:
        field["description"] = description
    return field


def validate_field(name: str, field: dict[str, Any]) -> None:
    if not isinstance(field, dict):
        raise ValueError(f"{name}: field must be a dict")
    ftype = field.get("type")
    if ftype not in ALLOWED_TYPES:
        raise ValueError(f"{name}: invalid type {ftype!r}")
    if "value" not in field:
        raise ValueError(f"{name}: missing value")
    if ftype == "select" and not field.get("options"):
        raise ValueError(f"{name}: select field requires options")


def inventory_item_fields(
    *,
    manufacturer: str = "",
    catalogue_number: str = "",
    original_barcode: str = "",
    lot_batch: str = "",
    expiry_date: str = "",
) -> dict[str, dict[str, Any]]:
    """Build rendered extra_fields for an inventory Item (top-level metadata.extra_fields)."""
    fields: dict[str, dict[str, Any]] = {
        "Manufacturer": text_field(manufacturer, description="Product manufacturer"),
        "Catalogue Number": text_field(catalogue_number, description="Supplier catalogue / product number"),
        "Original Barcode": text_field(original_barcode, description="Scanned manufacturer barcode or raw code"),
    }
    if lot_batch:
        fields["Lot/Batch Number"] = text_field(lot_batch, description="Physical lot or batch (container-level copy)")
    if expiry_date:
        fields["Expiry Date"] = date_field(expiry_date, description="Expiry date (container-level copy)")
    for name, field in fields.items():
        validate_field(name, field)
    return fields


def extract_legacy_poc_fields(meta: dict[str, Any]) -> dict[str, str]:
    """Read values from normalized metadata or legacy nested elabftw.extra_fields."""
    from .metadata import normalize_metadata

    m = normalize_metadata(meta)
    ef = m.get("extra_fields") or {}
    elab_nested = (m.get("elabftw") or {}).get("extra_fields") or {}

    def val(key: str, *aliases: str) -> str:
        for k in (key, *aliases):
            for source in (ef, elab_nested):
                f = source.get(k) or {}
                if isinstance(f, dict) and f.get("value") not in (None, ""):
                    return str(f["value"])
        return ""

    return {
        "manufacturer": val("Manufacturer"),
        "catalogue_number": val("Catalogue Number", "Catalogue Number"),
        "original_barcode": val("Original Barcode", "Manufacturer Barcode"),
        "lot_batch": val("Lot/Batch Number"),
        "expiry_date": val("Expiry Date"),
        "poc_tag": val("POC Tag"),
    }


def build_corrected_item_metadata(
    existing_meta: dict[str, Any],
    *,
    manufacturer: str | None = None,
    catalogue_number: str | None = None,
    original_barcode: str | None = None,
    lot_batch: str | None = None,
    expiry_date: str | None = None,
    poc_tag: str | None = None,
) -> dict[str, Any]:
    """Produce corrected metadata dict (not yet serialized)."""
    from .metadata import normalize_metadata

    meta = normalize_metadata(existing_meta)
    legacy = extract_legacy_poc_fields(meta)

    rendered = inventory_item_fields(
        manufacturer=manufacturer if manufacturer is not None else legacy["manufacturer"],
        catalogue_number=catalogue_number if catalogue_number is not None else legacy["catalogue_number"],
        original_barcode=original_barcode if original_barcode is not None else legacy["original_barcode"],
        lot_batch=lot_batch if lot_batch is not None else legacy["lot_batch"],
        expiry_date=expiry_date if expiry_date is not None else legacy["expiry_date"],
    )

    meta["extra_fields"] = rendered
    elabftw = meta.setdefault("elabftw", {})
    elabftw.pop("extra_fields", None)
    tag = poc_tag if poc_tag is not None else legacy.get("poc_tag") or ""
    if tag:
        elabftw["poc_tag"] = tag
    elabftw.setdefault("source", "inventory-scanner")
    return meta

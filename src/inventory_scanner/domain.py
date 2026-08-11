"""Typed inventory domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class ConfidenceResult:
    level: ConfidenceLevel
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def writable(self) -> bool:
        return self.level in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM) and self.score >= 0.7


@dataclass
class ProductIdentity:
    manufacturer: str
    catalogue_number: str
    manufacturer_norm: str = ""
    catalogue_norm: str = ""

    def __post_init__(self) -> None:
        self.manufacturer_norm = normalize_text(self.manufacturer)
        self.catalogue_norm = normalize_text(self.catalogue_number)


@dataclass
class ScanResult:
    raw_value: str
    symbology: str
    source: str = "camera"
    gs1_fields: dict[str, str] = field(default_factory=dict)


@dataclass
class ProductCandidate:
    identity: ProductIdentity
    product_name: str = ""
    cas_number: str = ""
    pubchem_cid: str = ""
    gtin: str = ""
    lot: str = ""
    expiry_date: str = ""
    package_qty: str = ""
    package_unit: str = ""
    confidence: ConfidenceResult = field(default_factory=lambda: ConfidenceResult(ConfidenceLevel.NONE, 0.0))
    lookup_source: str = ""


@dataclass
class CompoundCandidate:
    compound_id: int | None = None
    name: str = ""
    cas_number: str = ""
    pubchem_cid: str = ""
    action: str = "reuse"  # reuse | create
    confidence: ConfidenceResult = field(default_factory=lambda: ConfidenceResult(ConfidenceLevel.NONE, 0.0))


@dataclass
class InventoryItem:
    item_id: int | None = None
    title: str = ""
    category_id: int | None = None
    action: str = "reuse"  # reuse | create
    compound_id: int | None = None
    manufacturer: str = ""
    catalogue_number: str = ""
    original_barcode: str = ""


@dataclass
class InventoryContainer:
    container_id: int | None = None
    item_id: int | None = None
    storage_id: int | None = None
    qty_stored: float = 0.0
    qty_unit: str = "g"
    lot: str = ""
    expiry_date: str = ""
    action: str = "create"


@dataclass
class QuantityChange:
    container_id: int
    operation: str  # consume | restock | set_exact | move | mark_empty
    old_qty: float
    new_qty: float
    unit: str
    old_storage_id: int | None = None
    new_storage_id: int | None = None


@dataclass
class AuditEvent:
    timestamp: str
    user_id: str
    user_email: str
    operation: str
    container_id: int
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    idempotency_key: str = ""


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())

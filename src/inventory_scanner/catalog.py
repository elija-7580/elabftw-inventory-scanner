"""Local product catalog (lookup/reference data, separate from eLabFTW records)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_code(raw: str | None) -> str:
    """Normalize scanned codes for exact matching.

    - trim whitespace
    - remove scanner-added line breaks / NULs
    - preserve leading zeroes
    - do not blindly strip punctuation
    """
    if raw is None:
        return ""
    value = str(raw).replace("\r\n", "").replace("\n", "").replace("\r", "").replace("\x00", "")
    return value.strip()


def normalize_identity_part(raw: str | None) -> str:
    """Normalize manufacturer / catalog number for secondary identity matching."""
    if raw is None:
        return ""
    value = str(raw).strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


@dataclass(frozen=True)
class CatalogProduct:
    id: int
    product_name: str
    manufacturer: str
    catalog_number: str
    cas_number: str
    primary_code: str
    alternate_codes: list[str]
    source: str
    source_row: int | None
    category_id: int | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_name": self.product_name,
            "manufacturer": self.manufacturer,
            "catalog_number": self.catalog_number,
            "cas_number": self.cas_number,
            "primary_code": self.primary_code,
            "alternate_codes": list(self.alternate_codes),
            "source": self.source,
            "source_row": self.source_row,
            "category_id": self.category_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProductCatalog:
    """SQLite-backed product catalog sharing the companion ledger DB path."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            # WAL improves concurrent reader/writer behavior for the companion DB.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_name TEXT NOT NULL DEFAULT '',
                    manufacturer TEXT NOT NULL DEFAULT '',
                    catalog_number TEXT NOT NULL DEFAULT '',
                    cas_number TEXT NOT NULL DEFAULT '',
                    primary_code TEXT NOT NULL DEFAULT '',
                    primary_code_norm TEXT NOT NULL DEFAULT '',
                    alternate_codes TEXT NOT NULL DEFAULT '[]',
                    manufacturer_norm TEXT NOT NULL DEFAULT '',
                    catalog_number_norm TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    source_row INTEGER,
                    category_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_product_catalog_primary_norm
                    ON product_catalog(primary_code_norm);
                CREATE INDEX IF NOT EXISTS idx_product_catalog_mfg_cat
                    ON product_catalog(manufacturer_norm, catalog_number_norm);

                CREATE TABLE IF NOT EXISTS product_catalog_codes (
                    code_norm TEXT NOT NULL,
                    product_id INTEGER NOT NULL,
                    is_primary INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (code_norm, product_id),
                    FOREIGN KEY (product_id) REFERENCES product_catalog(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_product_catalog_codes_norm
                    ON product_catalog_codes(code_norm);
                """
            )

    @staticmethod
    def _parse_alternates(raw: Any) -> list[str]:
        if raw is None or raw == "":
            return []
        if isinstance(raw, list):
            return [normalize_code(x) for x in raw if normalize_code(x)]
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [normalize_code(x) for x in parsed if normalize_code(x)]
                except json.JSONDecodeError:
                    pass
            parts = re.split(r"[|;,]", text)
            return [normalize_code(p) for p in parts if normalize_code(p)]
        return [normalize_code(raw)]

    @classmethod
    def _row_to_product(cls, row: sqlite3.Row) -> CatalogProduct:
        return CatalogProduct(
            id=int(row["id"]),
            product_name=str(row["product_name"] or ""),
            manufacturer=str(row["manufacturer"] or ""),
            catalog_number=str(row["catalog_number"] or ""),
            cas_number=str(row["cas_number"] or ""),
            primary_code=str(row["primary_code"] or ""),
            alternate_codes=cls._parse_alternates(row["alternate_codes"]),
            source=str(row["source"] or ""),
            source_row=row["source_row"],
            category_id=row["category_id"],
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )

    def get(self, product_id: int) -> CatalogProduct | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM product_catalog WHERE id=?", (product_id,)
            ).fetchone()
        return self._row_to_product(row) if row else None

    def find_by_code(self, raw_code: str) -> list[CatalogProduct]:
        code = normalize_code(raw_code)
        if not code:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT p.*
                FROM product_catalog p
                JOIN product_catalog_codes c ON c.product_id = p.id
                WHERE c.code_norm = ?
                ORDER BY p.id
                """,
                (code,),
            ).fetchall()
        return [self._row_to_product(r) for r in rows]

    def find_by_manufacturer_catalog(
        self, manufacturer: str, catalog_number: str
    ) -> list[CatalogProduct]:
        mfg = normalize_identity_part(manufacturer)
        cat = normalize_identity_part(catalog_number)
        if not mfg or not cat:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM product_catalog
                WHERE manufacturer_norm=? AND catalog_number_norm=?
                ORDER BY id
                """,
                (mfg, cat),
            ).fetchall()
        return [self._row_to_product(r) for r in rows]

    def lookup(self, *, code: str = "", manufacturer: str = "", catalog_number: str = "") -> dict[str, Any]:
        """Lookup catalog products. Never creates eLab records."""
        raw = code or ""
        norm = normalize_code(raw)
        by_code = self.find_by_code(norm) if norm else []
        by_identity = self.find_by_manufacturer_catalog(manufacturer, catalog_number)

        # Prefer code matches; if both exist and disagree, report conflict.
        matches: list[CatalogProduct] = []
        seen: set[int] = set()
        for product in by_code + by_identity:
            if product.id in seen:
                continue
            seen.add(product.id)
            matches.append(product)

        if not matches:
            return {
                "status": "no_match",
                "raw_code": raw,
                "normalized_code": norm,
                "matches": [],
                "message": "No catalog match — complete manually",
            }
        if len(matches) > 1:
            return {
                "status": "conflict",
                "raw_code": raw,
                "normalized_code": norm,
                "matches": [m.to_dict() for m in matches],
                "message": "Multiple catalog matches — select one or enter manually",
            }
        return {
            "status": "match",
            "raw_code": raw,
            "normalized_code": norm,
            "matches": [matches[0].to_dict()],
            "product": matches[0].to_dict(),
            "message": "Values from local product catalog",
            "source": "local_catalog",
        }

    def _sync_codes(
        self,
        conn: sqlite3.Connection,
        product_id: int,
        primary_code: str,
        alternate_codes: list[str],
    ) -> None:
        conn.execute("DELETE FROM product_catalog_codes WHERE product_id=?", (product_id,))
        primary_norm = normalize_code(primary_code)
        seen: set[str] = set()
        if primary_norm:
            conn.execute(
                """
                INSERT OR IGNORE INTO product_catalog_codes (code_norm, product_id, is_primary)
                VALUES (?, ?, 1)
                """,
                (primary_norm, product_id),
            )
            seen.add(primary_norm)
        for alt in alternate_codes:
            alt_norm = normalize_code(alt)
            if not alt_norm or alt_norm in seen:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO product_catalog_codes (code_norm, product_id, is_primary)
                VALUES (?, ?, 0)
                """,
                (alt_norm, product_id),
            )
            seen.add(alt_norm)

    def insert(
        self,
        *,
        product_name: str = "",
        manufacturer: str = "",
        catalog_number: str = "",
        cas_number: str = "",
        primary_code: str = "",
        alternate_codes: list[str] | None = None,
        source: str = "",
        source_row: int | None = None,
        category_id: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> int:
        alts = self._parse_alternates(alternate_codes or [])
        primary = normalize_code(primary_code)
        # Keep display primary as provided trimmed (preserve leading zeros via normalize_code)
        display_primary = primary
        now = utc_now()
        owns = conn is None
        if owns:
            conn = self._conn()
        assert conn is not None
        try:
            cur = conn.execute(
                """
                INSERT INTO product_catalog (
                    product_name, manufacturer, catalog_number, cas_number,
                    primary_code, primary_code_norm, alternate_codes,
                    manufacturer_norm, catalog_number_norm,
                    source, source_row, category_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (product_name or "").strip(),
                    (manufacturer or "").strip(),
                    (catalog_number or "").strip(),
                    (cas_number or "").strip(),
                    display_primary,
                    primary,
                    json.dumps(alts),
                    normalize_identity_part(manufacturer),
                    normalize_identity_part(catalog_number),
                    source or "",
                    source_row,
                    category_id,
                    now,
                    now,
                ),
            )
            product_id = int(cur.lastrowid)
            self._sync_codes(conn, product_id, display_primary, alts)
            if owns:
                conn.commit()
            return product_id
        finally:
            if owns:
                conn.close()

    def update(
        self,
        product_id: int,
        *,
        product_name: str | None = None,
        manufacturer: str | None = None,
        catalog_number: str | None = None,
        cas_number: str | None = None,
        primary_code: str | None = None,
        alternate_codes: list[str] | None = None,
        source: str | None = None,
        source_row: int | None = None,
        category_id: int | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> CatalogProduct | None:
        existing = self.get(product_id)
        if not existing:
            return None
        name = existing.product_name if product_name is None else product_name.strip()
        mfg = existing.manufacturer if manufacturer is None else manufacturer.strip()
        cat = existing.catalog_number if catalog_number is None else catalog_number.strip()
        cas = existing.cas_number if cas_number is None else cas_number.strip()
        primary = existing.primary_code if primary_code is None else normalize_code(primary_code)
        alts = existing.alternate_codes if alternate_codes is None else self._parse_alternates(alternate_codes)
        src = existing.source if source is None else source
        srow = existing.source_row if source_row is None else source_row
        cat_id = existing.category_id if category_id is None else category_id
        now = utc_now()
        owns = conn is None
        if owns:
            conn = self._conn()
        assert conn is not None
        try:
            conn.execute(
                """
                UPDATE product_catalog SET
                    product_name=?, manufacturer=?, catalog_number=?, cas_number=?,
                    primary_code=?, primary_code_norm=?, alternate_codes=?,
                    manufacturer_norm=?, catalog_number_norm=?,
                    source=?, source_row=?, category_id=?, updated_at=?
                WHERE id=?
                """,
                (
                    name,
                    mfg,
                    cat,
                    cas,
                    primary,
                    primary,
                    json.dumps(alts),
                    normalize_identity_part(mfg),
                    normalize_identity_part(cat),
                    src,
                    srow,
                    cat_id,
                    now,
                    product_id,
                ),
            )
            self._sync_codes(conn, product_id, primary, alts)
            if owns:
                conn.commit()
        finally:
            if owns:
                conn.close()
        return self.get(product_id)

    def save_from_manual(
        self,
        *,
        product_name: str,
        manufacturer: str,
        catalog_number: str,
        cas_number: str = "",
        primary_code: str = "",
        alternate_codes: list[str] | None = None,
        category_id: int | None = None,
    ) -> dict[str, Any]:
        """Explicit operator save of validated metadata into the local catalog."""
        name = (product_name or "").strip()
        mfg = (manufacturer or "").strip()
        cat = (catalog_number or "").strip()
        code = normalize_code(primary_code)
        if not name and not (mfg and cat) and not code:
            raise ValueError("Refusing to save empty catalog metadata")
        if not code and not (mfg and cat):
            raise ValueError("Need a primary code or manufacturer + catalog number")

        if code:
            existing = self.find_by_code(code)
            if len(existing) > 1:
                raise ValueError("Conflicting catalog codes — resolve before saving")
            if len(existing) == 1:
                updated = self.update(
                    existing[0].id,
                    product_name=name or existing[0].product_name,
                    manufacturer=mfg or existing[0].manufacturer,
                    catalog_number=cat or existing[0].catalog_number,
                    cas_number=cas_number.strip() if cas_number else existing[0].cas_number,
                    primary_code=code,
                    alternate_codes=alternate_codes,
                    category_id=category_id,
                    source="manual_save",
                )
                return {"action": "update", "product": updated.to_dict() if updated else None}

        if mfg and cat:
            existing = self.find_by_manufacturer_catalog(mfg, cat)
            if len(existing) > 1:
                raise ValueError("Conflicting manufacturer/catalog entries — resolve before saving")
            if len(existing) == 1:
                updated = self.update(
                    existing[0].id,
                    product_name=name or existing[0].product_name,
                    manufacturer=mfg,
                    catalog_number=cat,
                    cas_number=cas_number.strip() if cas_number else existing[0].cas_number,
                    primary_code=code or existing[0].primary_code,
                    alternate_codes=alternate_codes,
                    category_id=category_id,
                    source="manual_save",
                )
                return {"action": "update", "product": updated.to_dict() if updated else None}

        product_id = self.insert(
            product_name=name,
            manufacturer=mfg,
            catalog_number=cat,
            cas_number=(cas_number or "").strip(),
            primary_code=code,
            alternate_codes=alternate_codes or [],
            source="manual_save",
            category_id=category_id,
        )
        product = self.get(product_id)
        return {"action": "create", "product": product.to_dict() if product else None}

    def count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM product_catalog").fetchone()
        return int(row["n"] if row else 0)

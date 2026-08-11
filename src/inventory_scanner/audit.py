"""Append-only stock transaction ledger (companion DB)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLedger:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stock_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT UNIQUE,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_email TEXT,
                    operation TEXT NOT NULL,
                    container_id INTEGER NOT NULL,
                    item_id INTEGER,
                    old_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    experiment_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS code_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_code TEXT NOT NULL,
                    symbology TEXT,
                    manufacturer TEXT,
                    catalogue_number TEXT,
                    item_id INTEGER,
                    created_at TEXT NOT NULL
                );
                """
            )

    def record(
        self,
        *,
        idempotency_key: str,
        user_id: str,
        user_email: str,
        operation: str,
        container_id: int,
        item_id: int | None,
        old_value: dict[str, Any],
        new_value: dict[str, Any],
        experiment_id: int | None = None,
    ) -> int:
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO stock_transactions
                (idempotency_key, timestamp, user_id, user_email, operation, container_id,
                 item_id, old_value, new_value, experiment_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    ts,
                    user_id,
                    user_email,
                    operation,
                    container_id,
                    item_id,
                    json.dumps(old_value),
                    json.dumps(new_value),
                    experiment_id,
                ),
            )
            return int(cur.lastrowid or 0)

    def get_by_container(self, container_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM stock_transactions WHERE container_id=? ORDER BY id DESC LIMIT ?",
                (container_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

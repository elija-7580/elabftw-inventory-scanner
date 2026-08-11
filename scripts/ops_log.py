#!/usr/bin/env python3
"""Append-only operational JSONL logger (stdlib only)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REDACT_KEY_RE = re.compile(
    r"(token|secret|password|api_key|authorization|cookie|private_key)",
    re.IGNORECASE,
)

DEFAULT_LOG = Path(__file__).resolve().parents[1] / "logs" / "operations.jsonl"


def utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_value(key: str, value: Any) -> Any:
    if isinstance(key, str) and REDACT_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value("", item) for item in value]
    if isinstance(value, str) and REDACT_KEY_RE.search(value):
        return "[REDACTED]"
    return value


def build_record(
    *,
    run_id: str,
    event: str,
    phase: str,
    status: str,
    environment: str,
    commit: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "timestamp": utc_now_z(),
        "run_id": run_id,
        "event": event,
        "phase": phase,
        "status": status,
        "environment": environment,
        "commit": commit,
        "message": message,
    }
    if extra:
        for key, value in extra.items():
            record[key] = redact_value(key, value)
    return record


def emit(record: dict[str, Any], log_path: Path) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    print(line)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch(mode=0o640)
        try:
            os.chmod(log_path, 0o640)
        except OSError:
            pass
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit one operational JSONL record.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--phase", default="general")
    parser.add_argument("--status", required=True)
    parser.add_argument("--environment", default="unknown")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--message", default="")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--extra-json", default="{}", help="JSON object of optional fields")
    args = parser.parse_args()

    try:
        extra = json.loads(args.extra_json)
        if not isinstance(extra, dict):
            raise ValueError("extra-json must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ops_log: invalid extra-json: {exc}", file=sys.stderr)
        return 2

    record = build_record(
        run_id=args.run_id,
        event=args.event,
        phase=args.phase,
        status=args.status,
        environment=args.environment,
        commit=args.commit,
        message=args.message,
        extra=extra,
    )
    emit(record, args.log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

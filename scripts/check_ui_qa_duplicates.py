#!/usr/bin/env python3
"""Fail if any required UI QA screenshots are byte-identical."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AFTER = ROOT / "docs" / "ui-qa" / "after"
REQUIRED = [
    "01-home-mobile.png",
    "02-home-desktop.png",
    "03-scanner-mobile.png",
    "04-register-mobile.png",
    "05-manage-mobile.png",
    "06-catalog-import-mobile.png",
    "07-catalog-import-desktop.png",
    "08-error-state.png",
    "09-no-match-state.png",
    "10-readonly-state.png",
]


def main() -> int:
    hashes: dict[str, str] = {}
    for name in REQUIRED:
        path = AFTER / name
        if not path.is_file():
            print(f"MISSING {name}", file=sys.stderr)
            return 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            print(f"DUPLICATE {hashes[digest]} == {name} sha256={digest}", file=sys.stderr)
            return 1
        hashes[digest] = name
        print(f"{digest}  {name}")
    print("duplicate-check: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

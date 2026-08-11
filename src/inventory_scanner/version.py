"""Build and deployment version metadata (no secrets)."""

from __future__ import annotations

import os


def git_commit() -> str:
    return os.environ.get("SCANNER_GIT_COMMIT", "unknown").strip() or "unknown"

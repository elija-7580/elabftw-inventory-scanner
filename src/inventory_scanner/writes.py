"""Controlled write gate for eLabFTW mutations."""

from __future__ import annotations

import os


def writes_enabled() -> bool:
    return os.environ.get("ELAB_INTEGRATION_LIVE", "").lower() in ("1", "true", "yes")


def require_writes() -> None:
    from fastapi import HTTPException

    if not writes_enabled():
        raise HTTPException(
            403,
            "Live writes disabled. Set ELAB_INTEGRATION_LIVE=true to enable scanner mutations.",
        )

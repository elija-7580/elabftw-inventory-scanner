"""Pure scanner detection logic (mirrored in web/js/scanner-core.js for browser)."""

from __future__ import annotations

import time
from typing import Literal

ScannerBackend = Literal["native", "polyfill", "unavailable"]

# BarcodeDetector format strings (native + polyfill target set).
TARGET_FORMATS: tuple[str, ...] = (
    "code_128",
    "ean_13",
    "ean_8",
    "qr_code",
    "data_matrix",
    "upc_a",
    "upc_e",
)

# Minimum set for reliable laboratory scanning.
REQUIRED_FORMATS: tuple[str, ...] = (
    "code_128",
    "ean_13",
    "qr_code",
    "data_matrix",
)

# Back-compat alias used by earlier tests/docs.
SUPPORTED_FORMATS = TARGET_FORMATS

DEFAULT_DUPLICATE_COOLDOWN_MS = 750
MAX_SCAN_VALUE_LENGTH = 512


def native_covers_required(runtime_formats: list[str] | None) -> bool:
    """True when native BarcodeDetector advertises all required formats."""
    if not runtime_formats:
        return False
    return all(fmt in runtime_formats for fmt in REQUIRED_FORMATS)


def resolve_scanner_backend(
    *,
    has_native: bool,
    native_formats: list[str] | None,
    polyfill_available: bool,
) -> ScannerBackend:
    """Pick decoder backend from runtime capability probes."""
    if has_native and native_covers_required(native_formats):
        return "native"
    if polyfill_available:
        return "polyfill"
    return "unavailable"


def should_suppress_duplicate(
    value: str,
    last_value: str | None,
    last_at_ms: int | None,
    *,
    now_ms: int | None = None,
    cooldown_ms: int = DEFAULT_DUPLICATE_COOLDOWN_MS,
) -> bool:
    """Return True when the same code was seen inside the cooldown window."""
    if not value or not last_value:
        return False
    if value != last_value:
        return False
    if last_at_ms is None:
        return False
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    return (now - last_at_ms) < cooldown_ms


def validate_scan_value(raw_value: str, *, max_length: int = MAX_SCAN_VALUE_LENGTH) -> str:
    """Normalize and validate a decoded value (untrusted plain text)."""
    value = (raw_value or "").strip()
    if not value:
        raise ValueError("empty scan value")
    if len(value) > max_length:
        raise ValueError(f"scan value exceeds {max_length} characters")
    return value


def apply_detected_scan(raw_value: str, symbology: str = "unknown") -> dict[str, str]:
    """Normalize a detection result for UI population."""
    value = validate_scan_value(raw_value)
    return {
        "value": value,
        "symbology": symbology or "unknown",
    }


def unsupported_formats_message(
    supported: list[str],
    runtime_formats: list[str] | None,
) -> str | None:
    """Return user-visible message when runtime lacks target formats."""
    if runtime_formats is None:
        return None
    missing = [f for f in supported if f not in runtime_formats]
    if not missing:
        return None
    return "Unsupported in this browser: " + ", ".join(missing)


def map_camera_error(name: str | None, message: str | None = None) -> str:
    """Map DOMException names to user-visible scanner errors."""
    mapping = {
        "NotAllowedError": "camera permission denied",
        "NotFoundError": "no camera available",
        "NotReadableError": "camera already in use",
        "AbortError": "camera stream interrupted",
        "SecurityError": "insecure context — HTTPS required",
        "OverconstrainedError": "no camera available",
    }
    if name and name in mapping:
        return mapping[name]
    if message:
        return message
    return "unexpected camera error"


def accept_detection(
    raw_value: str,
    symbology: str,
    *,
    last_value: str | None,
    last_at_ms: int | None,
    now_ms: int | None = None,
) -> dict[str, object]:
    """Decide whether to accept a decode, populate input, and stop scanning."""
    try:
        result = apply_detected_scan(raw_value, symbology)
    except ValueError as exc:
        return {"accepted": False, "stop_scanner": False, "error": str(exc)}
    if should_suppress_duplicate(
        result["value"],
        last_value,
        last_at_ms,
        now_ms=now_ms,
    ):
        return {"accepted": False, "stop_scanner": False, "suppressed": True}
    return {
        "accepted": True,
        "stop_scanner": True,
        "value": result["value"],
        "symbology": result["symbology"],
    }


def release_media_tracks(tracks: list[dict[str, object]]) -> int:
    """Stop media tracks (test mirror of browser MediaStreamTrack.stop())."""
    stopped = 0
    for track in tracks:
        if track.get("stopped"):
            continue
        track["stopped"] = True
        stopped += 1
    return stopped

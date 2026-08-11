"""Tests for scanner detection logic."""

from __future__ import annotations

import time

from inventory_scanner.scanner_detect import (
    MAX_SCAN_VALUE_LENGTH,
    REQUIRED_FORMATS,
    TARGET_FORMATS,
    accept_detection,
    apply_detected_scan,
    map_camera_error,
    native_covers_required,
    release_media_tracks,
    resolve_scanner_backend,
    should_suppress_duplicate,
    unsupported_formats_message,
    validate_scan_value,
)


def test_native_covers_required_all_present() -> None:
    runtime = list(REQUIRED_FORMATS) + ["ean_8", "upc_a"]
    assert native_covers_required(runtime)


def test_native_covers_required_missing_datamatrix() -> None:
    runtime = ["code_128", "ean_13", "qr_code"]
    assert not native_covers_required(runtime)


def test_resolve_backend_native_when_formats_complete() -> None:
    fmts = list(REQUIRED_FORMATS)
    assert resolve_scanner_backend(has_native=True, native_formats=fmts, polyfill_available=False) == "native"


def test_resolve_backend_polyfill_when_native_missing() -> None:
    assert (
        resolve_scanner_backend(has_native=False, native_formats=None, polyfill_available=True)
        == "polyfill"
    )


def test_resolve_backend_polyfill_when_native_lacks_required_format() -> None:
    partial = ["code_128", "ean_13", "qr_code"]
    assert (
        resolve_scanner_backend(has_native=True, native_formats=partial, polyfill_available=True)
        == "polyfill"
    )


def test_resolve_backend_unavailable() -> None:
    assert (
        resolve_scanner_backend(has_native=False, native_formats=None, polyfill_available=False)
        == "unavailable"
    )


def test_duplicate_suppression_blocks_repeat() -> None:
    now = int(time.time() * 1000)
    assert should_suppress_duplicate("4006381333931", "4006381333931", now - 500, now_ms=now)
    assert not should_suppress_duplicate("4006381333931", "4006381333931", now - 3000, now_ms=now)
    assert not should_suppress_duplicate("4006381333931", "999", now - 100, now_ms=now)


def test_apply_detected_scan_populates_value() -> None:
    result = apply_detected_scan("  4006381333931 ", "ean_13")
    assert result == {"value": "4006381333931", "symbology": "ean_13"}


def test_apply_detected_scan_rejects_empty() -> None:
    try:
        apply_detected_scan("   ", "qr_code")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_validate_scan_value_max_length() -> None:
    try:
        validate_scan_value("x" * (MAX_SCAN_VALUE_LENGTH + 1))
        raised = False
    except ValueError as exc:
        raised = True
        assert "exceeds" in str(exc)
    assert raised


def test_accept_detection_stops_after_success() -> None:
    decision = accept_detection("ABC123", "code_128", last_value=None, last_at_ms=None)
    assert decision["accepted"] is True
    assert decision["stop_scanner"] is True
    assert decision["value"] == "ABC123"
    assert decision["symbology"] == "code_128"


def test_accept_detection_suppresses_duplicate() -> None:
    now = int(time.time() * 1000)
    first = accept_detection("ABC123", "code_128", last_value=None, last_at_ms=None, now_ms=now)
    second = accept_detection(
        "ABC123", "code_128", last_value="ABC123", last_at_ms=now, now_ms=now + 100
    )
    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second.get("suppressed") is True


def test_accept_detection_rejects_empty() -> None:
    decision = accept_detection("  ", "qr_code", last_value=None, last_at_ms=None)
    assert decision["accepted"] is False
    assert "empty" in str(decision["error"])


def test_map_camera_error_permission_denied() -> None:
    assert map_camera_error("NotAllowedError") == "camera permission denied"


def test_map_camera_error_in_use() -> None:
    assert map_camera_error("NotReadableError") == "camera already in use"


def test_release_media_tracks_stops_active() -> None:
    tracks = [{"id": 1}, {"id": 2, "stopped": True}]
    assert release_media_tracks(tracks) == 1
    assert tracks[0]["stopped"] is True
    assert tracks[1]["stopped"] is True


def test_unsupported_formats_message() -> None:
    msg = unsupported_formats_message(list(TARGET_FORMATS), ["qr_code", "ean_13"])
    assert msg and "code_128" in msg
    assert unsupported_formats_message(list(TARGET_FORMATS), list(TARGET_FORMATS)) is None


def test_target_formats_include_required_set() -> None:
    for fmt in ("ean_13", "code_128", "qr_code", "data_matrix"):
        assert fmt in TARGET_FORMATS

"""Pack line validation and expansion tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from inventory_scanner.pack_lines import (
    expand_pack_lines,
    format_pack_line,
    normalize_unit,
    validate_pack_lines,
)


def test_normalize_unit_aliases() -> None:
    assert normalize_unit("ml") == "ml"
    assert normalize_unit("ML") == "ml"
    assert normalize_unit("ug") == "µg"
    assert normalize_unit("pcs") == "pcs"


def test_validate_pack_lines_requires_unit() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_pack_lines([{"amount_per_container": 10, "unit": ""}])
    assert exc.value.status_code == 400
    assert "Unit required" in str(exc.value.detail)


def test_validate_pack_lines_rejects_invalid_amount() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_pack_lines([{"amount_per_container": 0, "unit": "ml"}])
    assert exc.value.status_code == 400
    assert "Amount" in str(exc.value.detail)


def test_one_line_per_container() -> None:
    lines = validate_pack_lines(
        [
            {"amount_per_container": 300, "unit": "ml"},
            {"amount_per_container": 50, "unit": "g"},
        ]
    )
    specs = expand_pack_lines(lines)
    assert specs == [(300, "mL"), (50, "g")]
    assert format_pack_line(lines[0]) == "300 ml"


def test_legacy_container_count_ignored_one_container_per_line() -> None:
    lines = validate_pack_lines(
        [{"container_count": 5, "amount_per_container": 100, "unit": "g"}],
    )
    assert expand_pack_lines(lines) == [(100, "g")]

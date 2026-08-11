"""Inventory ID validation tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from inventory_scanner.inventory_validation import validate_category_id, validate_storage_id


def test_validate_category_id_required() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_category_id(None)
    assert exc.value.status_code == 400


def test_validate_category_id_rejects_unknown() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_category_id(99)
    assert exc.value.status_code == 400


def test_validate_category_id_accepts_poc_ids() -> None:
    assert validate_category_id(25) == 25


def test_validate_storage_id_required() -> None:
    with pytest.raises(HTTPException) as exc:
        validate_storage_id(None)
    assert exc.value.status_code == 400


def test_validate_storage_id_accepts_positive() -> None:
    assert validate_storage_id(4) == 4

"""Multi-pack quantity lines for register workflow."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

# Scanner-facing unit labels (UI + API payload).
PACK_UNITS = frozenset({"g", "mg", "µg", "kg", "ml", "µl", "L", "pcs"})

# Map scanner units to eLabFTW container qty_unit values.
_ELAB_UNIT_MAP = {
    "g": "g",
    "mg": "mg",
    "µg": "μg",
    "kg": "kg",
    "ml": "mL",
    "µl": "μL",
    "L": "L",
    "pcs": "•",
}


@dataclass(frozen=True)
class ValidatedPackLine:
    amount_per_container: float
    unit: str
    elab_unit: str


def normalize_unit(unit: str) -> str:
    raw = (unit or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    aliases = {
        "ug": "µg",
        "μg": "µg",
        "ul": "µl",
        "μl": "µl",
        "ml": "ml",
        "l": "L",
        "pc": "pcs",
        "pcs": "pcs",
        "piece": "pcs",
        "pieces": "pcs",
    }
    return aliases.get(lowered, raw if raw in PACK_UNITS else lowered)


def to_elab_unit(unit: str) -> str:
    normalized = normalize_unit(unit)
    if normalized not in PACK_UNITS:
        raise HTTPException(400, f"Invalid unit {unit!r}; allowed: {sorted(PACK_UNITS)}")
    return _ELAB_UNIT_MAP[normalized]


def validate_pack_lines(lines: list[dict[str, object]] | None) -> list[ValidatedPackLine]:
    if not lines:
        raise HTTPException(400, "At least one container line is required")
    validated: list[ValidatedPackLine] = []
    for index, raw in enumerate(lines):
        n = index + 1
        unit_raw = str(raw.get("unit") or "").strip()
        if not unit_raw:
            raise HTTPException(400, f"Unit required (container {n})")
        unit = normalize_unit(unit_raw)
        if unit not in PACK_UNITS:
            raise HTTPException(400, f"Invalid unit on container {n}")

        try:
            amount = float(raw.get("amount_per_container", 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"Amount required (container {n})") from exc
        if amount <= 0:
            raise HTTPException(400, f"Amount must be greater than 0 (container {n})")

        validated.append(
            ValidatedPackLine(
                amount_per_container=amount,
                unit=unit,
                elab_unit=to_elab_unit(unit),
            )
        )
    return validated


def expand_pack_lines(lines: list[ValidatedPackLine]) -> list[tuple[float, str]]:
    """One scanner line → one eLab container (amount + unit for that vessel)."""
    return [(line.amount_per_container, line.elab_unit) for line in lines]


def format_pack_line(line: ValidatedPackLine) -> str:
    return f"{line.amount_per_container:g} {line.unit}"

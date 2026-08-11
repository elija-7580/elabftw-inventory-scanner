"""Barcode and GS1 parsing utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedBarcode:
    raw: str
    symbology: str
    gtin: str = ""
    lot: str = ""
    expiry: str = ""
    gs1_fields: dict[str, str] = field(default_factory=dict)


GS1_AIS = {
    "01": "gtin",
    "10": "lot",
    "17": "expiry",
    "21": "serial",
}


def parse_gs1_datamatrix(payload: str) -> ParsedBarcode:
    """Parse GS1 element strings (parentheses or FNC1-separated)."""
    fields: dict[str, str] = {}
    # (01)09501101530003(17)231231(10)ABC123
    for m in re.finditer(r"\((\d{2})\)([^\(]+)", payload):
        ai, value = m.group(1), m.group(2).strip()
        key = GS1_AIS.get(ai, f"ai_{ai}")
        fields[key] = value
    if not fields and "\x1d" in payload:
        # FNC1 separated fallback — simplified
        parts = payload.split("\x1d")
        if parts:
            fields["raw_segment"] = parts[0]
    return ParsedBarcode(
        raw=payload,
        symbology="datamatrix_gs1",
        gtin=fields.get("gtin", ""),
        lot=fields.get("lot", ""),
        expiry=fields.get("expiry", ""),
        gs1_fields=fields,
    )


def classify_scan(raw: str) -> ParsedBarcode:
    raw = raw.strip()
    if raw.startswith("http"):
        return ParsedBarcode(raw=raw, symbology="qr_url")
    if re.match(r"^\(\d{2}\)", raw):
        return parse_gs1_datamatrix(raw)
    if re.match(r"^\d{8,14}$", raw):
        return ParsedBarcode(raw=raw, symbology="ean_upc", gtin=raw)
    if re.match(r"^\d{2,7}-\d{2}-\d$", raw):
        return ParsedBarcode(raw=raw, symbology="cas_number")
    return ParsedBarcode(raw=raw, symbology="unknown")

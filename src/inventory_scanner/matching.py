"""Product identity normalization and duplicate detection."""

from __future__ import annotations

from .domain import CompoundCandidate, ConfidenceLevel, ConfidenceResult, InventoryItem, ProductCandidate, normalize_text


def product_identity_key(manufacturer: str, catalogue_number: str) -> tuple[str, str]:
    return normalize_text(manufacturer), normalize_text(catalogue_number)


def match_item_exact(items: list[dict], manufacturer: str, catalogue_number: str) -> InventoryItem | None:
    mfg, cat = product_identity_key(manufacturer, catalogue_number)
    for it in items:
        meta = it.get("metadata") or {}
        if isinstance(meta, str):
            import json

            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                continue
        ef = meta.get("extra_fields") or (meta.get("elabftw") or {}).get("extra_fields") or {}
        im = normalize_text(str((ef.get("Manufacturer") or {}).get("value", "")))
        ic = normalize_text(str((ef.get("Catalogue Number") or {}).get("value", "")))
        if im == mfg and ic == cat and mfg and cat:
            return InventoryItem(
                item_id=int(it["id"]),
                title=it.get("title", ""),
                action="reuse",
                manufacturer=manufacturer,
                catalogue_number=catalogue_number,
            )
    return None


def match_compound_exact(compounds: list[dict], cas: str = "", cid: str = "") -> CompoundCandidate | None:
    cas_n = normalize_text(cas.replace("-", ""))
    for c in compounds:
        c_cas = normalize_text(str(c.get("cas_number") or "").replace("-", ""))
        c_cid = str(c.get("pubchem_cid") or "")
        if cas_n and c_cas and cas_n == c_cas:
            return CompoundCandidate(compound_id=int(c["id"]), name=c.get("name", ""), cas_number=cas, action="reuse",
                                     confidence=ConfidenceResult(ConfidenceLevel.HIGH, 0.95, ["cas_exact"]))
        if cid and c_cid and cid == c_cid:
            return CompoundCandidate(compound_id=int(c["id"]), name=c.get("name", ""), pubchem_cid=cid, action="reuse",
                                     confidence=ConfidenceResult(ConfidenceLevel.HIGH, 0.95, ["cid_exact"]))
    return None


def assess_candidate_confidence(candidate: ProductCandidate) -> ConfidenceResult:
    reasons: list[str] = []
    score = 0.0
    if candidate.identity.manufacturer_norm and candidate.identity.catalogue_norm:
        score += 0.5
        reasons.append("manufacturer+catalogue present")
    if candidate.cas_number:
        score += 0.2
        reasons.append("cas present")
    if candidate.lookup_source:
        score += 0.1
        reasons.append(f"lookup:{candidate.lookup_source}")
    if candidate.product_name:
        score += 0.1
    level = ConfidenceLevel.NONE
    if score >= 0.8:
        level = ConfidenceLevel.HIGH
    elif score >= 0.7:
        level = ConfidenceLevel.MEDIUM
    elif score >= 0.4:
        level = ConfidenceLevel.LOW
    return ConfidenceResult(level=level, score=min(score, 1.0), reasons=reasons)

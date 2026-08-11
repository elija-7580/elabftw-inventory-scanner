import json


from inventory_scanner.barcode import classify_scan, parse_gs1_datamatrix
from inventory_scanner.extra_fields import build_corrected_item_metadata, inventory_item_fields, validate_field
from inventory_scanner.matching import match_compound_exact, match_item_exact, product_identity_key
from inventory_scanner.metadata import merge_metadata, normalize_metadata


def test_normalize_moves_nested_extra_fields():
    raw = {
        "elabftw": {
            "extra_fields": {
                "Manufacturer": {"type": "text", "value": "VWR"},
            }
        }
    }
    out = normalize_metadata(raw)
    assert "Manufacturer" in out["extra_fields"]
    assert "extra_fields" not in out["elabftw"]


def test_merge_preserves_unrelated_metadata():
    base = {"extra_fields": {"ID": {"type": "text", "value": "X"}}, "elabftw": {"source": "test"}}
    patch = {"extra_fields": {"Manufacturer": {"type": "text", "value": "A"}}}
    merged = merge_metadata(base, patch)
    assert merged["extra_fields"]["ID"]["value"] == "X"
    assert merged["extra_fields"]["Manufacturer"]["value"] == "A"
    assert merged["elabftw"]["source"] == "test"


def test_build_corrected_item_metadata():
    before = {
        "elabftw": {
            "extra_fields": {
                "Manufacturer": {"type": "text", "value": "VWR"},
                "Manufacturer Barcode": {"type": "text", "value": "123"},
                "POC Tag": {"type": "text", "value": "tag"},
            }
        }
    }
    after = build_corrected_item_metadata(before)
    assert set(after["extra_fields"].keys()) == {"Manufacturer", "Catalogue Number", "Original Barcode"}
    assert after["elabftw"].get("poc_tag") == "tag"


def test_gs1_parse():
    p = parse_gs1_datamatrix("(01)09501101530003(10)LOT1(17)251231")
    assert p.gtin == "09501101530003"
    assert p.lot == "LOT1"


def test_classify_ean():
    p = classify_scan("4006381333931")
    assert p.symbology == "ean_upc"


def test_match_item_exact():
    items = [
        {
            "id": 233,
            "title": "Test",
            "metadata": json.dumps(
                {
                    "extra_fields": {
                        "Manufacturer": {"type": "text", "value": "VWR"},
                        "Catalogue Number": {"type": "text", "value": "27810.294"},
                    }
                }
            ),
        }
    ]
    hit = match_item_exact(items, "VWR", "27810.294")
    assert hit and hit.item_id == 233


def test_match_compound_cas():
    compounds = [{"id": 4, "name": "NaCl", "cas_number": "7647-14-5", "pubchem_cid": 5234}]
    hit = match_compound_exact(compounds, cas="7647-14-5")
    assert hit and hit.compound_id == 4


def test_product_identity_normalization():
    assert product_identity_key("  VWR ", "27810.294") == ("vwr", "27810.294")


def test_inventory_field_validation():
    f = inventory_item_fields(manufacturer="A", catalogue_number="B", original_barcode="C")
    for name, field in f.items():
        validate_field(name, field)

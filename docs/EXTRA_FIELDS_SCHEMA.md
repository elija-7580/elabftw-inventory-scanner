# eLabFTW Rendered Extra Fields Schema (5.5.x)

Verified against eLabFTW **5.5.x** behavior for inventory Items.

## Two metadata layers

| Layer | Path | Rendered in UI? |
|---|---|---|
| **Rendered extra fields** | `metadata.extra_fields` | **Yes** |
| **Machine metadata** | `metadata.elabftw` | **No** (internal) |

## Common defect

Inventory fields nested under `metadata.elabftw.extra_fields` are stored but **not rendered**.
eLabFTW UI reads **`metadata.extra_fields`** at the top level (sibling of `elabftw`).

Correct shape:

```json
{
  "elabftw": { "source": "inventory-scanner" },
  "extra_fields": {
    "Manufacturer": { "type": "text", "value": "VendorA" },
    "Catalogue Number": { "type": "text", "value": "CAT-A" }
  }
}
```

## Field schema

Each rendered field is an object:

```json
{
  "type": "text|date|number|select|url",
  "value": "<string>",
  "description": "<optional>",
  "options": ["..."],
  "group_id": 1,
  "position": 1,
  "required": true
}
```

- **text** — minimum for inventory strings
- **select** — requires `options` array
- **date** — ISO date string `YYYY-MM-DD`

## API transport

| Operation | metadata format |
|---|---|
| GET item | JSON **string** |
| PATCH item | JSON **string** (`json.dumps(meta)`) |
| POST item | JSON **object** acceptable |

## Inventory scanner canonical fields

Rendered on Items (top-level `extra_fields`):

- `Manufacturer` (text)
- `Catalogue Number` (text)
- `Original Barcode` (text)
- `Lot/Batch Number` (text, optional)
- `Expiry Date` (date, optional)

Machine-only (`metadata.elabftw`):

- `source`, `scanner_version`, `idempotency_key`

## Do not duplicate native fields

| Data | Store in |
|---|---|
| Chemical identity | Compound + `compounds_links` |
| Quantity / unit | Container `qty_stored`, `qty_unit` |
| Location | Container `storage_id` |
| Product title | Item `title` |

CAS / PubChem CID belong on **Compound**, not Item extra fields, when a compound link exists.

## Serializer

`src/inventory_scanner/extra_fields.py` — `build_corrected_item_metadata()`

# Product catalog import

Local product catalog for scan prefill. Separate from eLabFTW items/containers.

## Demo fixtures

Synthetic fixtures (no real lab inventory data):

- `fixtures/catalog/synthetic_products.csv`
- `fixtures/catalog/synthetic_products.xlsx`
- `fixtures/catalog/duplicates_conflicts.csv`
- `fixtures/catalog/malformed_rows.csv`

## Canonical fields

| Field | Required identity role |
|-------|------------------------|
| `product_name` | optional |
| `manufacturer` | secondary identity (with catalog_number) |
| `catalog_number` | secondary identity (with manufacturer) |
| `cas_number` | optional |
| `primary_code` | primary exact match |
| `alternate_codes` | primary exact match |
| `category_id` | optional; validated only when requested |

Each row needs **primary_code** **or** **manufacturer + catalog_number**.

## API

- `POST /api/catalog/import/preview` — multipart file (+ optional sheet/mapping); **zero DB writes**
- `POST /api/catalog/import/commit` — same payload + `confirm=true`; transactional
- `POST /api/catalog/import/error-report` — CSV of row/field/reason
- `POST /api/catalog/lookup` — scan/code lookup for register prefill
- `POST /api/catalog/save` — explicit operator save (`confirm=true`)

Catalog operations never create eLabFTW records and never bypass `ELAB_INTEGRATION_LIVE`.

## Security limits

| Limit | Value |
|-------|-------|
| Max upload size | 5 MiB |
| Max data rows | 5,000 |
| Max columns | 64 |
| Max worksheets | 20 |
| ZIP members | 200 |
| ZIP uncompressed total | 25 MiB |
| ZIP per-member uncompressed | 10 MiB |
| ZIP compression ratio | 100× (for members > 1 MiB) |

Uploads are validated by **content signature** (CSV text vs OOXML ZIP), not extension alone. Legacy `.xls` is rejected. Encrypted ZIPs, path traversal, and ZIP bombs are rejected before openpyxl loads the workbook. Uploaded bytes are processed in memory and are **not** retained on disk.

Downloadable error CSVs neutralize cells beginning with `=`, `+`, `-`, or `@` (prefix `'`) to prevent spreadsheet formula injection. Leading zeroes in product codes are preserved during normalize/match.

All `/api/catalog/*` routes require an authenticated scanner session when OIDC is configured.

# Scanning Workflows

## Camera barcode detection (read-only)

Detection populates the code input only. It does **not** register products, change quantities, or call mutation endpoints. Staging keeps `ELAB_INTEGRATION_LIVE=false` — confirm/action endpoints return **403**.

### Decoder architecture

| Backend | When selected | Target formats |
|---|---|---|
| **Native** `BarcodeDetector` | API present **and** `getSupportedFormats()` includes `code_128`, `ean_13`, `qr_code`, `data_matrix` | Runtime-dependent |
| **ZXing fallback** (`@zxing/browser@0.1.5`, bundled) | Native missing or lacks a required format | Code 128, EAN-13/EAN-8, QR, DataMatrix, UPC-A/E |

Selection logic: `scanner_detect.py` / `web/src/scanner-core.js`. UI entry: `web/src/scanner-app.js` built to `web/dist/js/scanner-app.<hash>.js` (esbuild IIFE, no import maps).

### Requirements

- **HTTPS** secure context
- Explicit **Start scanner** tap before camera permission
- Camera frames processed **locally** — not uploaded

### Out of scope

- Live writes, OCR, continuous multi-scan without restart

## Workflow A — Register new product

1. Start **Register new product**
2. **Start scanner** or enter code manually
3. Parse → lookup duplicates (read-only API)
4. Confirm fields (mutation gated on staging)

## Workflow B — Manage existing stock

1. Start **Manage existing stock**
2. Scan container QR or enter ID
3. View container details
4. Quantity changes (mutation gated on staging)

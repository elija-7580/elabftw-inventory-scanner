# Architecture

## Components

```
[Mobile browser] ──HTTPS──► [Caddy] ──► [Scanner BFF :8020]
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            [eLabFTW API v2]          [SQLite ledger]            [PubChem REST]
```

- **Browser** — camera scan, confirmation UI; no API keys
- **BFF** — FastAPI (`src/inventory_scanner/app.py`); all privileged writes
- **eLabFTW** — authoritative Compound, Item, Container, storage_units
- **Ledger** — append-only stock transactions (`audit.py`)

## Data model

See `docs/DATA_MODEL.md`.

## Internal container QR

`https://elab.example.com/scanner/container/{container_id}`

Requires BFF route + authentication. QR encodes no secrets.

## Integration gate

`ELAB_INTEGRATION_LIVE=true` required for write endpoints touching production.

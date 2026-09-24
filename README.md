# VialTrack

<p align="center">
  <img src="docs/brand/wordmark-lockup-dark.svg" alt="VialTrack" height="40" />
</p>

<p align="center">
  <img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" />
  <img alt="eLabFTW" src="https://img.shields.io/badge/eLabFTW-5.5.x%20API-29ADB9.svg" />
  <img alt="Status" src="https://img.shields.io/badge/status-technical%20prototype-important.svg" />
  <img alt="Writes" src="https://img.shields.io/badge/ELAB_INTEGRATION_LIVE-default%20false-lightgrey.svg" />
</p>

Mobile-first inventory companion for **eLabFTW 5.5.x**.

This project is an independent FastAPI BFF + web UI that talks to eLabFTW over its public API. It is **not** part of eLabFTW, **not** affiliated with Deltablot, and **not** a validated GxP system. Formal production / GxP sign-off remains open.

> Product UI brand: **VialTrack — by Elijá Friedrich-Ulrich** (Lato lockup). Configure via `BRAND_PRODUCT_NAME` / `BRAND_ENDORSEMENT` / `BRAND_ACCENT_HEX` (`#29ADB9`). Header/nav chrome is `#2B2B2B` in both modes. Design tokens live in `web/tokens.css` (eLabFTW-look). No brand on printed labels.

## What it does

Two operator workflows:

1. **Register new product** — scan or enter a manufacturer code, confirm identity fields, then create eLabFTW Item + Container(s) (when live writes are enabled).
2. **Manage existing stock** — scan an internal container QR / ID and update quantity (consume, restock, set exact, mark empty).
3. **Print / reprint labels** — after register confirm, download PDF/PNG for each container; Manage reprints the same ID (no new container).

Supporting features:

- Camera barcode detection (native `BarcodeDetector` with ZXing fallback)
- Local SQLite product catalog for scan prefill (CSV/XLSX import)
- Authentik / OIDC session gate (optional)
- Write gate `ELAB_INTEGRATION_LIVE` (default **false**)
- Reverse-proxy friendly under Caddy path prefix `/scanner`

## Screenshots

Demo UI (dark default). Writes disabled (`ELAB_INTEGRATION_LIVE=false`). Synthetic options only.

### Mobile

![Home on mobile](docs/screenshots/home-mobile.png)

![Register view with scan panel on mobile](docs/screenshots/register-mobile.png)

![Manage view on mobile](docs/screenshots/manage-mobile.png)

![Catalog import on mobile](docs/screenshots/catalog-import-mobile.png)

### Desktop

<details>
<summary>Desktop layouts (1440×900)</summary>

| Home | Register |
| --- | --- |
| ![Home on desktop](docs/screenshots/home-desktop.png) | ![Register view with scan panel on desktop](docs/screenshots/register-desktop.png) |

| Manage | Catalog import |
| --- | --- |
| ![Manage view on desktop](docs/screenshots/manage-desktop.png) | ![Catalog import on desktop](docs/screenshots/catalog-import-desktop.png) |

</details>

Social preview asset: [`docs/brand/social-512.png`](docs/brand/social-512.png).

## Quick start (Docker)

```bash
cp .env.example .env
# Fill ELABFTW_API_URL / ELABFTW_API_KEY and session secrets.
# Keep ELAB_INTEGRATION_LIVE=false until you intentionally enable writes.

docker compose up -d --build
```

Health (behind Caddy `/scanner` stripping):

```bash
curl -fsS https://elab.example.com/scanner/health
```

### Caddy prefix (example)

```caddyfile
handle_path /scanner/* {
    reverse_proxy inventory-scanner:8020
}
```

### OIDC (optional)

Set `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `SCANNER_SESSION_SECRET`.
Redirect URI: `https://elab.example.com/scanner/auth/callback`.

When OIDC is configured, unauthenticated browser visits redirect to login and APIs return `401` JSON.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest

# Web bundle (required for UI-serving tests)
bash scripts/build_web.sh
```

## Write safety

- `ELAB_INTEGRATION_LIVE=false` → mutation endpoints return **403**
- Local catalog import/save does **not** create eLabFTW inventory records
- Browser never receives the eLabFTW API key

## License

Apache License 2.0. See `LICENSE` and `NOTICE`.

## Disclaimer

This software is provided **as is**, without warranty. It has **not** been validated for GMP, GDP, GxP, or 21 CFR Part 11 use. You are responsible for your own risk assessment, configuration, and deployment practices. eLabFTW® is a trademark of its respective owners; this project is an independent API client.

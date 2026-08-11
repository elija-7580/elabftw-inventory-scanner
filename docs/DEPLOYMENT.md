# Deployment

Generic staging notes for the scanner BFF. Adapt host paths and domains to your environment.

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker + Compose | Scanner service only |
| External Docker network | Shared with your eLabFTW stack (example name: `elabftw-net`) |
| Reverse proxy | Caddy (or equivalent) with `/scanner` path strip |
| Secrets | eLabFTW API key + OIDC secrets in `.env` (mode 600) |
| Writes | Keep `ELAB_INTEGRATION_LIVE=false` until intentionally enabling mutations |

## Staging target (example)

| Item | Value |
|---|---|
| Public URL | `https://elab.example.com/scanner/` |
| BFF port | `8020` (internal) |
| Image | `inventory-scanner:staging` |
| Memory limit | `256m` (compose default) |

## Caddy route (example)

```caddyfile
handle_path /scanner/* {
    reverse_proxy inventory-scanner:8020 {
        header_up Host {host}
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Prefix /scanner
    }
}
```

Backup your reverse-proxy config before editing.

## Deploy sequence (scanner only)

```bash
cp .env.example .env   # then fill secrets; keep ELAB_INTEGRATION_LIVE=false
docker compose build
docker compose up -d --no-deps --force-recreate inventory-scanner
curl -fsS https://elab.example.com/scanner/health
```

## Rollback

See `docs/ROLLBACK.md`.

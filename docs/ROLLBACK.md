# Rollback Procedures

Scanner-only rollback notes for a Docker Compose staging deployment. This does **not** cover eLabFTW core stack recovery.

## 1. Scanner container image rollback

Tag the previous known-good image before deploying a new candidate, then retag and recreate **only** the scanner service:

```bash
docker tag inventory-scanner:rollback-YYYYMMDDTHHMMSSZ inventory-scanner:staging
cd /path/to/inventory-scanner
docker compose up -d --no-deps --force-recreate inventory-scanner
```

Verify:

```bash
curl -fsS https://elab.example.com/scanner/health
curl -fsS https://elab.example.com/api/v2/info
```

## 2. Keep writes disabled by default

Ensure `ELAB_INTEGRATION_LIVE=false` in the scanner environment before and after rollback unless a controlled write pilot is intentionally approved.

## 3. Companion database

The scanner SQLite companion DB (`SCANNER_DB_PATH`, often mounted under `./data`) stores:

- local product catalog
- stock transaction ledger rows

Back up that file before upgrades if you rely on catalog/audit history. Restoring eLabFTW alone does **not** restore the companion ledger.

## 4. Do not

- Do not run `docker compose down` on the shared eLabFTW stack unless you intend to stop unrelated services
- Do not mutate eLabFTW MySQL to “fix” scanner state
- Do not enable live writes to recover from a bad deploy

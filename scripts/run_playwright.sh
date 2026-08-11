#!/usr/bin/env bash
# Run Playwright Chromium + WebKit tests in pinned container (uvicorn on host).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PW_IMAGE="${SCANNER_PLAYWRIGHT_IMAGE:-mcr.microsoft.com/playwright:v1.49.1-jammy}"
PORT="${PLAYWRIGHT_PORT:-8765}"

bash "$ROOT/scripts/build_web.sh"

export OIDC_ISSUER="${OIDC_ISSUER:-https://auth.example.com/application/o/scanner/}"
export OIDC_CLIENT_ID="${OIDC_CLIENT_ID:-scanner-bff-test}"
export OIDC_CLIENT_SECRET="${OIDC_CLIENT_SECRET:-test-client-secret}"
export SCANNER_SESSION_SECRET="${SCANNER_SESSION_SECRET:-test-session-secret-32-chars-minimum!}"
export SCANNER_SESSION_HTTPS_ONLY=false
export SCANNER_ALLOW_DEV_LOGIN=true
export ELAB_INTEGRATION_LIVE=false

SCANNER_WEB_DIR="$ROOT/web/dist" \
  "$ROOT/.venv/bin/uvicorn" inventory_scanner.app:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker run --rm \
  --network host \
  -v "$ROOT:/repo" \
  -w /repo/tests/e2e \
  -e "PLAYWRIGHT_BASE_URL=http://127.0.0.1:$PORT" \
  "$PW_IMAGE" \
  bash -c 'npm install && npx playwright test --config playwright.docker.config.mjs'

echo "playwright tests complete"

#!/usr/bin/env bash
# Build web bundle inside pinned Node container (no global Node on host).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NODE_IMAGE="${SCANNER_NODE_IMAGE:-node:22.12.0-bookworm-slim}"

docker run --rm \
  -v "$ROOT:/repo" \
  -w /repo/web \
  "$NODE_IMAGE" \
  bash -c 'npm ci && npm run build && node ../tests/js/test_scanner_core.mjs && node ../tests/js/test_scanner_ui.mjs'

echo "web build complete"

#!/usr/bin/env bash
# Copy built web assets into web/dist for local pytest (expects build already ran).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -f "$ROOT/web/dist/build-manifest.json" ]]; then
  bash "$ROOT/scripts/build_web.sh"
fi

echo "web/dist ready: $(cat "$ROOT/web/dist/build-manifest.json")"

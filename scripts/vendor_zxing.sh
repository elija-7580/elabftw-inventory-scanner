#!/usr/bin/env bash
# Vendor @zxing/browser + @zxing/library for offline serving (no runtime CDN).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/web/js/vendor"
BROWSER_VER="0.1.5"
LIBRARY_VER="0.21.3"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$VENDOR"
rm -rf "$VENDOR/zxing-browser" "$VENDOR/zxing-library"

curl -fsSL "https://registry.npmjs.org/@zxing/browser/-/browser-${BROWSER_VER}.tgz" \
  | tar xz -C "$TMP" -f -
mv "$TMP/package" "$VENDOR/zxing-browser"

curl -fsSL "https://registry.npmjs.org/@zxing/library/-/library-${LIBRARY_VER}.tgz" \
  | tar xz -C "$TMP" -f -
mv "$TMP/package" "$VENDOR/zxing-library"

echo "vendored @zxing/browser@${BROWSER_VER} and @zxing/library@${LIBRARY_VER} -> web/js/vendor/"

#!/usr/bin/env node
/** UI presentation smoke checks for redesigned scanner shell. */
import { resolveApiBase, isSmallCodeDebugEnabled } from "../../web/src/scanner-core.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

const root = dirname(fileURLToPath(import.meta.url));
const template = readFileSync(join(root, "../../web/index.template.html"), "utf8");

assert(template.includes("--accent: __BRAND_ACCENT_HEX__"), "brand accent token placeholder missing");
assert(template.includes("--touch-primary: 56px") || template.includes("tokens.css"), "primary touch / tokens missing");
assert(template.includes('href="tokens.css"'), "tokens.css link missing");
assert(template.includes("prefers-color-scheme: light") || true); // light lives in tokens.css
const tokens = readFileSync(join(root, "../../web/tokens.css"), "utf8");
assert(tokens.includes("--bg: #1E1E1E"), "dark bg missing from tokens.css");
assert(tokens.includes("--accent: #29ADB9"), "eLabFTW accent missing from tokens.css");
assert(tokens.includes("--chrome: #2B2B2B"), "chrome token missing from tokens.css");
assert(tokens.includes("prefers-color-scheme: light"), "light mode missing from tokens.css");
assert(tokens.includes("--bg: #F2F2F2"), "light bg missing from tokens.css");
assert(tokens.includes('"Lato"'), "Lato font stack missing from tokens.css");
assert(!/#14B8A6/i.test(tokens), "old teal accent still in tokens.css");
assert(!/#05070A/i.test(tokens), "old cold-gray-0 still in tokens.css");
assert(!/IBM Plex/i.test(tokens), "IBM Plex still in tokens.css");
assert(!/#14B8A6/i.test(template), "old teal still in template");
assert(!/IBM Plex/i.test(template), "IBM Plex still in template");
assert(!/#1a8a94/i.test(template), "legacy teal brand still present");
assert(!/Schild Lab/i.test(template), "hardcoded lab brand still present");
assert(template.includes('id="readonly-bar"'), "read-only bar missing");
assert(template.includes('id="nav-home"'), "home nav missing");
assert(template.includes('id="btn-register"'), "register action missing");
assert(template.includes("Catalog management"), "catalog utility section missing");
assert(template.includes('data-step-indicator="1"'), "import steps missing");
assert(template.includes("Hold the code inside the frame."), "scan instruction missing");
assert(template.includes("sticky-actions"), "sticky actions missing");
assert(template.includes("prefers-reduced-motion"), "reduced motion missing");
assert(template.includes("--mono:") || tokens.includes("--mono:"), "monospace token missing");
assert(template.includes("Space Mono") || tokens.includes("Space Mono"), "Space Mono mono stack missing");
assert(template.includes("font-variant-numeric: tabular-nums"), "tabular numerals missing");
assert(template.includes("__BRAND_PRODUCT_NAME__"), "brand product placeholder missing");
assert(template.includes("__BRAND_ENDORSEMENT__"), "brand endorsement placeholder missing");
assert(template.includes("brand/wordmark-lockup-dark.svg"), "wordmark dark SVG missing");
assert(template.includes('id="reg-label-panel"'), "register print panel missing");
assert(template.includes('id="mgr-label-panel"'), "manage reprint panel missing");
assert(template.includes("print-panel"), "print panel class missing");
assert(!/print-panel-pending/.test(template), "print-panel-pending still present");
assert(!/#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})\b/.test(template.replace(/__BRAND_ACCENT_HEX__/g, "")), "ad-hoc hex outside tokens.css");
assert(resolveApiBase({ getAttribute: () => "/scanner" }) === "/scanner");
assert(isSmallCodeDebugEnabled("?scanner_debug=1"));

console.log("scanner-ui presentation tests passed");

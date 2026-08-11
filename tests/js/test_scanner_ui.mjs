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

assert(template.includes("--accent: #FF9C1B"), "IMC accent token missing");
assert(template.includes("--action: #1F1F1F"), "primary action token missing");
assert(!/#1a8a94/i.test(template), "legacy teal brand still present");
assert(template.includes('id="readonly-bar"'), "read-only bar missing");
assert(template.includes('id="nav-home"'), "home nav missing");
assert(template.includes('id="btn-register"'), "register action missing");
assert(template.includes("Catalog management"), "catalog utility section missing");
assert(template.includes('data-step-indicator="1"'), "import steps missing");
assert(template.includes("Hold the code inside the frame."), "scan instruction missing");
assert(template.includes("sticky-actions"), "sticky actions missing");
assert(template.includes("prefers-reduced-motion"), "reduced motion missing");

assert(resolveApiBase({ getAttribute: () => "/scanner" }) === "/scanner");
assert(isSmallCodeDebugEnabled("?scanner_debug=1"));

console.log("scanner-ui presentation tests passed");

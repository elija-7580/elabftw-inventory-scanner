#!/usr/bin/env node
/**
 * Capture README screenshots with synthetic demo data only.
 * Serves web/dist statically and mocks BFF APIs (no real eLabFTW / OIDC).
 */
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  statSync,
} from "node:fs";
import { dirname, join, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = dirname(fileURLToPath(import.meta.url));
const repo = join(root, "..");
const dist = join(repo, "web", "dist");
const outDir = join(repo, "docs", "screenshots");

const REQUIRED = [
  "home-mobile.png",
  "home-desktop.png",
  "register-mobile.png",
  "register-desktop.png",
  "manage-mobile.png",
  "manage-desktop.png",
  "catalog-import-mobile.png",
  "catalog-import-desktop.png",
];

const SYNTHETIC_CSV =
  "Product,Manufacturer,Catalogue Number,CAS,Barcode,Alternate Codes,Category\n" +
  "Example Chemical A,VendorA,CAT-A,,00012345678905,,\n" +
  "Example Chemical B,VendorB,CAT-B,,4012345678901,,\n" +
  "Example Chemical C,VendorC,CAT-C,,TF18912014,,\n" +
  "Example Chemical D,VendorD,CAT-D,,7612345678901,,\n";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".map": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

function loadChromium() {
  const moduleRoots = [
    process.env.PLAYWRIGHT_NODE_MODULES,
    join(repo, "tests", "e2e", "node_modules"),
    join(repo, "node_modules"),
  ].filter(Boolean);
  for (const modules of moduleRoots) {
    const pkg = join(modules, "playwright", "package.json");
    if (!existsSync(pkg)) continue;
    const require = createRequire(pkg);
    const pw = require(".");
    if (pw.chromium) return pw.chromium;
  }
  // @playwright/test re-exports playwright
  for (const modules of moduleRoots) {
    const pkg = join(modules, "@playwright", "test", "package.json");
    if (!existsSync(pkg)) continue;
    const require = createRequire(pkg);
    try {
      const pw = require("playwright");
      if (pw.chromium) return pw.chromium;
    } catch (_) {
      /* continue */
    }
  }
  const require = createRequire(import.meta.url);
  return require("playwright").chromium;
}

function startStaticServer() {
  const server = createServer((req, res) => {
    try {
      const url = new URL(req.url || "/", "http://127.0.0.1");
      let path = decodeURIComponent(url.pathname);
      if (path === "/" || path === "") path = "/index.html";
      const file = join(dist, path.replace(/^\//, ""));
      if (!file.startsWith(dist)) {
        res.writeHead(403);
        res.end("forbidden");
        return;
      }
      const body = readFileSync(file);
      res.writeHead(200, { "Content-Type": MIME[extname(file)] || "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "not found" }));
    }
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, base: `http://127.0.0.1:${port}` });
    });
  });
}

async function installApiMocks(page) {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.route("**/api/config/public**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        modes: ["register", "manage"],
        elab_public_url: "https://elab.example.com",
        auth_enabled: false,
        writes_enabled: false,
        beta: true,
      }),
    });
  });

  await page.route("**/auth/session**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sub: "demo-user",
        email: "demo@example.com",
        name: "Demo Operator",
      }),
    });
  });

  await page.route("**/api/inventory/options**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        categories: [
          { id: 10, title: "Reagents" },
          { id: 11, title: "Consumables" },
        ],
        locations: [
          { id: 100, name: "Building", full_path: "Building", parent_id: null },
          {
            id: 101,
            name: "Unassigned Location",
            full_path: "Building / Unassigned Location",
            parent_id: 100,
          },
        ],
        pack_units: ["ml", "g", "units"],
        default_category_id: 10,
        default_storage_id: 101,
      }),
    });
  });

  await page.route("**/api/catalog/lookup**", async (route) => {
    let post = {};
    try {
      post = route.request().postDataJSON() || {};
    } catch (_) {
      post = {};
    }
    const code = String(post.code || "");
    if (code === "00012345678905") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "match",
          message: "Values from local product catalog",
          source: "local_catalog",
          product: {
            id: 1,
            product_name: "Example Chemical A",
            manufacturer: "VendorA",
            catalog_number: "CAT-A",
            cas_number: "",
            primary_code: "00012345678905",
            category_id: 10,
          },
          matches: [],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "no_match",
        message: "No catalog match — complete manually",
        matches: [],
        raw_code: code,
        normalized_code: code,
      }),
    });
  });

  await page.route("**/api/catalog/import/preview**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        headers: [
          "Product",
          "Manufacturer",
          "Catalogue Number",
          "CAS",
          "Barcode",
          "Alternate Codes",
          "Category",
        ],
        suggested_mapping: {
          product_name: "Product",
          manufacturer: "Manufacturer",
          catalog_number: "Catalogue Number",
          cas_number: "CAS",
          primary_code: "Barcode",
          alternate_codes: "Alternate Codes",
          category_id: "Category",
        },
        sheets: ["Products"],
        selected_sheet: "Products",
        new_products: 4,
        updates: 0,
        exact_duplicates: 0,
        conflicts: 0,
        error_count: 0,
        blank_rows: 0,
        format: "csv",
      }),
    });
  });
}

async function waitForApp(page) {
  await page.waitForFunction(() => document.documentElement.dataset.scannerReady === "true", null, {
    timeout: 15000,
  });
  await page.waitForTimeout(200);
}

async function prepare(page, base) {
  await installApiMocks(page);
  await page.goto(base + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForApp(page);
  await page.evaluate(() => {
    const retry = document.getElementById("scanner-retry");
    if (retry) retry.hidden = true;
    const banner = document.getElementById("status-banner");
    if (banner) banner.hidden = true;
  });
}

async function shot(browser, base, name, width, height, fn) {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 1,
  });
  await prepare(page, base);
  if (fn) await fn(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(150);
  const path = join(outDir, name);
  // Clip to viewport — no browser chrome; avoid fullPage scroll chrome artifacts
  await page.screenshot({ path, fullPage: false, type: "png" });
  await page.close();
  const kb = Math.round(statSync(path).size / 1024);
  console.log(`wrote ${name} (${kb} KiB)`);
  return path;
}

async function showRegisterScan(page) {
  await page.click("#btn-register");
  await page.waitForSelector("#register.active");
  await page.waitForSelector("#reg-scan-panel");
  await page.evaluate(() => {
    const status = document.getElementById("reg-scan-status");
    if (status) {
      status.className = "scan-status";
      status.textContent = "Camera inactive";
    }
  });
}

async function showManage(page) {
  await page.click("#btn-manage");
  await page.waitForSelector("#manage.active");
  await page.waitForSelector("#mgr-scan-panel");
  await page.waitForSelector("#mgr-empty:not([hidden])");
}

async function showCatalogImport(page) {
  await page.click("#btn-catalog-import");
  await page.waitForSelector("#catalog-import.active");
  await page.setInputFiles("#cat-file", {
    name: "synthetic_products.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(SYNTHETIC_CSV, "utf8"),
  });
  await page.click("#cat-preview");
  await page.waitForSelector("#cat-summary:not([hidden])");
}

function optimizePng(path) {
  // Prefer pngquant if available; otherwise leave as-is (Playwright PNGs are usually fine).
  try {
    execFileSync(
      "pngquant",
      ["--force", "--quality=65-85", "--skip-if-larger", "--output", path, path],
      { stdio: "ignore" },
    );
  } catch (_) {
    /* optional */
  }
  const size = statSync(path).size;
  if (size > 200 * 1024) {
    console.warn(`warning: ${path} is ${Math.round(size / 1024)} KiB (>200 KiB target)`);
  }
}

function assertNoBannedPixels(dir) {
  // Text OCR isn't available; scan PNG binary for ASCII brand strings as a cheap gate.
  const banned = [
    "Schild",
    "schildlab",
    "eln-schildlab",
    "Theraferm",
    "Sigma-Aldrich",
    "Sodium Chloride",
  ];
  for (const name of REQUIRED) {
    const buf = readFileSync(join(dir, name));
    const ascii = buf.toString("latin1");
    for (const term of banned) {
      assert(!ascii.includes(term), `${name} contains banned string ${term}`);
    }
  }
}

function assertDistinct(dir) {
  const hashes = new Map();
  for (const name of REQUIRED) {
    const file = join(dir, name);
    assert(statSync(file).isFile(), `missing ${name}`);
    const digest = createHash("sha256").update(readFileSync(file)).digest("hex");
    if (hashes.has(digest)) {
      throw new Error(`duplicate screenshots: ${hashes.get(digest)} and ${name}`);
    }
    hashes.set(digest, name);
  }
  return Object.fromEntries([...hashes.entries()].map(([h, n]) => [n, h]));
}

mkdirSync(outDir, { recursive: true });
assert(statSync(join(dist, "index.html")).isFile(), "web/dist missing — run scripts/build_web.sh first");

const chromium = loadChromium();
const { server, base } = await startStaticServer();
const browser = await chromium.launch({ args: ["--no-sandbox"] });

try {
  await shot(browser, base, "home-mobile.png", 390, 844);
  await shot(browser, base, "home-desktop.png", 1440, 900);
  await shot(browser, base, "register-mobile.png", 390, 844, showRegisterScan);
  await shot(browser, base, "register-desktop.png", 1440, 900, showRegisterScan);
  await shot(browser, base, "manage-mobile.png", 390, 844, showManage);
  await shot(browser, base, "manage-desktop.png", 1440, 900, showManage);
  await shot(browser, base, "catalog-import-mobile.png", 390, 844, showCatalogImport);
  await shot(browser, base, "catalog-import-desktop.png", 1440, 900, showCatalogImport);
} finally {
  await browser.close();
  server.close();
}

for (const name of REQUIRED) {
  optimizePng(join(outDir, name));
}

assertNoBannedPixels(outDir);
const hashMap = assertDistinct(outDir);
writeFileSync(
  join(outDir, "SHA256SUMS.json"),
  JSON.stringify({ generatedAt: new Date().toISOString(), sha256: hashMap }, null, 2) + "\n",
);
console.log("README screenshots complete");

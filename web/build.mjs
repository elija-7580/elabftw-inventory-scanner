import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync, rmSync, cpSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
const distJs = join(dist, "js");
mkdirSync(distJs, { recursive: true });

const tmpOut = join(distJs, "scanner-app.tmp.js");
await esbuild.build({
  entryPoints: [join(root, "src", "scanner-app.js")],
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["safari15", "ios15", "chrome100"],
  outfile: tmpOut,
  minify: true,
  sourcemap: true,
  legalComments: "none",
});

const bundleBytes = readFileSync(tmpOut);
const hash = createHash("sha256").update(bundleBytes).digest("hex").slice(0, 12);
const bundleName = `scanner-app.${hash}.js`;
const bundlePath = join(distJs, bundleName);
writeFileSync(bundlePath, bundleBytes);
rmSync(tmpOut);

const mapTmp = `${tmpOut}.map`;
const mapPath = `${bundlePath}.map`;
try {
  const mapBytes = readFileSync(mapTmp);
  writeFileSync(mapPath, mapBytes);
  rmSync(mapTmp);
} catch (_) {
  // source map optional
}

const brandName =
  (process.env.BRAND_PRODUCT_NAME || "Inventory Scanner").trim() || "Inventory Scanner";
const brandEndorsement = (process.env.BRAND_ENDORSEMENT || "").trim();
let brandAccent = (process.env.BRAND_ACCENT_HEX || "#29ADB9").trim();
if (!brandAccent.startsWith("#")) brandAccent = `#${brandAccent}`;

const template = readFileSync(join(root, "index.template.html"), "utf8");
// Relative path so the bundle resolves under Caddy handle_path /scanner/*.
const bundleRef = `js/${bundleName}`;
const html = template
  .replaceAll("__SCANNER_BUNDLE__", bundleRef)
  .replaceAll("__BRAND_PRODUCT_NAME__", brandName)
  .replaceAll("__BRAND_ENDORSEMENT__", brandEndorsement)
  .replaceAll("__BRAND_ACCENT_HEX__", brandAccent.toUpperCase());
writeFileSync(join(dist, "index.html"), html, "utf8");

// Tokens + brand + OFL fonts (visual assets only).
for (const name of ["tokens.css", "brand", "fonts"]) {
  const src = join(root, name);
  if (!existsSync(src)) continue;
  const dest = join(dist, name);
  if (name.endsWith(".css")) {
    writeFileSync(dest, readFileSync(src));
  } else {
    cpSync(src, dest, { recursive: true });
  }
}

const manifest = {
  bundle: bundleRef,
  hash,
  builtAt: new Date().toISOString(),
};
writeFileSync(join(dist, "build-manifest.json"), JSON.stringify(manifest, null, 2));

console.log(`built ${bundleName} (${bundleBytes.length} bytes)`);

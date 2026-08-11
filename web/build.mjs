import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import esbuild from "esbuild";

const root = dirname(fileURLToPath(import.meta.url));
const distJs = join(root, "dist", "js");
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

const template = readFileSync(join(root, "index.template.html"), "utf8");
// Relative path so the bundle resolves under Caddy handle_path /scanner/*.
const bundleRef = `js/${bundleName}`;
const html = template.replace("__SCANNER_BUNDLE__", bundleRef);
writeFileSync(join(root, "dist", "index.html"), html, "utf8");

const manifest = {
  bundle: bundleRef,
  hash,
  builtAt: new Date().toISOString(),
};
writeFileSync(join(root, "dist", "build-manifest.json"), JSON.stringify(manifest, null, 2));

console.log(`built ${bundleName} (${bundleBytes.length} bytes)`);

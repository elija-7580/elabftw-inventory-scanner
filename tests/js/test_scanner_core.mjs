#!/usr/bin/env node
/** Node smoke tests for scanner-core ES module. */
import {
  nativeCoversRequired,
  resolveScannerBackend,
  shouldSuppressDuplicate,
  applyDetectedScan,
  acceptDetection,
  mapCameraError,
  releaseMediaTracks,
  unsupportedFormatsMessage,
  TARGET_FORMATS,
  buildCameraConstraints,
  readTrackCapabilities,
  canUseZoom,
  canUseTorch,
  clampZoom,
  applyContinuousFocus,
  resolveApiBase,
  isSmallCodeDebugEnabled,
  buildSmallCodeDiagnostics,
  IDEAL_VIDEO_WIDTH,
  IDEAL_VIDEO_HEIGHT,
} from "../../web/src/scanner-core.js";

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

assert(nativeCoversRequired(["code_128", "ean_13", "qr_code", "data_matrix"]));
assert(!nativeCoversRequired(["code_128", "ean_13", "qr_code"]));

assert(
  resolveScannerBackend({
    hasNative: true,
    nativeFormats: ["code_128", "ean_13", "qr_code", "data_matrix"],
    polyfillAvailable: false,
  }) === "native",
);
assert(
  resolveScannerBackend({
    hasNative: true,
    nativeFormats: ["code_128", "ean_13", "qr_code"],
    polyfillAvailable: true,
  }) === "polyfill",
);

const now = Date.now();
assert(shouldSuppressDuplicate("abc", "abc", now - 500, now));
assert(!shouldSuppressDuplicate("abc", "abc", now - 3000, now));

const applied = applyDetectedScan("  4006381333931 ", "ean_13");
assert(applied.value === "4006381333931");

const accepted = acceptDetection("XYZ", "qr_code", null, null);
assert(accepted.accepted && accepted.stopScanner);
const suppressed = acceptDetection("XYZ", "qr_code", "XYZ", now - 100, now);
assert(!suppressed.accepted && suppressed.suppressed);

assert(mapCameraError("NotAllowedError") === "camera permission denied");

const tracks = [{}, { stopped: true }];
assert(releaseMediaTracks(tracks) === 1);
let stoppedCalls = 0;
assert(
  releaseMediaTracks([
    {
      stop() {
        stoppedCalls += 1;
      },
    },
  ]) === 1,
);
assert(stoppedCalls === 1);

const msg = unsupportedFormatsMessage(TARGET_FORMATS, ["qr_code"]);
assert(msg && msg.includes("code_128"));

const constraints = buildCameraConstraints();
assert(constraints.video.facingMode.ideal === "environment");
assert(constraints.video.width.ideal === IDEAL_VIDEO_WIDTH);
assert(constraints.video.height.ideal === IDEAL_VIDEO_HEIGHT);

const emptyCaps = readTrackCapabilities(null);
assert(!canUseZoom(emptyCaps));
assert(!canUseTorch(emptyCaps));
assert(clampZoom(2, emptyCaps) === null);
assert(applyContinuousFocus(null, emptyCaps) === false);

const zoomCaps = {
  focusMode: ["continuous"],
  zoom: { min: 1, max: 5, step: 0.5 },
  torch: true,
};
assert(canUseZoom(zoomCaps));
assert(canUseTorch(zoomCaps));
assert(clampZoom(9, zoomCaps) === 5);
assert(clampZoom(0.2, zoomCaps) === 1);

let focusApplied = false;
assert(
  applyContinuousFocus(
    {
      applyConstraints() {
        focusApplied = true;
        return Promise.resolve();
      },
    },
    zoomCaps,
  ),
);
assert(focusApplied);

const fakeDoc = {
  getAttribute(name) {
    return name === "data-scanner-api-base" ? "/scanner" : null;
  },
};
assert(resolveApiBase(fakeDoc) === "/scanner");
assert(isSmallCodeDebugEnabled("?scanner_debug=1"));
assert(!isSmallCodeDebugEnabled("?foo=1"));

const diag = buildSmallCodeDiagnostics({
  cameraLabel: "cam",
  videoWidth: 1920,
  videoHeight: 1080,
  formats: TARGET_FORMATS,
  capabilities: zoomCaps,
  backend: "native",
  decodeMs: 12,
});
assert(diag.decoderPath === "native");
assert(diag.torch === true);
assert(!("decodedValue" in diag));

console.log("scanner-core.js tests passed");

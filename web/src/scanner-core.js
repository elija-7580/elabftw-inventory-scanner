/**
 * Scanner detection helpers (keep in sync with scanner_detect.py).
 */
export const TARGET_FORMATS = [
  "code_128",
  "ean_13",
  "ean_8",
  "qr_code",
  "data_matrix",
  "upc_a",
  "upc_e",
];
export const REQUIRED_FORMATS = ["code_128", "ean_13", "qr_code", "data_matrix"];
export const SUPPORTED_FORMATS = TARGET_FORMATS;
export const DEFAULT_DUPLICATE_COOLDOWN_MS = 750;
export const MAX_SCAN_VALUE_LENGTH = 512;
export const IDEAL_VIDEO_WIDTH = 1920;
export const IDEAL_VIDEO_HEIGHT = 1080;
export const NATIVE_SCAN_INTERVAL_MS = 120;

export function nativeCoversRequired(runtimeFormats) {
  if (!runtimeFormats || !runtimeFormats.length) return false;
  return REQUIRED_FORMATS.every((f) => runtimeFormats.includes(f));
}

export function resolveScannerBackend({ hasNative, nativeFormats, polyfillAvailable }) {
  if (hasNative && nativeCoversRequired(nativeFormats)) return "native";
  if (polyfillAvailable) return "polyfill";
  return "unavailable";
}

export function shouldSuppressDuplicate(value, lastValue, lastAtMs, nowMs, cooldownMs) {
  const cooldown = cooldownMs == null ? DEFAULT_DUPLICATE_COOLDOWN_MS : cooldownMs;
  if (!value || !lastValue || value !== lastValue || lastAtMs == null) return false;
  const now = nowMs == null ? Date.now() : nowMs;
  return now - lastAtMs < cooldown;
}

export function validateScanValue(rawValue, maxLength) {
  const limit = maxLength == null ? MAX_SCAN_VALUE_LENGTH : maxLength;
  const value = String(rawValue || "").trim();
  if (!value) throw new Error("empty scan value");
  if (value.length > limit) throw new Error("scan value exceeds " + limit + " characters");
  return value;
}

export function applyDetectedScan(rawValue, symbology) {
  const value = validateScanValue(rawValue);
  return { value, symbology: symbology || "unknown" };
}

export function unsupportedFormatsMessage(supported, runtimeFormats) {
  if (!runtimeFormats) return null;
  const missing = supported.filter((f) => !runtimeFormats.includes(f));
  if (!missing.length) return null;
  return "Unsupported in this browser: " + missing.join(", ");
}

export function mapCameraError(name, message) {
  const mapping = {
    NotAllowedError: "camera permission denied",
    NotFoundError: "no camera available",
    NotReadableError: "camera already in use",
    AbortError: "camera stream interrupted",
    SecurityError: "insecure context — HTTPS required",
    OverconstrainedError: "no camera available",
  };
  if (name && mapping[name]) return mapping[name];
  return message || "unexpected camera error";
}

export function acceptDetection(rawValue, symbology, lastValue, lastAtMs, nowMs) {
  try {
    const result = applyDetectedScan(rawValue, symbology);
    if (shouldSuppressDuplicate(result.value, lastValue, lastAtMs, nowMs)) {
      return { accepted: false, stopScanner: false, suppressed: true };
    }
    return {
      accepted: true,
      stopScanner: true,
      value: result.value,
      symbology: result.symbology,
    };
  } catch (err) {
    return { accepted: false, stopScanner: false, error: err.message };
  }
}

export function parseContainerReference(raw) {
  const value = String(raw || "").trim();
  if (!value) return null;
  const m = value.match(/\/scanner\/container\/(\d+)/i) || value.match(/^container:(\d+)$/i);
  if (m) return m[1];
  if (/^\d+$/.test(value)) return value;
  return null;
}

export function releaseMediaTracks(tracks) {
  let stopped = 0;
  (tracks || []).forEach((track) => {
    if (track && typeof track.stop === "function") {
      try {
        track.stop();
      } catch (_) {}
      stopped += 1;
      return;
    }
    if (track && track.stopped) return;
    if (track) {
      track.stopped = true;
      stopped += 1;
    }
  });
  return stopped;
}

/** Build getUserMedia constraints with soft high-res ideals (never hard requirements). */
export function buildCameraConstraints(overrides) {
  const video = {
    facingMode: { ideal: "environment" },
    width: { ideal: IDEAL_VIDEO_WIDTH },
    height: { ideal: IDEAL_VIDEO_HEIGHT },
  };
  return { audio: false, video: Object.assign(video, overrides || {}) };
}

/**
 * Read MediaTrackCapabilities safely. Missing APIs return empty capability flags.
 */
export function readTrackCapabilities(track) {
  const empty = {
    focusMode: [],
    zoom: null,
    torch: false,
    width: null,
    height: null,
  };
  if (!track || typeof track.getCapabilities !== "function") {
    return empty;
  }
  try {
    const caps = track.getCapabilities() || {};
    return {
      focusMode: Array.isArray(caps.focusMode) ? caps.focusMode : [],
      zoom:
        caps.zoom && typeof caps.zoom === "object"
          ? {
              min: Number(caps.zoom.min),
              max: Number(caps.zoom.max),
              step: Number(caps.zoom.step || 0.1),
            }
          : null,
      torch: Boolean(caps.torch),
      width: caps.width || null,
      height: caps.height || null,
    };
  } catch (_) {
    return empty;
  }
}

export function applyContinuousFocus(track, capabilities) {
  const modes = (capabilities && capabilities.focusMode) || [];
  if (!modes.includes("continuous")) return false;
  if (!track || typeof track.applyConstraints !== "function") return false;
  try {
    const result = track.applyConstraints({ advanced: [{ focusMode: "continuous" }] });
    if (result && typeof result.catch === "function") result.catch(() => {});
    return true;
  } catch (_) {
    return false;
  }
}

export function canUseZoom(capabilities) {
  return Boolean(capabilities && capabilities.zoom && capabilities.zoom.max > capabilities.zoom.min);
}

export function canUseTorch(capabilities) {
  return Boolean(capabilities && capabilities.torch);
}

export function clampZoom(value, capabilities) {
  if (!canUseZoom(capabilities)) return null;
  const { min, max } = capabilities.zoom;
  const n = Number(value);
  if (!Number.isFinite(n)) return min;
  return Math.min(max, Math.max(min, n));
}

/** Preserve API base under /scanner/ when building relative paths. */
export function resolveApiBase(doc) {
  const root = doc || (typeof document !== "undefined" ? document.documentElement : null);
  const attr = root && root.getAttribute ? root.getAttribute("data-scanner-api-base") : null;
  if (attr && attr.trim()) return attr.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location && window.location.pathname) {
    const path = window.location.pathname;
    if (path === "/scanner" || path.startsWith("/scanner/")) return "/scanner";
  }
  return "";
}

export function isSmallCodeDebugEnabled(search) {
  const q =
    search == null
      ? typeof window !== "undefined"
        ? window.location.search
        : ""
      : search;
  return /(?:\?|&)scanner_debug=1(?:&|$)/.test(String(q || ""));
}

export function buildSmallCodeDiagnostics({
  cameraLabel,
  videoWidth,
  videoHeight,
  formats,
  capabilities,
  backend,
  decodeMs,
}) {
  return {
    cameraLabel: cameraLabel || "",
    videoResolution: {
      width: videoWidth || 0,
      height: videoHeight || 0,
    },
    supportedFormats: formats || [],
    focusModes: (capabilities && capabilities.focusMode) || [],
    zoom: canUseZoom(capabilities) ? capabilities.zoom : null,
    torch: canUseTorch(capabilities),
    decoderPath: backend || "unknown",
    decodeTimingMs: decodeMs == null ? null : decodeMs,
  };
}

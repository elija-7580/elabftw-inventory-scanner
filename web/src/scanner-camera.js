/**
 * Camera barcode scanner: native BarcodeDetector with bundled ZXing fallback.
 * Soft high-res constraints; zoom/torch/focus only when MediaTrackCapabilities allow.
 */
import {
  BrowserMultiFormatReader,
  BarcodeFormat,
} from "@zxing/browser";
import { DecodeHintType } from "@zxing/library";
import * as Core from "./scanner-core.js";

export class CameraScanner {
  constructor({
    videoEl,
    statusEl,
    symbologyEl,
    detectedEl,
    onResult,
    onError,
    keepScanning,
    controlsEl,
    debugEl,
  }) {
    this.videoEl = videoEl;
    this.statusEl = statusEl;
    this.symbologyEl = symbologyEl;
    this.detectedEl = detectedEl;
    this.controlsEl = controlsEl || null;
    this.debugEl = debugEl || null;
    this.onResult = onResult;
    this.onError = onError || (() => {});
    this.keepScanning = Boolean(keepScanning);
    this.stream = null;
    this.track = null;
    this.running = false;
    this.paused = false;
    this.loopTimer = null;
    this.detector = null;
    this.backend = "unavailable";
    this.zxingControls = null;
    this.lastValue = null;
    this.lastAtMs = null;
    this._nativeFormats = null;
    this._unsupportedNote = null;
    this._zxingReader = null;
    this._capabilities = null;
    this._debug = Core.isSmallCodeDebugEnabled();
    this._lastDecodeMs = null;
    this._onVisibility = this._onVisibility.bind(this);
    document.addEventListener("visibilitychange", this._onVisibility);
  }

  _setStatus(msg, isError) {
    if (!this.statusEl) return;
    this.statusEl.textContent = msg;
    this.statusEl.className = isError ? "scan-status err" : "scan-status";
  }

  _setSymbology(msg) {
    if (this.symbologyEl) {
      this.symbologyEl.textContent = msg ? "Type: " + msg : "";
    }
  }

  _setDetected(msg) {
    if (this.detectedEl) {
      // Never put decoded product codes into debug panels by default.
      this.detectedEl.textContent = msg ? "Value: " + msg : "";
    }
  }

  async _probeNative() {
    if (!("BarcodeDetector" in window)) {
      return { available: false, formats: null };
    }
    try {
      const formats = await window.BarcodeDetector.getSupportedFormats();
      this._nativeFormats = formats;
      this._unsupportedNote = Core.unsupportedFormatsMessage(
        [...Core.TARGET_FORMATS],
        formats,
      );
      return { available: true, formats };
    } catch (err) {
      console.warn("BarcodeDetector probe failed", err);
      return { available: false, formats: null };
    }
  }

  _zxingAvailable() {
    return Boolean(BrowserMultiFormatReader);
  }

  async _initBackend() {
    const native = await this._probeNative();
    const polyfillAvailable = this._zxingAvailable();
    if (!native.available && !polyfillAvailable) {
      throw new Error("BarcodeDetector unsupported and fallback unavailable");
    }
    this.backend = Core.resolveScannerBackend({
      hasNative: native.available,
      nativeFormats: native.formats,
      polyfillAvailable,
    });
    if (this.backend === "native") {
      this.detector = new window.BarcodeDetector({ formats: Core.TARGET_FORMATS });
      const note = this._unsupportedNote ? " (" + this._unsupportedNote + ")" : "";
      this._setStatus("Scanner ready (native BarcodeDetector)" + note);
    } else if (this.backend === "polyfill") {
      this._setStatus("Scanner ready (ZXing fallback — formats may vary by browser)");
    } else if (native.available) {
      throw new Error("required native formats unsupported; fallback unavailable");
    } else {
      throw new Error("BarcodeDetector unsupported and fallback unavailable");
    }
  }

  _renderControls() {
    if (!this.controlsEl) return;
    this.controlsEl.innerHTML = "";
    const caps = this._capabilities || Core.readTrackCapabilities(null);
    const showZoom = Core.canUseZoom(caps);
    const showTorch = Core.canUseTorch(caps);
    if (!showZoom && !showTorch) {
      this.controlsEl.hidden = true;
      return;
    }
    this.controlsEl.hidden = false;
    if (showZoom) {
      const label = document.createElement("label");
      label.className = "scan-control-label";
      label.textContent = "Zoom";
      const input = document.createElement("input");
      input.type = "range";
      input.min = String(caps.zoom.min);
      input.max = String(caps.zoom.max);
      input.step = String(caps.zoom.step || 0.1);
      input.value = String(caps.zoom.min);
      input.addEventListener("input", () => {
        const zoom = Core.clampZoom(input.value, caps);
        if (zoom == null || !this.track) return;
        this.track.applyConstraints({ advanced: [{ zoom }] }).catch(() => {});
      });
      label.appendChild(input);
      this.controlsEl.appendChild(label);
    }
    if (showTorch) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "secondary";
      btn.textContent = "Torch";
      let on = false;
      btn.addEventListener("click", () => {
        if (!this.track) return;
        on = !on;
        this.track
          .applyConstraints({ advanced: [{ torch: on }] })
          .then(() => {
            btn.textContent = on ? "Torch on" : "Torch";
          })
          .catch(() => {
            on = false;
            btn.textContent = "Torch";
          });
      });
      this.controlsEl.appendChild(btn);
    }
  }

  _renderDebug() {
    if (!this._debug || !this.debugEl) return;
    const settings =
      this.track && typeof this.track.getSettings === "function"
        ? this.track.getSettings()
        : {};
    const diag = Core.buildSmallCodeDiagnostics({
      cameraLabel: settings.label || settings.deviceId || "",
      videoWidth: this.videoEl?.videoWidth,
      videoHeight: this.videoEl?.videoHeight,
      formats: this._nativeFormats || Core.TARGET_FORMATS,
      capabilities: this._capabilities,
      backend: this.backend,
      decodeMs: this._lastDecodeMs,
    });
    this.debugEl.hidden = false;
    this.debugEl.textContent = JSON.stringify(diag, null, 2);
  }

  async start() {
    if (this.running) return;
    if (!window.isSecureContext) {
      throw new Error("insecure context — HTTPS required");
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("browser camera API unavailable");
    }
    this._setDetected("");
    this._setSymbology("");
    await this._initBackend();
    try {
      this.stream = await navigator.mediaDevices.getUserMedia(Core.buildCameraConstraints());
    } catch (err) {
      // Retry without soft advanced ideals if the first attempt fails.
      try {
        this.stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: { facingMode: { ideal: "environment" } },
        });
      } catch (err2) {
        throw new Error(Core.mapCameraError(err2 && err2.name, err2 && err2.message));
      }
    }
    this.track = this.stream.getVideoTracks()[0] || null;
    this._capabilities = Core.readTrackCapabilities(this.track);
    Core.applyContinuousFocus(this.track, this._capabilities);
    this._renderControls();
    this.videoEl.srcObject = this.stream;
    await this.videoEl.play();
    this.running = true;
    this.paused = false;
    this._setStatus("Ready to scan");
    this._renderDebug();
    if (this.backend === "native") {
      this._startNativeLoop();
    } else {
      await this._startZxingLoop();
    }
  }

  _handleDetection(rawValue, symbology) {
    const decision = Core.acceptDetection(
      rawValue,
      symbology,
      this.lastValue,
      this.lastAtMs,
    );
    if (!decision.accepted) return;
    this.lastValue = decision.value;
    this.lastAtMs = Date.now();
    this._setSymbology(decision.symbology);
    this._setDetected(decision.value);
    this._setStatus("Detected: " + decision.value);
    this.onResult({ value: decision.value, symbology: decision.symbology });
    if (!this.keepScanning) {
      this.stop();
    }
  }

  _startNativeLoop() {
    const tick = async () => {
      if (!this.running || this.paused || !this.detector) return;
      const t0 = performance.now();
      try {
        // Decode from the displayed video element (center region via CSS guide only —
        // avoid aggressive canvas cropping that drops normal codes).
        const codes = await this.detector.detect(this.videoEl);
        this._lastDecodeMs = Math.round(performance.now() - t0);
        if (this._debug) this._renderDebug();
        if (codes && codes.length) {
          const c = codes[0];
          this._handleDetection(c.rawValue, c.format || "unknown");
          return;
        }
      } catch (err) {
        console.warn("native detect error", err);
      }
      this.loopTimer = window.setTimeout(tick, Core.NATIVE_SCAN_INTERVAL_MS);
    };
    tick();
  }

  async _startZxingLoop() {
    const hints = new Map();
    hints.set(DecodeHintType.POSSIBLE_FORMATS, [
      BarcodeFormat.EAN_13,
      BarcodeFormat.EAN_8,
      BarcodeFormat.CODE_128,
      BarcodeFormat.QR_CODE,
      BarcodeFormat.DATA_MATRIX,
      BarcodeFormat.UPC_A,
      BarcodeFormat.UPC_E,
    ]);
    hints.set(DecodeHintType.TRY_HARDER, true);
    this._zxingReader = new BrowserMultiFormatReader(hints, 200);
    this.zxingControls = await this._zxingReader.decodeFromVideoElement(
      this.videoEl,
      (result, err) => {
        if (!this.running || this.paused) return;
        if (result) {
          const sym = result.getBarcodeFormat
            ? String(result.getBarcodeFormat())
            : "unknown";
          this._handleDetection(result.getText(), sym);
        }
        if (err && err.name !== "NotFoundException") {
          console.warn("zxing decode", err);
        }
      },
    );
  }

  _onVisibility() {
    if (!this.running) return;
    if (document.hidden) {
      this.paused = true;
      this._setStatus("Scanner paused (page hidden)");
    } else if (this.paused) {
      this.paused = false;
      this._setStatus("Ready to scan");
    }
  }

  stop() {
    this.running = false;
    this.paused = false;
    if (this.loopTimer) {
      clearTimeout(this.loopTimer);
      this.loopTimer = null;
    }
    if (this.zxingControls && this.zxingControls.stop) {
      try {
        this.zxingControls.stop();
      } catch (_) {}
      this.zxingControls = null;
    }
    if (this.stream) {
      Core.releaseMediaTracks(this.stream.getTracks());
      this.stream = null;
    }
    this.track = null;
    if (this.videoEl) this.videoEl.srcObject = null;
    if (this.controlsEl) {
      this.controlsEl.innerHTML = "";
      this.controlsEl.hidden = true;
    }
    if (this.statusEl && !this.statusEl.classList.contains("err")) {
      const txt = this.statusEl.textContent || "";
      if (!txt.startsWith("Detected:")) {
        this._setStatus("Camera stopped");
      }
    }
  }

  destroy() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    this.stop();
  }
}

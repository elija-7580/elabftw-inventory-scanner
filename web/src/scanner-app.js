/**
 * Inventory Scanner beta UI — context, forms, API integration.
 */
import { CameraScanner } from "./scanner-camera.js";
import { parseContainerReference, resolveApiBase } from "./scanner-core.js";

const PACK_UNITS = ["g", "mg", "µg", "kg", "ml", "µl", "L", "pcs"];
const CATALOG_FIELDS = [
  { id: "reg-mfg", key: "manufacturer", sourceId: "reg-mfg-source" },
  { id: "reg-cat", key: "catalog_number", sourceId: "reg-cat-source" },
  { id: "reg-name", key: "product_name", sourceId: "reg-name-source" },
  { id: "reg-cas", key: "cas_number", sourceId: "reg-cas-source" },
];
const state = {
  mode: null,
  options: null,
  config: null,
  context: { storage_id: null, category_id: null },
  loadedContainer: null,
  catalogFile: null,
  catalogPreview: null,
  catalogMapping: {},
  fieldTouched: {},
};

let regScanner = null;
let mgrScanner = null;
let initAttempts = 0;

function $(id) {
  return document.getElementById(id);
}

function show(id) {
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  $(id)?.classList.add("active");
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    const target = btn.getAttribute("data-nav");
    if (target === id || (id === "context" && target === state.mode)) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  });
  if (id === "home") {
    const homeNav = $("nav-home");
    if (homeNav) homeNav.setAttribute("aria-current", "page");
  }
  if (id === "manage") {
    updateManageEmptyState();
  }
  window.scrollTo(0, 0);
}

function setStatusBox(el, text, kind) {
  if (!el) return;
  if (!text) {
    el.hidden = true;
    return;
  }
  el.hidden = false;
  el.className = "status " + (kind || "info");
  const title = el.querySelector(".status-title");
  const body = el.querySelector(".status-body");
  if (title && body) {
    title.textContent = text;
    body.textContent = "";
  } else {
    el.textContent = text;
  }
}

function showBanner(text, kind) {
  // Persistent read-only uses dedicated bar; banner is for blocking errors only.
  if (!text) {
    setStatusBox($("status-banner"), "", kind);
    return;
  }
  setStatusBox($("status-banner"), text, kind || "warn");
}

function setMsg(id, text, kind) {
  setStatusBox($(id), text, kind || "info");
}

function applyReadOnlyUi(enabledWrites) {
  const bar = $("readonly-bar");
  if (bar) bar.classList.toggle("visible", !enabledWrites);
  ["reg-confirm", "mgr-apply", "cat-commit"].forEach((id) => {
    const btn = $(id);
    if (!btn) return;
    if (!enabledWrites) {
      btn.disabled = true;
      btn.dataset.readonlyLocked = "1";
    } else if (btn.dataset.readonlyLocked === "1" && id !== "cat-commit") {
      btn.disabled = false;
      delete btn.dataset.readonlyLocked;
    }
  });
  const regHint = $("reg-readonly-hint");
  const mgrHint = $("mgr-readonly-hint");
  const catHint = $("cat-readonly-hint");
  if (regHint) regHint.hidden = enabledWrites;
  if (mgrHint) mgrHint.hidden = enabledWrites;
  if (catHint) catHint.hidden = enabledWrites;
}

function updateManageEmptyState() {
  const empty = $("mgr-empty");
  if (!empty) return;
  empty.hidden = Boolean(state.loadedContainer);
}

function setImportStep(step) {
  document.querySelectorAll("[data-step-indicator]").forEach((el) => {
    const n = Number(el.getAttribute("data-step-indicator"));
    if (n === step) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
}

function sanitizeError(err) {
  const msg = err && err.message ? String(err.message) : "unknown error";
  const cleaned = msg.replace(/https?:\/\/\S+/g, "[url]").replace(/<[^>]+>/g, "");
  return cleaned.slice(0, 200);
}

function scannerApiBase() {
  return resolveApiBase(document.documentElement);
}

function extractApiError(status, text, body, url) {
  if (body && body.detail) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    return `${detail} (${url}, ${status})`;
  }
  if (/^\s*<!DOCTYPE/i.test(text) || /^\s*<html/i.test(text)) {
    if (status === 401 || status === 403) {
      return `Session expired — please log in again. (${url}, ${status})`;
    }
    return `Server error (${status}) at ${url}`;
  }
  const snippet = (text || "").replace(/<[^>]+>/g, "").trim().slice(0, 80);
  return `${snippet || "Request failed"} (${url}, ${status})`;
}

async function apiJson(path, options) {
  const apiPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${scannerApiBase()}${apiPath}`;
  const r = await fetch(url, {
    credentials: "same-origin",
    redirect: "manual",
    ...options,
    headers: {
      Accept: "application/json",
      ...(options?.headers || {}),
    },
  });
  if (r.type === "opaqueredirect" || r.status === 301 || r.status === 302) {
    throw new Error("Session expired — please log in again.");
  }
  const ct = (r.headers.get("content-type") || "").toLowerCase();
  const text = await r.text();
  let body = null;
  if (text && ct.includes("application/json")) {
    try {
      body = JSON.parse(text);
    } catch (_) {
      body = null;
    }
  }
  if (!r.ok) {
    throw new Error(extractApiError(r.status, text, body, url));
  }
  if (body !== null) return body;
  if (!text) return null;
  if (ct.includes("application/json")) {
    try {
      return JSON.parse(text);
    } catch (_) {
      throw new Error("Invalid JSON response from server");
    }
  }
  throw new Error(extractApiError(r.status, text, body, url));
}

function fillSelect(select, items, { valueKey, labelKey, placeholder, selectedId }) {
  if (!select) return;
  select.innerHTML = "";
  if (placeholder) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder;
    select.appendChild(opt);
  }
  (items || []).forEach((item) => {
    const opt = document.createElement("option");
    opt.value = String(item[valueKey]);
    opt.textContent = item[labelKey];
    select.appendChild(opt);
  });
  if (selectedId != null) select.value = String(selectedId);
}

function reportOptionsGap(message) {
  showBanner(message, "err");
}

function locationRoots(locs) {
  return locs.filter((l) => l.parent_id == null || l.parent_id === "");
}

function locationChildren(locs, parentId) {
  return locs.filter((l) => String(l.parent_id) === String(parentId));
}

function hasStorageHierarchy(locs) {
  return locs.some((l) => l.parent_id != null && l.parent_id !== "");
}

function resolveLocationSelection(locs, selectedId) {
  if (!selectedId) return { parentId: null, leafId: null };
  const leaf = locs.find((l) => String(l.id) === String(selectedId));
  if (!leaf) return { parentId: null, leafId: selectedId };
  if (leaf.parent_id == null || leaf.parent_id === "") {
    const kids = locationChildren(locs, leaf.id);
    return { parentId: leaf.id, leafId: kids.length ? null : leaf.id };
  }
  return { parentId: leaf.parent_id, leafId: leaf.id };
}

function setupStoragePicker({ locs, parentWrapId, parentSelectId, leafSelectId, placeholder, selectedId }) {
  const parentWrap = $(parentWrapId);
  const parentSel = $(parentSelectId);
  const leafSel = $(leafSelectId);
  if (!leafSel) return;

  if (!hasStorageHierarchy(locs)) {
    if (parentWrap) parentWrap.hidden = true;
    fillSelect(leafSel, locs, {
      valueKey: "id",
      labelKey: "full_path",
      placeholder,
      selectedId,
    });
    return;
  }

  if (parentWrap) parentWrap.hidden = false;
  const roots = locationRoots(locs);
  const picked = resolveLocationSelection(locs, selectedId);

  fillSelect(parentSel, roots, {
    valueKey: "id",
    labelKey: "full_path",
    placeholder: "— Room / zone —",
    selectedId: picked.parentId,
  });

  const syncChildren = () => {
    const pid = parentSel?.value;
    if (!pid) {
      fillSelect(leafSel, [], {
        valueKey: "id",
        labelKey: "full_path",
        placeholder: "— Shelf / location —",
      });
      return;
    }
    const children = locationChildren(locs, pid);
    if (!children.length) {
      const parentLoc = roots.find((r) => String(r.id) === String(pid));
      fillSelect(leafSel, parentLoc ? [parentLoc] : [], {
        valueKey: "id",
        labelKey: "full_path",
        selectedId: pid,
      });
      return;
    }
    fillSelect(leafSel, children, {
      valueKey: "id",
      labelKey: "full_path",
      placeholder: "— Shelf / location —",
      selectedId: picked.leafId,
    });
  };

  if (parentSel) parentSel.onchange = syncChildren;
  syncChildren();
}

function populateOptionSelects() {
  const opts = state.options;
  if (!opts) {
    reportOptionsGap("Storage and categories not loaded — use Retry scanner load.");
    return;
  }
  const locs = opts.locations || [];
  const cats = opts.categories || [];
  if (!cats.length) {
    reportOptionsGap("No resource categories available (expected ids 24–31).");
  }
  if (!locs.length) {
    reportOptionsGap("No storage locations available from eLab.");
  }
  const storageDefault = state.context.storage_id || opts.default_storage_id;
  const catDefault = state.context.category_id || opts.default_category_id;

  setupStoragePicker({
    locs,
    parentWrapId: "ctx-location-parent-wrap",
    parentSelectId: "ctx-location-parent",
    leafSelectId: "ctx-location",
    placeholder: locs.length ? "— No default location —" : "— No locations —",
    selectedId: storageDefault,
  });
  fillSelect($("ctx-category"), cats, {
    valueKey: "id",
    labelKey: "title",
    placeholder: cats.length ? "— Default category —" : "— No categories —",
    selectedId: catDefault,
  });
  setupStoragePicker({
    locs,
    parentWrapId: "reg-storage-parent-wrap",
    parentSelectId: "reg-storage-parent",
    leafSelectId: "reg-storage",
    placeholder: locs.length ? null : "— No locations —",
    selectedId: storageDefault,
  });
  fillSelect($("reg-category"), cats, {
    valueKey: "id",
    labelKey: "title",
    placeholder: cats.length ? null : "— No categories —",
    selectedId: catDefault,
  });
  const mgrUnit = $("mgr-unit");
  if (mgrUnit) {
    const current = mgrUnit.value;
    mgrUnit.innerHTML = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "—";
    mgrUnit.appendChild(blank);
    (opts.pack_units || opts.units || PACK_UNITS).forEach((u) => {
      const opt = document.createElement("option");
      opt.value = u;
      opt.textContent = u;
      mgrUnit.appendChild(opt);
    });
    if (current) mgrUnit.value = current;
  }
}

function packUnitsList() {
  return state.options?.pack_units || state.options?.units || PACK_UNITS;
}

function packUnitSelectHtml(selected) {
  let html = '<option value="">— unit —</option>';
  packUnitsList().forEach((u) => {
    html += '<option value="' + u + '"' + (selected === u ? " selected" : "") + ">" + u + "</option>";
  });
  return html;
}

function formatPackPreview(amount, unit) {
  if (!amount || !unit) return "Amount and unit required";
  return amount + " " + unit;
}

function readPackLines() {
  const rows = document.querySelectorAll("#reg-pack-lines .pack-line");
  return Array.from(rows).map((row) => ({
    amount_per_container: parseFloat(row.querySelector(".pack-amount")?.value) || 0,
    unit: (row.querySelector(".pack-unit")?.value || "").trim(),
  }));
}

function updatePackLineLabels() {
  document.querySelectorAll("#reg-pack-lines .pack-line").forEach((row, index) => {
    const label = row.querySelector(".pack-line-label");
    const amount = row.querySelector(".pack-amount")?.value || "";
    const unit = row.querySelector(".pack-unit")?.value || "";
    if (label) {
      label.textContent = "Container " + (index + 1) + ": " + formatPackPreview(amount, unit);
    }
  });
}

function addPackLine() {
  const host = $("reg-pack-lines");
  if (!host) return;
  const index = host.querySelectorAll(".pack-line").length;
  const row = document.createElement("div");
  row.className = "pack-line";
  row.innerHTML =
    '<div class="pack-line-head">' +
    '<span class="pack-line-label">Container ' +
    (index + 1) +
    ": Amount and unit required</span>" +
    '<button type="button" class="pack-remove secondary">Remove</button>' +
    "</div>" +
    '<div class="pack-line-grid">' +
    "<div><label>Amount</label><input class=\"pack-amount\" type=\"number\" min=\"0\" step=\"any\" inputmode=\"decimal\" /></div>" +
    "<div><label>Unit</label><select class=\"pack-unit\">" +
    packUnitSelectHtml("") +
    "</select></div>" +
    "</div>";
  host.appendChild(row);
  row.querySelector(".pack-remove").onclick = () => {
    if (host.querySelectorAll(".pack-line").length <= 1) return;
    row.remove();
    updatePackLineLabels();
  };
  row.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("input", updatePackLineLabels);
    el.addEventListener("change", updatePackLineLabels);
  });
  updatePackLineLabels();
}

function initPackLines() {
  const host = $("reg-pack-lines");
  if (!host) return;
  host.innerHTML = "";
  addPackLine();
  const addBtn = $("reg-pack-add");
  if (addBtn) addBtn.onclick = () => addPackLine();
}

function validatePackLines(lines) {
  if (!lines.length) throw new Error("Add at least one container line.");
  lines.forEach((line, index) => {
    const n = index + 1;
    if (!line.unit) throw new Error("Unit required (container " + n + ").");
    const units = packUnitsList();
    if (!units.includes(line.unit)) throw new Error("Invalid unit (container " + n + ").");
    if (!Number.isFinite(line.amount_per_container) || line.amount_per_container <= 0) {
      throw new Error("Amount required (container " + n + ").");
    }
  });
  return lines;
}

function readContextFromForm() {
  const sid = $("ctx-location")?.value;
  const cid = $("ctx-category")?.value;
  state.context.storage_id = sid ? parseInt(sid, 10) : null;
  state.context.category_id = cid ? parseInt(cid, 10) : null;
}

function applyContextToWorkflow() {
  const opts = state.options;
  const chips = [];
  const sid = state.context.storage_id || $("reg-storage")?.value || opts?.default_storage_id;
  const cid = state.context.category_id || $("reg-category")?.value || opts?.default_category_id;
  if (sid && opts) {
    const loc = opts.locations.find((l) => String(l.id) === String(sid));
    if (loc) chips.push("Location: " + loc.full_path);
    if ($("reg-storage")) $("reg-storage").value = String(sid);
  }
  if (cid && opts) {
    const cat = opts.categories.find((c) => String(c.id) === String(cid));
    if (cat) chips.push("Category: " + cat.title);
    if ($("reg-category")) $("reg-category").value = String(cid);
  }
  const html = chips.length
    ? chips.map((c) => '<span class="context-chip">' + c + "</span>").join("")
    : '<span class="context-chip">No preset context</span>';
  ["reg-context-summary", "mgr-context-summary"].forEach((id) => {
    const el = $(id);
    if (el) el.innerHTML = html;
  });
}

function wireScanner(prefix, inputId) {
  const video = $(prefix + "-video");
  const status = $(prefix + "-scan-status");
  const detected = $(prefix + "-scan-detected");
  const sym = $(prefix + "-scan-symbology");
  const startBtn = $(prefix + "-start-scanner");
  const stopBtn = $(prefix + "-stop-scanner");
  const controlsEl = $(prefix + "-scan-controls");
  const debugEl = $(prefix + "-scan-debug");
  const input = $(inputId);
  let scanner = null;

  if (!startBtn || !stopBtn || !video || !status || !input) {
    return { stop: () => {} };
  }

  startBtn.onclick = async () => {
    status.className = "scan-status";
    sym.textContent = "";
    detected.textContent = "";
    try {
      scanner = new CameraScanner({
        videoEl: video,
        statusEl: status,
        detectedEl: detected,
        symbologyEl: sym,
        controlsEl,
        debugEl,
        keepScanning: false,
        onResult: (result) => {
          input.value = result.value;
          input.dispatchEvent(new Event("input", { bubbles: true }));
          if (prefix === "mgr") {
            const cid = parseContainerReference(result.value);
            if (cid) input.value = cid;
          }
          if (prefix === "reg") {
            lookupCatalogForRegister().catch((err) => {
              setMsg("reg-catalog-status", sanitizeError(err), "err");
            });
          }
        },
      });
      startBtn.disabled = true;
      stopBtn.disabled = false;
      await scanner.start();
    } catch (err) {
      status.className = "scan-status err";
      status.textContent = sanitizeError(err);
      startBtn.disabled = false;
      stopBtn.disabled = true;
      scanner?.destroy();
      scanner = null;
    }
  };

  stopBtn.onclick = () => {
    scanner?.destroy();
    scanner = null;
    startBtn.disabled = false;
    stopBtn.disabled = true;
    if (!status.classList.contains("err")) {
      status.className = "scan-status";
      status.textContent = "Camera stopped";
    }
  };

  return {
    stop: () => {
      scanner?.destroy();
      scanner = null;
      startBtn.disabled = false;
      stopBtn.disabled = true;
    },
  };
}

function setFieldSource(sourceId, kind, text) {
  const el = $(sourceId);
  if (!el) return;
  el.className = "field-source " + (kind || "none");
  el.textContent = text || "";
}

function markFieldTouched(fieldId) {
  state.fieldTouched[fieldId] = true;
  $(fieldId)?.classList.add("field-touched");
}

function clearFieldTouched() {
  state.fieldTouched = {};
  CATALOG_FIELDS.forEach(({ id }) => $(id)?.classList.remove("field-touched"));
}

function fillCatalogField(fieldId, value, sourceKind, sourceText) {
  const el = $(fieldId);
  if (!el) return;
  if (state.fieldTouched[fieldId]) return;
  if (value == null || value === "") return;
  el.value = value;
  const meta = CATALOG_FIELDS.find((f) => f.id === fieldId);
  if (meta) setFieldSource(meta.sourceId, sourceKind, sourceText);
}

async function lookupCatalogForRegister() {
  const code = $("reg-raw")?.value || "";
  const j = await apiJson("/api/catalog/lookup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      manufacturer: $("reg-mfg")?.value || "",
      catalogue_number: $("reg-cat")?.value || "",
    }),
  });
  if (j.status === "match" && j.product) {
    const p = j.product;
    const src = "From local catalog";
    fillCatalogField("reg-name", p.product_name, "match", src);
    fillCatalogField("reg-mfg", p.manufacturer, "match", src);
    fillCatalogField("reg-cat", p.catalog_number, "match", src);
    fillCatalogField("reg-cas", p.cas_number, "match", src);
    if (p.category_id && $("reg-category") && !$("reg-category").value) {
      $("reg-category").value = String(p.category_id);
    }
    setMsg("reg-catalog-status", j.message || "Catalog match", "ok");
  } else if (j.status === "conflict") {
    setMsg(
      "reg-catalog-status",
      j.message || "Multiple catalog matches — choose manually",
      "warn",
    );
    CATALOG_FIELDS.forEach(({ sourceId }) => setFieldSource(sourceId, "conflict", "Conflict — enter manually"));
  } else {
    setMsg("reg-catalog-status", j.message || "No catalog match — complete manually", "warn");
    CATALOG_FIELDS.forEach(({ id, sourceId }) => {
      if (!state.fieldTouched[id] && !$(id)?.value) {
        setFieldSource(sourceId, "none", "No catalog match");
      }
    });
  }
  return j;
}

function renderCatalogMapping(headers, suggested) {
  const wrap = $("cat-mapping");
  if (!wrap) return;
  const fields = [
    ["product_name", "Product name"],
    ["manufacturer", "Manufacturer"],
    ["catalog_number", "Catalog number"],
    ["cas_number", "CAS number"],
    ["primary_code", "Primary code"],
    ["alternate_codes", "Alternate codes"],
    ["category_id", "Category"],
  ];
  state.catalogMapping = { ...(suggested || {}) };
  wrap.innerHTML = "";
  fields.forEach(([key, label]) => {
    const row = document.createElement("div");
    row.className = "mapping-row";
    const lab = document.createElement("label");
    lab.textContent = label;
    lab.setAttribute("for", "map-" + key);
    const sel = document.createElement("select");
    sel.id = "map-" + key;
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "— Not mapped —";
    sel.appendChild(empty);
    (headers || []).forEach((h) => {
      const opt = document.createElement("option");
      opt.value = h;
      opt.textContent = h;
      if ((suggested || {})[key] === h) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.onchange = () => {
      state.catalogMapping[key] = sel.value || null;
      if ($("cat-commit") && !state.config?.writes_enabled) {
        $("cat-commit").disabled = true;
      } else if ($("cat-commit")) {
        $("cat-commit").disabled = true;
      }
      setImportStep(2);
    };
    row.appendChild(lab);
    row.appendChild(sel);
    wrap.appendChild(row);
  });
  setImportStep(2);
}

function renderImportSummary(summary) {
  const el = $("cat-summary");
  if (!el || !summary) return;
  el.hidden = false;
  const pairs = [
    ["New", summary.new_products],
    ["Updates", summary.updates],
    ["Duplicates", summary.exact_duplicates],
    ["Conflicts", summary.conflicts],
    ["Errors", summary.error_count],
    ["Blank skipped", summary.blank_rows],
  ];
  el.innerHTML = pairs
    .map(
      ([k, v]) =>
        '<div class="stat"><strong>' +
        (v ?? "—") +
        "</strong><span>" +
        k +
        "</span></div>",
    )
    .join("");
}

async function postCatalogImport(path, confirm) {
  const fileInput = $("cat-file");
  const file = fileInput?.files?.[0];
  if (!file) throw new Error("Choose a CSV or XLSX file first");
  const fd = new FormData();
  fd.append("file", file);
  const sheet = $("cat-sheet")?.value || "";
  if (sheet) fd.append("sheet", sheet);
  fd.append("mapping", JSON.stringify(state.catalogMapping || {}));
  if (confirm) fd.append("confirm", "true");
  const url = `${scannerApiBase()}${path}`;
  const r = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    redirect: "manual",
    body: fd,
    headers: { Accept: "application/json" },
  });
  if (r.type === "opaqueredirect" || r.status === 301 || r.status === 302) {
    throw new Error("Session expired — please log in again.");
  }
  const text = await r.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch (_) {
    body = null;
  }
  if (!r.ok) {
    throw new Error(extractApiError(r.status, text, body, url));
  }
  return body;
}

function registerPayload() {
  const storageRaw = $("reg-storage")?.value;
  const categoryRaw = $("reg-category")?.value;
  return {
    manufacturer: $("reg-mfg").value.trim(),
    catalogue_number: $("reg-cat").value.trim(),
    product_name: $("reg-name").value.trim(),
    original_barcode: $("reg-raw").value.trim(),
    lot_batch: $("reg-lot").value.trim(),
    expiry_date: $("reg-expiry").value,
    cas_number: $("reg-cas")?.value.trim() || "",
    lines: readPackLines(),
    storage_id: storageRaw ? parseInt(storageRaw, 10) : null,
    category_id: categoryRaw ? parseInt(categoryRaw, 10) : null,
  };
}

function requireRegisterLookup() {
  const payload = registerPayload();
  if (!payload.category_id) {
    throw new Error("Category is required — choose a resource category.");
  }
  if (!payload.storage_id) {
    throw new Error("Storage location is required — choose where to store the container.");
  }
  return payload;
}

function requireRegisterPayload() {
  const payload = registerPayload();
  if (!payload.category_id) {
    throw new Error("Category is required — choose a resource category.");
  }
  if (!payload.storage_id) {
    throw new Error("Storage location is required — choose where to store the container.");
  }
  validatePackLines(payload.lines);
  return payload;
}

function fillManageForm(data) {
  state.loadedContainer = data;
  updateManageEmptyState();
  $("mgr-mfg").value = data.manufacturer || "";
  $("mgr-catno").value = data.catalogue_number || "";
  $("mgr-name").value = data.product_name || "";
  $("mgr-lot").value = data.lot_batch || "";
  $("mgr-expiry").value = data.expiry_date || "";
  $("mgr-qty").value = data.qty_stored || "";
  if (data.qty_unit) {
    const mgrUnit = $("mgr-unit");
    if (mgrUnit && !Array.from(mgrUnit.options).some((o) => o.value === data.qty_unit)) {
      const opt = document.createElement("option");
      opt.value = data.qty_unit;
      opt.textContent = data.qty_unit;
      mgrUnit.appendChild(opt);
    }
    if (mgrUnit) mgrUnit.value = data.qty_unit;
  }
  $("mgr-edit").hidden = false;
  $("mgr-detail").hidden = false;
  $("mgr-detail").innerHTML =
    "<h3>" +
    (data.product_name || "Container #" + data.container_id) +
    "</h3>" +
    '<p class="meta">' +
    (data.manufacturer || "—") +
    " · " +
    (data.catalogue_number || "—") +
    "</p>" +
    '<p class="meta code-mono">Container #' +
    data.container_id +
    "</p>" +
    '<p class="path">' +
    (data.full_path || data.storage_name || "unknown location") +
    " · " +
    data.qty_stored +
    " " +
    data.qty_unit +
    "</p>";
}

async function loadBootstrapData() {
  try {
    state.config = await apiJson("/api/config/public");
  } catch (err) {
    state.config = { writes_enabled: false, beta: true };
    showBanner("Could not load scanner config: " + sanitizeError(err), "err");
  }
  applyReadOnlyUi(Boolean(state.config?.writes_enabled));
  try {
    const session = await apiJson("/auth/session");
    const chip = $("user-chip");
    if (chip && session) {
      const label = session.email || session.name || session.sub || "";
      if (label) {
        chip.hidden = false;
        chip.textContent = label;
        chip.title = label;
      }
    }
  } catch (_) {
    // Session chip is optional; auth middleware already gates pages when enabled.
  }
  try {
    state.options = await apiJson("/api/inventory/options");
    populateOptionSelects();
  } catch (err) {
    state.options = null;
    reportOptionsGap("Could not load storage and categories: " + sanitizeError(err));
  }
  if (!state.options) {
    return;
  }
  if (!state.config?.writes_enabled) {
    showBanner("", "");
  } else {
    showBanner("", "");
  }
}

function bindClick(id, handler) {
  const el = $(id);
  if (el) el.onclick = handler;
}

function wireWorkflowButtons() {
  bindClick("btn-register", () => {
    state.mode = "register";
    clearFieldTouched();
    readContextFromForm();
    applyContextToWorkflow();
    show("register");
  });
  bindClick("btn-manage", () => {
    state.mode = "manage";
    state.loadedContainer = null;
    readContextFromForm();
    applyContextToWorkflow();
    show("manage");
  });
  bindClick("btn-catalog-import", () => {
    state.mode = "catalog-import";
    if ($("cat-commit")) $("cat-commit").disabled = true;
    setImportStep(1);
    show("catalog-import");
  });

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-nav");
      if (target === "home") {
        regScanner?.stop();
        mgrScanner?.stop();
        show("home");
        return;
      }
      if (target === "register") $("btn-register")?.click();
      if (target === "manage") $("btn-manage")?.click();
      if (target === "catalog-import") $("btn-catalog-import")?.click();
    });
  });

  bindClick("ctx-skip", () => {
    readContextFromForm();
    applyContextToWorkflow();
    show(state.mode);
  });
  bindClick("ctx-continue", () => {
    readContextFromForm();
    applyContextToWorkflow();
    show(state.mode);
  });

  document.querySelectorAll("[data-back]").forEach((b) => {
    b.onclick = () => {
      regScanner?.stop();
      mgrScanner?.stop();
      show("home");
    };
  });

  bindClick("mgr-empty-scan", () => {
    $("mgr-start-scanner")?.click();
  });

  CATALOG_FIELDS.forEach(({ id, sourceId }) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markFieldTouched(id);
      setFieldSource(sourceId, "manual", "Manually entered");
    });
  });

  bindClick("reg-parse", async () => {
    try {
      const j = await apiJson("/api/scan/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_value: $("reg-raw").value }),
      });
      setMsg("reg-parsed", "Parsed: GTIN " + (j.gtin || "—") + ", lot " + (j.lot || "—"), "warn");
      if (j.lot && !$("reg-lot").value) $("reg-lot").value = j.lot;
      if (j.expiry && !$("reg-expiry").value) $("reg-expiry").value = j.expiry.slice(0, 10);
      await lookupCatalogForRegister();
    } catch (err) {
      setMsg("reg-parsed", sanitizeError(err), "err");
    }
  });

  bindClick("reg-catalog-lookup", async () => {
    setMsg("reg-catalog-status", "", "");
    try {
      await lookupCatalogForRegister();
    } catch (err) {
      setMsg("reg-catalog-status", sanitizeError(err), "err");
    }
  });

  bindClick("reg-lookup", async () => {
    setMsg("reg-lookup-result", "", "");
    try {
      const payload = requireRegisterLookup();
      const j = await apiJson("/api/register/lookup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const msg =
        j.existing_item
          ? "Possible duplicate item found — review before saving."
          : "No exact duplicate found.";
      setMsg("reg-lookup-result", msg, j.existing_item ? "warn" : "ok");
    } catch (err) {
      setMsg("reg-lookup-result", sanitizeError(err), "err");
    }
  });

  bindClick("reg-confirm", async () => {
    setMsg("reg-result", "", "");
    try {
      const payload = requireRegisterPayload();
      const j = await apiJson("/api/register/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const ids = (j.containers || []).map((c) => "#" + c.id).join(", ");
      setMsg(
        "reg-result",
        "Saved item #" + j.item.id + (ids ? " and containers " + ids : ""),
        "ok",
      );
      if ($("reg-save-catalog")?.checked) {
        try {
          await apiJson("/api/catalog/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              product_name: payload.product_name,
              manufacturer: payload.manufacturer,
              catalogue_number: payload.catalogue_number,
              cas_number: payload.cas_number || "",
              primary_code: payload.original_barcode,
              category_id: payload.category_id,
              confirm: true,
            }),
          });
          setMsg(
            "reg-catalog-status",
            "Also saved to local product catalog",
            "ok",
          );
        } catch (catalogErr) {
          setMsg(
            "reg-catalog-status",
            "eLab save ok; catalog save failed: " + sanitizeError(catalogErr),
            "warn",
          );
        }
      }
    } catch (err) {
      setMsg("reg-result", sanitizeError(err), "err");
    }
  });

  bindClick("cat-preview", async () => {
    setMsg("cat-result", "", "");
    if ($("cat-commit")) $("cat-commit").disabled = true;
    try {
      const j = await postCatalogImport("/api/catalog/import/preview", false);
      state.catalogPreview = j;
      renderCatalogMapping(j.headers || [], j.suggested_mapping || j.mapping || {});
      if (j.sheets && j.sheets.length) {
        const sel = $("cat-sheet");
        const current = sel.value;
        sel.innerHTML = '<option value="">— Auto / first sheet —</option>';
        j.sheets.forEach((name) => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          if (name === j.selected_sheet || name === current) opt.selected = true;
          sel.appendChild(opt);
        });
      }
      renderImportSummary(j);
      setImportStep(3);
      const errHint = j.error_count ? " · " + j.error_count + " row issues" : "";
      setMsg(
        "cat-result",
        "Preview complete (zero writes)." + errHint + " Review mapping, then import.",
        j.conflicts || j.error_count ? "warn" : "ok",
      );
      const canCommit = !j.conflicts && !j.error_count && Boolean(state.config?.writes_enabled);
      if ($("cat-commit")) $("cat-commit").disabled = !canCommit;
      if (canCommit) setImportStep(4);
      const hint = $("cat-import-hint");
      if (hint) {
        if (!state.config?.writes_enabled) {
          hint.hidden = true;
        } else {
          hint.hidden = false;
          hint.textContent = canCommit
            ? "Preview succeeded. Commit writes only to the local catalog."
            : "Resolve conflicts/errors before import.";
        }
      }
    } catch (err) {
      setMsg("cat-result", sanitizeError(err), "err");
    }
  });

  bindClick("cat-commit", async () => {
    setMsg("cat-result", "", "");
    if (!state.config?.writes_enabled) {
      setMsg("cat-result", "Import commit is disabled in read-only test mode.", "warn");
      return;
    }
    if (!window.confirm("Commit this catalog import? This writes to the local catalog only (not eLabFTW).")) {
      return;
    }
    try {
      const j = await postCatalogImport("/api/catalog/import/commit", true);
      renderImportSummary(j.summary || j);
      setImportStep(4);
      if (!j.committed) {
        setMsg("cat-result", "Commit blocked: " + (j.reason || "validation failed"), "err");
        $("cat-commit").disabled = true;
        return;
      }
      setMsg(
        "cat-result",
        "Committed: " + (j.applied_new || 0) + " new, " + (j.applied_updates || 0) + " updates",
        "ok",
      );
      $("cat-commit").disabled = true;
    } catch (err) {
      setMsg("cat-result", sanitizeError(err), "err");
    }
  });

  const catFile = $("cat-file");
  if (catFile) {
    catFile.onchange = () => {
      if ($("cat-commit")) $("cat-commit").disabled = true;
      state.catalogPreview = null;
      setImportStep(1);
    };
  }

  bindClick("mgr-load", async () => {
    setMsg("mgr-result", "", "");
    try {
      let id = $("mgr-container-id").value.trim();
      const parsed = parseContainerReference(id);
      if (parsed) id = parsed;
      const j = await apiJson("/api/container/" + encodeURIComponent(id));
      fillManageForm(j);
    } catch (err) {
      state.loadedContainer = null;
      $("mgr-edit").hidden = true;
      $("mgr-detail").hidden = true;
      updateManageEmptyState();
      setMsg("mgr-result", sanitizeError(err), "err");
    }
  });

  bindClick("mgr-apply", async () => {
    if (!state.loadedContainer) return;
    setMsg("mgr-result", "", "");
    const id = state.loadedContainer.container_id;
    const body = {
      operation: $("mgr-op").value,
      qty: parseFloat($("mgr-qty").value),
      unit: $("mgr-unit").value,
      manufacturer: $("mgr-mfg").value.trim(),
      catalogue_number: $("mgr-catno").value.trim(),
      product_name: $("mgr-name").value.trim(),
      lot_batch: $("mgr-lot").value.trim(),
      expiry_date: $("mgr-expiry").value,
    };
    try {
      const j = await apiJson("/api/container/" + id + "/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMsg("mgr-result", "Updated this container: " + j.old_qty + " → " + j.new_qty + " " + j.unit, "ok");
      $("mgr-load").click();
    } catch (err) {
      setMsg("mgr-result", sanitizeError(err), "err");
    }
  });
}

function setScannerLoadFailure(message) {
  document.querySelectorAll("[id$='-start-scanner']").forEach((btn) => {
    btn.disabled = true;
  });
  document.querySelectorAll("[id$='-scan-status']").forEach((el) => {
    el.className = "scan-status err";
    el.textContent = message;
  });
  const retry = $("scanner-retry");
  if (retry) retry.hidden = false;
}

export function initializeScannerUi() {
  initPackLines();
  wireWorkflowButtons();
  regScanner = wireScanner("reg", "reg-raw");
  mgrScanner = wireScanner("mgr", "mgr-container-id");
  document.documentElement.dataset.scannerReady = "true";
}

async function bootstrap() {
  initAttempts += 1;
  try {
    initializeScannerUi();
  } catch (err) {
    console.error("scanner ui init failed", sanitizeError(err));
    setScannerLoadFailure("Scanner UI could not initialize");
    return;
  }
  try {
    await loadBootstrapData();
    const retry = $("scanner-retry");
    if (retry) retry.hidden = true;
  } catch (err) {
    console.error("scanner bootstrap failed", sanitizeError(err));
    reportOptionsGap("Scanner data could not be loaded: " + sanitizeError(err));
    const retry = $("scanner-retry");
    if (retry) retry.hidden = false;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
} else {
  bootstrap();
}

if (typeof window !== "undefined") {
  window.scannerAppRetry = () => {
    if (initAttempts > 5) return;
    bootstrap();
  };
  window.scannerBundleLoadFailed = () => {
    setScannerLoadFailure("Scanner could not be loaded");
  };
}

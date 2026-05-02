const tbody = document.querySelector("#watchTable tbody");
const statusEl = document.querySelector("#status");
const excelFileInput = document.querySelector("#excelFileInput");
const providerSelect = document.querySelector("#providerSelect");

let saveTimer = null;
let isRendering = false;

const TEXT = {
  delete: "\u522a\u9664",
  saved: "\u5df2\u5132\u5b58",
  autoSaved: "\u5df2\u81ea\u52d5\u5132\u5b58",
  autoSaveFailed: "\u81ea\u52d5\u5132\u5b58\u5931\u6557\uff0c\u8acb\u624b\u52d5\u5132\u5b58\u78ba\u8a8d",
  updating: "\u66f4\u65b0\u4e2d...",
  updateDone: "\u66f4\u65b0\u5b8c\u6210",
  importStarted: "Excel \u532f\u5165\u4e2d...",
  importFailed: "\u532f\u5165\u5931\u6557",
  importDone: "\u532f\u5165\u5b8c\u6210",
  exportStarted: "Excel \u532f\u51fa\u4e2d...",
  exportFailed: "\u532f\u51fa\u5931\u6557",
  exportDone: "\u532f\u51fa\u5b8c\u6210",
  rows: "\u7b46",
  providerSaved: "\u5df2\u5132\u5b58\u8cc7\u6599\u4f86\u6e90",
  loadFailed: "\u8f09\u5165\u5931\u6557",
};

function setStatus(msg) {
  statusEl.textContent = msg;
}

function n(v) {
  return v ?? "";
}

function parseNumber(v) {
  if (v === null || v === undefined) return null;
  const text = String(v).replace(/,/g, "").trim();
  if (!text) return null;
  const num = Number(text);
  return Number.isFinite(num) ? num : null;
}

function cellInput(key, value, className = "", readOnly = false) {
  const td = document.createElement("td");
  const input = document.createElement("input");
  input.dataset.k = key;
  input.value = n(value);
  if (className) input.className = className;
  if (readOnly) input.readOnly = true;
  td.appendChild(input);
  return td;
}

function cellTextarea(key, value, className = "", rows = 2) {
  const td = document.createElement("td");
  if (className) td.className = className;
  const textarea = document.createElement("textarea");
  textarea.dataset.k = key;
  textarea.rows = rows;
  textarea.value = n(value);
  td.appendChild(textarea);
  return td;
}

function applyRowDisplayState(tr) {
  const price = parseNumber(tr.querySelector('[data-k="price"]')?.value);
  const breakevenInput = tr.querySelector('[data-k="entry"]');
  const breakeven = parseNumber(breakevenInput?.value);
  if (!breakevenInput) return;
  breakevenInput.classList.toggle("below-breakeven", price !== null && breakeven !== null && price < breakeven);
}

function rowTemplate(r = {}) {
  const tr = document.createElement("tr");
  tr.appendChild(cellInput("watch_date", r.watch_date, "date"));
  tr.appendChild(cellInput("ticker", r.ticker, "short"));
  tr.appendChild(cellInput("name", r.name));
  tr.appendChild(cellInput("price", r.price, "short"));
  tr.appendChild(cellInput("planned_buy_price", r.planned_buy_price, "short"));
  tr.appendChild(cellInput("ma5", r.ma5, "short"));
  tr.appendChild(cellInput("ma10", r.ma10, "short"));
  tr.appendChild(cellInput("ma20", r.ma20, "short"));
  tr.appendChild(cellInput("ma50", r.ma50, "short"));
  tr.appendChild(cellInput("entry", r.entry, "short"));
  tr.appendChild(cellInput("stop_loss", r.stop_loss, "short"));
  tr.appendChild(cellInput("take_profit", r.take_profit, "short"));
  tr.appendChild(cellInput("action", r.action, "", true));
  tr.appendChild(cellInput("trend", r.trend, "", true));
  tr.appendChild(cellTextarea("strategy", r.strategy, "strategy-cell", 2));
  tr.appendChild(cellInput("strategy_status", r.strategy_status, "", true));
  tr.appendChild(cellTextarea("user_notes", r.user_notes, "notes-cell", 2));
  tr.appendChild(cellInput("last_update", r.last_update, "", true));
  tr.appendChild(cellInput("notes", r.notes, "system-note", true));

  const actionTd = document.createElement("td");
  const delBtn = document.createElement("button");
  delBtn.className = "del";
  delBtn.type = "button";
  delBtn.textContent = TEXT.delete;
  delBtn.addEventListener("click", () => {
    tr.remove();
    scheduleSave();
  });
  actionTd.appendChild(delBtn);
  tr.appendChild(actionTd);
  applyRowDisplayState(tr);
  return tr;
}

function collectRows() {
  return [...tbody.querySelectorAll("tr")].map((tr) => {
    const out = {};
    tr.querySelectorAll("input[data-k], textarea[data-k]").forEach((el) => {
      out[el.dataset.k] = el.value.trim();
    });
    return out;
  });
}

function renderRows(rows) {
  isRendering = true;
  tbody.innerHTML = "";
  rows.forEach((r) => tbody.appendChild(rowTemplate(r)));
  isRendering = false;
}

async function loadProviders(selectedId = "twse_tpex") {
  const res = await fetch("/api/providers");
  const data = await res.json();
  providerSelect.innerHTML = "";
  (data.providers || []).forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    if (p.id === selectedId) opt.selected = true;
    providerSelect.appendChild(opt);
  });
}

async function saveProvider(provider) {
  await fetch("/api/provider", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
}

async function loadRows() {
  const res = await fetch("/api/watchlist");
  const data = await res.json();
  await loadProviders(data.provider || "twse_tpex");
  renderRows(data.rows || []);
}

async function saveRows({ quiet = false } = {}) {
  const rows = collectRows();
  const res = await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows }),
  });
  if (!res.ok) throw new Error("save_failed");
  if (!quiet) setStatus(TEXT.saved);
}

function scheduleSave() {
  if (isRendering) return;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    try {
      await saveRows({ quiet: true });
      setStatus(`${TEXT.autoSaved} ${new Date().toLocaleTimeString()}`);
    } catch {
      setStatus(TEXT.autoSaveFailed);
    }
  }, 700);
}

async function flushPendingSave() {
  if (!saveTimer) return;
  window.clearTimeout(saveTimer);
  saveTimer = null;
  await saveRows({ quiet: true });
}

async function updateRows() {
  setStatus(TEXT.updating);
  await flushPendingSave();
  await saveRows({ quiet: true });
  await saveProvider(providerSelect.value);
  const res = await fetch("/api/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: providerSelect.value }),
  });
  const data = await res.json();
  renderRows(data.rows || []);
  if ((data.failed_count || 0) > 0) {
    setStatus(`${TEXT.updateDone}: ${data.success_count || 0} OK, ${data.failed_count} failed. ${data.first_failure || ""}`);
  } else {
    setStatus(`${TEXT.updateDone}: ${data.success_count || 0} OK, ${data.provider}`);
  }
}

async function importExcel(file) {
  const fd = new FormData();
  fd.append("file", file);
  setStatus(TEXT.importStarted);
  const res = await fetch("/api/import_excel", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    setStatus(TEXT.importFailed);
    return;
  }
  renderRows(data.rows || []);
  await saveRows({ quiet: true });
  setStatus(`${TEXT.importDone}: ${data.count} ${TEXT.rows}`);
}

async function exportExcel() {
  setStatus(TEXT.exportStarted);
  await flushPendingSave();
  await saveRows({ quiet: true });
  const res = await fetch("/api/export_excel");
  if (!res.ok) {
    setStatus(TEXT.exportFailed);
    return;
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "stock_watchlist.xlsx";
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setStatus(TEXT.exportDone);
}

document.querySelector("#addRowBtn").addEventListener("click", () => {
  tbody.appendChild(rowTemplate({ watch_date: new Date().toISOString().slice(0, 10) }));
  scheduleSave();
});

tbody.addEventListener("input", (event) => {
  if (event.target.matches("input[data-k], textarea[data-k]")) {
    applyRowDisplayState(event.target.closest("tr"));
    scheduleSave();
  }
});

providerSelect.addEventListener("change", async () => {
  await saveProvider(providerSelect.value);
  setStatus(`${TEXT.providerSaved}: ${providerSelect.value}`);
});

document.querySelector("#importExcelBtn").addEventListener("click", () => excelFileInput.click());
document.querySelector("#exportExcelBtn").addEventListener("click", exportExcel);
excelFileInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  await importExcel(file);
  excelFileInput.value = "";
});

document.querySelector("#saveBtn").addEventListener("click", async () => {
  await flushPendingSave();
  await saveRows();
});
document.querySelector("#updateBtn").addEventListener("click", updateRows);

window.addEventListener("beforeunload", () => {
  if (!saveTimer) return;
  const payload = JSON.stringify({ rows: collectRows() });
  navigator.sendBeacon("/api/watchlist", new Blob([payload], { type: "application/json" }));
});

loadRows().catch(() => setStatus(TEXT.loadFailed));

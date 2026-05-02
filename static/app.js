const tbody = document.querySelector("#watchTable tbody");
const statusEl = document.querySelector("#status");
const excelFileInput = document.querySelector("#excelFileInput");
const providerSelect = document.querySelector("#providerSelect");

let saveTimer = null;
let isRendering = false;

function setStatus(msg) {
  statusEl.textContent = msg;
}

function n(v) {
  return v ?? "";
}

function setValue(el, value) {
  el.value = n(value);
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

function rowTemplate(r = {}) {
  const tr = document.createElement("tr");
  tr.appendChild(cellInput("watch_date", r.watch_date, "date"));
  tr.appendChild(cellInput("ticker", r.ticker, "short"));
  tr.appendChild(cellInput("name", r.name));
  tr.appendChild(cellInput("price", r.price, "short"));
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
  delBtn.textContent = "刪除";
  delBtn.addEventListener("click", () => {
    tr.remove();
    scheduleSave();
  });
  actionTd.appendChild(delBtn);
  tr.appendChild(actionTd);
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
  if (!quiet) setStatus("已保存");
}

function scheduleSave() {
  if (isRendering) return;
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    try {
      await saveRows({ quiet: true });
      setStatus(`已自動保存 ${new Date().toLocaleTimeString()}`);
    } catch {
      setStatus("自動保存失敗，請按保存再試一次");
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
  setStatus("更新中...");
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
    setStatus(`更新完成：成功 ${data.success_count || 0}，失敗 ${data.failed_count}。${data.first_failure || "請查看系統備註"}`);
  } else {
    setStatus(`更新完成：成功 ${data.success_count || 0}，資料來源 ${data.provider}`);
  }
}

async function importExcel(file) {
  const fd = new FormData();
  fd.append("file", file);
  setStatus("Excel 匯入中...");
  const res = await fetch("/api/import_excel", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok || !data.ok) {
    setStatus("匯入失敗");
    return;
  }
  renderRows(data.rows || []);
  await saveRows({ quiet: true });
  setStatus(`匯入完成，共 ${data.count} 筆`);
}

document.querySelector("#addRowBtn").addEventListener("click", () => {
  tbody.appendChild(rowTemplate({ watch_date: new Date().toISOString().slice(0, 10) }));
  scheduleSave();
});

tbody.addEventListener("input", (event) => {
  if (event.target.matches("input[data-k], textarea[data-k]")) {
    scheduleSave();
  }
});

providerSelect.addEventListener("change", async () => {
  await saveProvider(providerSelect.value);
  setStatus(`已保存資料來源：${providerSelect.value}`);
});

document.querySelector("#importExcelBtn").addEventListener("click", () => excelFileInput.click());
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

loadRows().catch(() => setStatus("載入失敗"));

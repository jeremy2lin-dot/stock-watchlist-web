const tbody = document.querySelector("#watchTable tbody");
const statusEl = document.querySelector("#status");
const excelFileInput = document.querySelector("#excelFileInput");
const providerSelect = document.querySelector("#providerSelect");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function n(v) {
  return v ?? "";
}

function rowTemplate(r = {}) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input class="date" data-k="watch_date" value="${n(r.watch_date)}"></td>
    <td><input class="short" data-k="ticker" value="${n(r.ticker)}"></td>
    <td><input data-k="name" value="${n(r.name)}"></td>
    <td><input class="short" data-k="price" value="${n(r.price)}"></td>
    <td><input class="short" data-k="ma5" value="${n(r.ma5)}"></td>
    <td><input class="short" data-k="ma10" value="${n(r.ma10)}"></td>
    <td><input class="short" data-k="ma20" value="${n(r.ma20)}"></td>
    <td><input class="short" data-k="ma50" value="${n(r.ma50)}"></td>
    <td><input class="short" data-k="entry" value="${n(r.entry)}"></td>
    <td><input class="short" data-k="stop_loss" value="${n(r.stop_loss)}"></td>
    <td><input class="short" data-k="take_profit" value="${n(r.take_profit)}"></td>
    <td><input data-k="action" value="${n(r.action)}" readonly></td>
    <td><input data-k="trend" value="${n(r.trend)}" readonly></td>
    <td class="strategy-cell"><textarea data-k="strategy" rows="2">${n(r.strategy)}</textarea></td>
    <td><input data-k="strategy_status" value="${n(r.strategy_status)}" readonly></td>
    <td><input data-k="last_update" value="${n(r.last_update)}" readonly></td>
    <td><input data-k="notes" value="${n(r.notes)}" readonly></td>
    <td><button class="del">刪</button></td>
  `;
  tr.querySelector(".del").addEventListener("click", () => tr.remove());
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
  tbody.innerHTML = "";
  rows.forEach((r) => tbody.appendChild(rowTemplate(r)));
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

async function saveRows() {
  const rows = collectRows();
  await fetch("/api/watchlist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows }),
  });
  setStatus("已儲存");
}

async function updateRows() {
  setStatus("更新中...");
  await saveRows();
  await saveProvider(providerSelect.value);
  const res = await fetch("/api/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: providerSelect.value }),
  });
  const data = await res.json();
  renderRows(data.rows || []);
  if ((data.failed_count || 0) > 0) {
    setStatus(`更新完成（成功 ${data.success_count || 0}，異常 ${data.failed_count}；${data.first_failure || "請查看備註欄"}）`);
  } else {
    setStatus(`更新完成（成功 ${data.success_count || 0}；資料源: ${data.provider}）`);
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
  setStatus(`匯入完成，共 ${data.count} 筆`);
}

document.querySelector("#addRowBtn").addEventListener("click", () => {
  tbody.appendChild(rowTemplate({ watch_date: new Date().toISOString().slice(0, 10) }));
});

providerSelect.addEventListener("change", async () => {
  await saveProvider(providerSelect.value);
  setStatus(`已切換資料源: ${providerSelect.value}`);
});

document.querySelector("#importExcelBtn").addEventListener("click", () => excelFileInput.click());
excelFileInput.addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  await importExcel(file);
  excelFileInput.value = "";
});

document.querySelector("#saveBtn").addEventListener("click", saveRows);
document.querySelector("#updateBtn").addEventListener("click", updateRows);

loadRows().catch(() => setStatus("載入失敗"));

const NEW_PORTFOLIO_VALUE = "__new__";

const state = {
  interval: "monthly",
  portfolios: [],
  records: { trades: [], dividends: [] },
  summary: null,
  performance: { points: [], annual: [] },
  allocation: null,
  charts: { performance: null, annual: null, allocation: null },
  recordsVisible: false,
  recordPage: 1,
};

const colors = {
  market: "#2563eb",
  gain: "#0f9f6e",
  dividend: "#d97706",
  realized: "#7c3aed",
  negative: "#d14343",
  grid: "#d8dee6",
  text: "#667085",
  tooltipBg: "#ffffff",
  tooltipStroke: "#cbd5e1",
};

const allocationPalette = ["#2563eb", "#0f9f6e", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#475569", "#65a30d"];

document.addEventListener("DOMContentLoaded", async () => {
  setupStaticEnhancements();
  setDefaultDates();
  bindEvents();
  await refreshDefaultDates();
  refreshAll();
});

function setupStaticEnhancements() {
  replaceSvgWithCanvas("performanceChart");
  replaceSvgWithCanvas("annualChart");
  setupDividendImportPanel();
  setupRecordsPanel();
}

function replaceSvgWithCanvas(id) {
  const element = byId(id);
  if (!element || element.tagName.toLowerCase() === "canvas") {
    return;
  }
  const frame = document.createElement("div");
  frame.className = "chart-canvas-frame";
  const canvas = document.createElement("canvas");
  canvas.id = id;
  canvas.setAttribute("role", element.getAttribute("role") || "img");
  canvas.setAttribute("aria-label", element.getAttribute("aria-label") || "");
  frame.appendChild(canvas);
  element.replaceWith(frame);
}

function setupDividendImportPanel() {
  const tradeButton = byId("importTradesButton");
  if (!tradeButton || byId("importDividendsButton")) {
    return;
  }
  const panel = tradeButton.closest(".import-panel");
  const header = panel.querySelector("header");
  header.insertAdjacentHTML(
    "beforeend",
    `<button class="secondary" id="downloadDividendTemplateButton" type="button">下載配息模板</button>`,
  );
  tradeButton.insertAdjacentHTML(
    "afterend",
    `
      <label>
        配息 CSV 檔案
        <input id="dividendImportFile" type="file" accept=".csv,text/csv" />
      </label>
      <button class="primary" id="importDividendsButton" type="button">匯入配息</button>`,
  );
}

function setupRecordsPanel() {
  const tableBody = byId("recordsBody");
  if (!tableBody || byId("recordsPanelBody")) {
    return;
  }
  const panel = tableBody.closest(".table-panel");
  const header = panel.querySelector("header");
  const tableWrap = tableBody.closest(".table-wrap");
  panel.classList.add("records-panel");
  header.insertAdjacentHTML(
    "beforeend",
    `<button class="secondary" id="toggleRecordsButton" type="button">顯示紀錄</button>`,
  );
  tableWrap.insertAdjacentHTML(
    "beforebegin",
    `
      <div class="record-filters">
        <label>
          類型
          <select id="recordTypeFilter">
            <option value="all">全部</option>
            <option value="trade">交易</option>
            <option value="dividend">配息</option>
          </select>
        </label>
        <label>
          投資組合
          <select id="recordPortfolioFilter">
            <option value="All">全部</option>
          </select>
        </label>
        <label>
          股票代號
          <input id="recordSymbolFilter" type="search" />
        </label>
        <label>
          起日
          <input id="recordStartFilter" type="date" />
        </label>
        <label>
          訖日
          <input id="recordEndFilter" type="date" />
        </label>
        <label>
          每頁
          <select id="recordPageSize">
            <option value="10">10</option>
            <option value="25" selected>25</option>
            <option value="50">50</option>
          </select>
        </label>
      </div>`,
  );
  tableWrap.insertAdjacentHTML(
    "afterend",
    `
      <div class="pagination">
        <button class="secondary" id="recordPrevPage" type="button">上一頁</button>
        <span id="recordPageText"></span>
        <button class="secondary" id="recordNextPage" type="button">下一頁</button>
      </div>`,
  );
  const body = document.createElement("div");
  body.id = "recordsPanelBody";
  body.className = "records-panel-body hidden";
  panel.appendChild(body);
  body.appendChild(panel.querySelector(".record-filters"));
  body.appendChild(tableWrap);
  body.appendChild(panel.querySelector(".pagination"));
}

function setDefaultDates(defaults = null) {
  const today = new Date();
  const fallbackStart = new Date(today.getFullYear(), 0, 1);
  const fallbackAsOf = previousWeekday(today);
  byId("asOfInput").value = defaults?.as_of || toInputDate(fallbackAsOf);
  byId("endInput").value = defaults?.end || toInputDate(today);
  byId("startInput").value = defaults?.start || toInputDate(fallbackStart);
  document.querySelectorAll("form input[name='date']").forEach((input) => {
    input.value = byId("asOfInput").value;
  });
}

async function refreshDefaultDates() {
  try {
    setDefaultDates(await apiGet("/api/defaults"));
  } catch (_error) {
    setDefaultDates();
  }
}

function bindEvents() {
  byId("refreshButton").addEventListener("click", refreshAll);
  ["asOfInput", "startInput", "endInput", "portfolioFilter", "currencyFilter"].forEach((id) => {
    byId(id).addEventListener("change", refreshAll);
  });

  ["performanceXAxisMode", "performanceYAxisMode", "annualXAxisMode", "annualYAxisMode"].forEach((id) => {
    byId(id).addEventListener("change", renderPerformance);
  });

  document.querySelectorAll("[data-interval]").forEach((button) => {
    button.addEventListener("click", () => {
      state.interval = button.dataset.interval;
      document.querySelectorAll("[data-interval]").forEach((item) => item.classList.toggle("active", item === button));
      refreshPerformance();
    });
  });

  document.querySelectorAll("[data-form-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.formTab;
      document.querySelectorAll("[data-form-tab]").forEach((item) => item.classList.toggle("active", item === button));
      byId("tradeForm").classList.toggle("hidden", tab !== "trade");
      byId("dividendForm").classList.toggle("hidden", tab !== "dividend");
    });
  });

  document.querySelectorAll("form input[name='symbol']").forEach((input) => {
    input.addEventListener("change", () => {
      input.form.elements.currency.value = inferCurrency(input.value);
    });
  });

  document.querySelectorAll("[data-portfolio-select]").forEach((select) => {
    select.addEventListener("change", () => syncNewPortfolioField(select.form));
  });

  byId("tradeForm").addEventListener("submit", submitTrade);
  byId("dividendForm").addEventListener("submit", submitDividend);
  byId("downloadTradeTemplateButton").addEventListener("click", downloadTradeTemplate);
  byId("downloadDividendTemplateButton").addEventListener("click", downloadDividendTemplate);
  byId("importTradesButton").addEventListener("click", importTradesFromFile);
  byId("importDividendsButton").addEventListener("click", importDividendsFromFile);
  byId("toggleRecordsButton").addEventListener("click", toggleRecordsPanel);
  ["recordTypeFilter", "recordPortfolioFilter", "recordStartFilter", "recordEndFilter", "recordPageSize"].forEach((id) => {
    byId(id).addEventListener("change", () => {
      state.recordPage = 1;
      refreshRecords();
    });
  });
  byId("recordSymbolFilter").addEventListener("input", () => {
    state.recordPage = 1;
    refreshRecords();
  });
  byId("recordPrevPage").addEventListener("click", () => {
    state.recordPage = Math.max(1, state.recordPage - 1);
    refreshRecords();
  });
  byId("recordNextPage").addEventListener("click", () => {
    state.recordPage += 1;
    refreshRecords();
  });
}

async function refreshAll() {
  setStatus("更新中");
  try {
    await refreshPortfolios();
    const tasks = [refreshSummary(), refreshPerformance(), refreshAllocation()];
    if (state.recordsVisible) {
      tasks.push(refreshRecords());
    }
    await Promise.all(tasks);
    const warnings = state.summary?.warnings || [];
    setStatus(warnings.length ? warnings.join(" ") : "已更新");
  } catch (error) {
    setStatus(error.message || "更新失敗");
  }
}

async function refreshPortfolios() {
  const payload = await apiGet("/api/portfolios");
  state.portfolios = payload.portfolios || [];
  renderPortfolioOptions();
}

async function refreshRecords() {
  if (!state.recordsVisible) {
    renderRecords();
    return;
  }
  state.records = await apiGet(`/api/records?${recordQuery()}`);
  state.recordPage = state.records.page || state.recordPage;
  renderRecords();
}

async function refreshSummary() {
  const start = byId("startInput").value;
  const end = byId("endInput").value;
  state.summary = await apiGet(
    `/api/period-summary?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}${portfolioQuery()}${currencyQuery()}`,
  );
  renderSummary();
}

async function refreshPerformance() {
  const start = byId("startInput").value;
  const end = byId("endInput").value;
  state.performance = await apiGet(
    `/api/performance?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&interval=${state.interval}${portfolioQuery()}${currencyQuery()}`,
  );
  renderPerformance();
}

async function refreshAllocation() {
  const asOf = byId("endInput").value;
  state.allocation = await apiGet(`/api/allocation?as_of=${encodeURIComponent(asOf)}${portfolioQuery()}${currencyQuery()}`);
  renderAllocation();
}

async function submitTrade(event) {
  event.preventDefault();
  const form = event.currentTarget;
  let payload;
  try {
    payload = formPayloadWithPortfolio(form);
  } catch (error) {
    setStatus(error.message);
    return;
  }
  payload.quantity = Number(payload.quantity);
  payload.price = Number(payload.price);
  payload.fees = Number(payload.fees || 0);
  await apiPost("/api/trades", payload);
  resetRecordForm(form);
  await refreshAll();
}

async function submitDividend(event) {
  event.preventDefault();
  const form = event.currentTarget;
  let payload;
  try {
    payload = formPayloadWithPortfolio(form);
  } catch (error) {
    setStatus(error.message);
    return;
  }
  payload.gross_amount = Number(payload.gross_amount);
  payload.tax = Number(payload.tax || 0);
  await apiPost("/api/dividends", payload);
  resetRecordForm(form);
  await refreshAll();
}

async function deleteRecord(kind, id) {
  const path = kind === "trade" ? `/api/trades/${encodeURIComponent(id)}` : `/api/dividends/${encodeURIComponent(id)}`;
  await apiDelete(path);
  await refreshAll();
}

async function downloadTradeTemplate() {
  try {
    const template = await apiGet("/api/templates/trades");
    downloadTextFile(template.filename || "trade-import-template.csv", template.content || "");
    setImportStatus("已下載交易匯入範本");
  } catch (error) {
    setImportStatus(error.message || "下載範本失敗");
  }
}

async function downloadDividendTemplate() {
  try {
    const template = await apiGet("/api/templates/dividends");
    downloadTextFile(template.filename || "dividend-import-template.csv", template.content || "");
    setImportStatus("已下載配息匯入範本");
  } catch (error) {
    setImportStatus(error.message || "下載範本失敗");
  }
}

async function importTradesFromFile() {
  const fileInput = byId("tradeImportFile");
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    setImportStatus("請先選擇 CSV 檔案");
    return;
  }

  try {
    setImportStatus("讀取檔案中");
    const text = await file.text();
    const records = parseTradeImportCSV(text);
    setImportStatus(`準備匯入 ${records.length} 筆交易`);
    const payload = await apiPost("/api/import/trades", { records });
    fileInput.value = "";
    setImportStatus(`已匯入 ${payload.imported_count} 筆交易`);
    await refreshAll();
  } catch (error) {
    setImportStatus(error.message || "匯入失敗");
  }
}

async function importDividendsFromFile() {
  const fileInput = byId("dividendImportFile");
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    setImportStatus("請先選擇配息 CSV 檔案");
    return;
  }

  try {
    setImportStatus("讀取配息檔案中");
    const text = await file.text();
    const records = parseDividendImportCSV(text);
    setImportStatus(`準備匯入 ${records.length} 筆配息`);
    const payload = await apiPost("/api/import/dividends", { records });
    fileInput.value = "";
    setImportStatus(`已匯入 ${payload.imported_count} 筆配息`);
    await refreshAll();
  } catch (error) {
    setImportStatus(error.message || "配息匯入失敗");
  }
}

function renderSummary() {
  const summary = state.summary || {};
  const currency = summary.currency || reportCurrency();
  const rangeText = `${summary.start || byId("startInput").value} ~ ${summary.end || byId("endInput").value}`;
  byId("metricGrid").innerHTML = [
    metric("市值", money(summary.market_value, currency), `訖日持有 · ${rangeText}`, summary.market_value),
    metric("總損益", signedMoney(summary.total_gain, currency), `${pct(summary.return_pct)} · 區間`, summary.total_gain),
    metric("已實現", signedMoney(summary.realized_gain, currency), `區間已實現 · ${currency}`, summary.realized_gain),
    metric("賣出損益", signedMoney(summary.sell_gain, currency), `區間賣出 · ${currency}`, summary.sell_gain),
    metric("累計配息", money(summary.dividends, currency), `區間稅後 · ${currency}`, summary.dividends),
  ].join("");

  const rows = summary.positions || [];
  byId("positionsBody").innerHTML = rows.length
    ? rows
        .map(
          (row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.currency)}</td>
          <td>${number(row.quantity)}</td>
          <td>${money(row.average_cost, currency)}</td>
          <td>${money(row.last_price, currency)}</td>
          <td>${money(row.market_value, currency)}</td>
          <td>${pct(row.allocation_pct)}</td>
          <td class="${classFor(row.unrealized_gain)}">${signedMoney(row.unrealized_gain, currency)}</td>
          <td>${money(row.dividends, currency)}</td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="9">尚無持股</td></tr>`;
}

function renderRecords() {
  const body = byId("recordsPanelBody");
  const toggle = byId("toggleRecordsButton");
  body.classList.toggle("hidden", !state.recordsVisible);
  toggle.textContent = state.recordsVisible ? "隱藏紀錄" : "顯示紀錄";
  if (!state.recordsVisible) {
    return;
  }

  const rows = state.records.records || [];
  byId("recordsBody").innerHTML = rows.length
    ? rows
        .map(
          (row) => `
        <tr>
          <td>${escapeHtml(row.date)}</td>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.portfolio)}</td>
          <td>${escapeHtml(row.currency)}</td>
          <td>${escapeHtml(recordTypeLabel(row))}</td>
          <td>${money(row.amount, row.currency)}</td>
          <td><button class="danger" type="button" data-delete-kind="${escapeHtml(row.kind)}" data-delete-id="${escapeHtml(row.id)}">刪除</button></td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="7">尚無紀錄</td></tr>`;

  byId("recordPageText").textContent = `${state.records.page || 1} / ${state.records.total_pages || 1} · ${state.records.total || 0} 筆`;
  byId("recordPrevPage").disabled = (state.records.page || 1) <= 1;
  byId("recordNextPage").disabled = (state.records.page || 1) >= (state.records.total_pages || 1);
  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", () => deleteRecord(button.dataset.deleteKind, button.dataset.deleteId));
  });
}

function recordTypeLabel(row) {
  if (row.kind === "dividend") {
    return "配息";
  }
  return row.type === "BUY" ? "買進" : "賣出";
}

function toggleRecordsPanel() {
  state.recordsVisible = !state.recordsVisible;
  if (state.recordsVisible) {
    refreshRecords();
    return;
  }
  renderRecords();
}

function renderPortfolioOptions() {
  const filter = byId("portfolioFilter");
  const filterCurrent = filter.value || "All";
  const portfolios = state.portfolios.length ? state.portfolios : ["General"];
  filter.innerHTML = `<option value="All">全部</option>${portfolios
    .map((portfolio) => `<option value="${escapeHtml(portfolio)}">${escapeHtml(portfolio)}</option>`)
    .join("")}`;
  filter.value = portfolios.includes(filterCurrent) || filterCurrent === "All" ? filterCurrent : "All";

  const recordFilter = byId("recordPortfolioFilter");
  if (recordFilter) {
    const recordCurrent = recordFilter.value || "All";
    recordFilter.innerHTML = `<option value="All">全部</option>${portfolios
      .map((portfolio) => `<option value="${escapeHtml(portfolio)}">${escapeHtml(portfolio)}</option>`)
      .join("")}`;
    recordFilter.value = portfolios.includes(recordCurrent) || recordCurrent === "All" ? recordCurrent : "All";
  }

  document.querySelectorAll("[data-portfolio-select]").forEach((select) => {
    const current = select.value || selectedPortfolioForForm();
    select.innerHTML = `${portfolios
      .map((portfolio) => `<option value="${escapeHtml(portfolio)}">${escapeHtml(portfolio)}</option>`)
      .join("")}<option value="${NEW_PORTFOLIO_VALUE}">新增投資組合</option>`;
    const preferred = selectedPortfolioForForm();
    select.value = portfolios.includes(current) ? current : portfolios.includes(preferred) ? preferred : "General";
    syncNewPortfolioField(select.form);
  });
}

function renderAllocation() {
  const allocation = state.allocation;
  const container = byId("allocationGrid");
  if (!allocation) {
    destroyChart("allocation");
    container.innerHTML = "";
    return;
  }
  const currency = allocation.currency || reportCurrency();
  const selected = allocation.selected || allocation.overall || {};
  const positions = [...(selected.positions || [])]
    .filter((position) => Number(position.market_value || 0) > 0)
    .sort((a, b) => Number(b.allocation_pct || 0) - Number(a.allocation_pct || 0));
  const scope = allocation.portfolio && allocation.portfolio !== "All" ? allocation.portfolio : "整體投資";

  destroyChart("allocation");
  container.innerHTML = `
    <div class="allocation-summary">
      <span>範圍</span>
      <strong>${escapeHtml(scope)}</strong>
      <small>${money(selected.market_value, currency)}</small>
    </div>
    <div class="allocation-pie-stage">
      <canvas id="allocationPieChart" class="allocation-pie-chart" role="img" aria-label="持股占比圓餅圖"></canvas>
    </div>
    <div id="allocationLegend" class="allocation-legend"></div>`;

  drawAllocationPie(byId("allocationPieChart"), positions, currency);
  renderAllocationLegend(positions, currency);
}

function renderAllocationLegend(positions, currency) {
  const legend = byId("allocationLegend");
  if (!positions.length) {
    legend.innerHTML = `<p class="empty">尚無持股</p>`;
    return;
  }
  legend.innerHTML = positions
    .map(
      (position, index) => `
      <div class="allocation-legend-row">
        <span class="allocation-legend-swatch" style="background:${allocationColor(index)}"></span>
        <span class="allocation-legend-main">
          <strong>${escapeHtml(position.symbol)}</strong>
          <small>${escapeHtml(position.currency)} · ${number(position.quantity)} 股</small>
        </span>
        <span class="allocation-legend-value">
          <strong>${pct(position.allocation_pct)}</strong>
          <small>${money(position.market_value, currency)}</small>
        </span>
      </div>`,
    )
    .join("");
}

function allocationColor(index) {
  return allocationPalette[index % allocationPalette.length];
}

function renderPerformance() {
  const performanceConfig = lineChartConfig();
  const annualConfig = annualChartConfig();
  renderLegend("performanceLegend", performanceConfig.series.map((item) => [item.label, item.color]));
  renderLegend("annualLegend", annualConfig.series.map((item) => [item.label, item.color]));

  drawLineChart(byId("performanceChart"), state.performance.points || [], performanceConfig.series, {
    xMode: byId("performanceXAxisMode").value,
    yFormatter: performanceConfig.yFormatter,
    tooltipTitle: "日期",
  });
  drawBarChart(byId("annualChart"), state.performance.annual || [], annualConfig.series, {
    xMode: byId("annualXAxisMode").value,
    yFormatter: annualConfig.yFormatter,
    tooltipTitle: "年度",
  });
}

function lineChartConfig() {
  if (byId("performanceYAxisMode").value === "return_pct") {
    return {
      series: [{ key: "return_pct", label: "報酬率", color: colors.gain, formatter: pct }],
      yFormatter: pct,
    };
  }
  const currency = state.performance.currency || reportCurrency();
  return {
    series: [
      { key: "market_value", label: "市值", color: colors.market, formatter: (value) => money(value, currency) },
      { key: "total_gain", label: "總損益", color: colors.gain, formatter: (value) => money(value, currency) },
      { key: "dividends", label: "累計配息", color: colors.dividend, formatter: (value) => money(value, currency) },
    ],
    yFormatter: (value) => compactMoney(value, currency),
  };
}

function annualChartConfig() {
  if (byId("annualYAxisMode").value === "return_pct") {
    return {
      series: [{ key: "return_pct", label: "年度報酬率", color: colors.gain, formatter: pct }],
      yFormatter: pct,
    };
  }
  const currency = state.performance.currency || reportCurrency();
  return {
    series: [
      { key: "gain", label: "年度損益", color: colors.gain, formatter: (value) => money(value, currency) },
      { key: "dividends", label: "年度配息", color: colors.dividend, formatter: (value) => money(value, currency) },
    ],
    yFormatter: (value) => compactMoney(value, currency),
  };
}

function renderLegend(id, items) {
  byId(id).innerHTML = items
    .map(([label, color]) => `<span class="legend-item"><span class="swatch" style="background:${color}"></span>${label}</span>`)
    .join("");
}

function metric(label, value, subtext, rawValue) {
  return `<article class="metric"><span>${label}</span><strong class="${Number(rawValue || 0) < 0 ? "negative" : ""}">${value}</strong><small>${subtext}</small></article>`;
}

async function apiGet(path) {
  return api(path, { method: "GET" });
}

async function apiPost(path, payload) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function apiDelete(path) {
  return api(path, { method: "DELETE" });
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function parseTradeImportCSV(text) {
  const rows = parseCSV(text);
  if (rows.length < 2) {
    throw new Error("CSV 至少需要標題列與一筆資料");
  }
  const headers = rows[0].map((header) => header.trim());
  const required = ["date", "symbol", "side", "quantity", "price"];
  const missing = required.filter((field) => !headers.includes(field));
  if (missing.length) {
    throw new Error(`CSV 缺少必要欄位: ${missing.join(", ")}`);
  }

  return rows
    .slice(1)
    .filter((row) => row.some((cell) => String(cell || "").trim() !== ""))
    .map((row, index) => {
      const record = {};
      headers.forEach((header, columnIndex) => {
        if (header) {
          record[header] = row[columnIndex] || "";
        }
      });
      if (!record.fees) {
        record.fees = "0";
      }
      if (!record.portfolio) {
        record.portfolio = selectedPortfolioForForm();
      }
      if (!record.currency) {
        record.currency = inferCurrency(record.symbol);
      }
      if (!record.notes) {
        record.notes = "";
      }
      for (const field of required) {
        if (!String(record[field] || "").trim()) {
          throw new Error(`第 ${index + 2} 列缺少 ${field}`);
        }
      }
      return record;
    });
}

function parseDividendImportCSV(text) {
  const rows = parseCSV(text);
  if (rows.length < 2) {
    throw new Error("CSV 至少需要標題列與一筆配息資料");
  }
  const headers = rows[0].map((header) => header.trim());
  const required = ["date", "symbol", "gross_amount"];
  const missing = required.filter((field) => !headers.includes(field));
  if (missing.length) {
    throw new Error(`CSV 缺少必要欄位: ${missing.join(", ")}`);
  }

  return rows
    .slice(1)
    .filter((row) => row.some((cell) => String(cell || "").trim() !== ""))
    .map((row, index) => {
      const record = {};
      headers.forEach((header, columnIndex) => {
        if (header) {
          record[header] = row[columnIndex] || "";
        }
      });
      if (!record.tax) {
        record.tax = "0";
      }
      if (!record.portfolio) {
        record.portfolio = selectedPortfolioForForm();
      }
      if (!record.currency) {
        record.currency = inferCurrency(record.symbol);
      }
      if (!record.notes) {
        record.notes = "";
      }
      for (const field of required) {
        if (!String(record[field] || "").trim()) {
          throw new Error(`第 ${index + 2} 列缺少 ${field}`);
        }
      }
      return record;
    });
}

function parseCSV(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }
    cell += char;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setImportStatus(message) {
  byId("importStatus").textContent = message;
}

function formPayloadWithPortfolio(form) {
  const payload = Object.fromEntries(new FormData(form).entries());
  if (payload.portfolio === NEW_PORTFOLIO_VALUE) {
    const newPortfolio = String(payload.new_portfolio || "").trim();
    if (!newPortfolio) {
      throw new Error("請輸入新的投資組合名稱");
    }
    payload.portfolio = newPortfolio;
  }
  delete payload.new_portfolio;
  return payload;
}

function resetRecordForm(form) {
  form.reset();
  form.elements.date.value = byId("asOfInput").value;
  form.elements.portfolio.value = selectedPortfolioForForm();
  form.elements.currency.value = byId("currencyFilter").value;
  if (form.elements.fees) {
    form.elements.fees.value = "0";
  }
  if (form.elements.tax) {
    form.elements.tax.value = "0";
  }
  syncNewPortfolioField(form);
}

function syncNewPortfolioField(form) {
  const select = form.querySelector("[data-portfolio-select]");
  const wrapper = form.querySelector(".portfolio-new");
  const input = form.elements.new_portfolio;
  const isNew = select.value === NEW_PORTFOLIO_VALUE;
  wrapper.classList.toggle("hidden", !isNew);
  input.required = isNew;
  if (!isNew) {
    input.value = "";
  }
}

function portfolioQuery() {
  const portfolio = byId("portfolioFilter").value;
  return portfolio && portfolio !== "All" ? `&portfolio=${encodeURIComponent(portfolio)}` : "";
}

function recordQuery() {
  const params = new URLSearchParams();
  params.set("kind", byId("recordTypeFilter").value || "all");
  params.set("page", String(state.recordPage));
  params.set("page_size", byId("recordPageSize").value || "25");
  const portfolio = byId("recordPortfolioFilter").value;
  const symbol = byId("recordSymbolFilter").value.trim();
  const start = byId("recordStartFilter").value || byId("startInput").value;
  const end = byId("recordEndFilter").value || byId("endInput").value;
  if (portfolio && portfolio !== "All") {
    params.set("portfolio", portfolio);
  }
  if (symbol) {
    params.set("symbol", symbol);
  }
  if (start) {
    params.set("start", start);
  }
  if (end) {
    params.set("end", end);
  }
  return params.toString();
}

function currencyQuery() {
  return `&currency=${encodeURIComponent(reportCurrency())}`;
}

function reportCurrency() {
  return byId("currencyFilter").value || "TWD";
}

function selectedPortfolioForForm() {
  const portfolio = byId("portfolioFilter").value;
  return portfolio && portfolio !== "All" ? portfolio : "General";
}

function annualXValue(row) {
  return `${row.year}-12-31`;
}

function formatXAxisLabel(value, mode) {
  const text = String(value || "");
  if (mode === "short_year") {
    return text.slice(2, 4);
  }
  if (mode === "year") {
    return text.slice(0, 4);
  }
  if (mode === "month") {
    return text.slice(0, 7);
  }
  if (mode === "auto") {
    if (state.interval === "yearly") {
      return text.slice(0, 4);
    }
    if (state.interval === "monthly") {
      return text.slice(0, 7);
    }
  }
  return text;
}

function inferCurrency(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  return normalized.endsWith(".TW") || normalized.endsWith(".TWO") ? "TWD" : "USD";
}

const emptyChartPlugin = {
  id: "emptyMessage",
  afterDraw(chart, _args, options) {
    const hasData = chart.data.datasets.some((dataset) => (dataset.data || []).length);
    if (hasData || !options.text) {
      return;
    }
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.fillStyle = colors.text;
    ctx.font = "14px Segoe UI, Noto Sans TC, Arial, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(options.text, (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2);
    ctx.restore();
  },
};

function drawLineChart(canvas, points, series, options) {
  const labels = points.map((point) => formatXAxisLabel(point.date, options.xMode));
  const datasets = series.map((item) => ({
    label: item.label,
    data: points.map((point) => Number(point[item.key] || 0)),
    borderColor: item.color,
    backgroundColor: item.color,
    borderWidth: 3,
    pointRadius: 2,
    pointHoverRadius: 5,
    tension: 0.25,
  }));
  createChart("performance", canvas, {
    type: "line",
    data: { labels, datasets },
    plugins: [emptyChartPlugin],
    options: chartOptions({
      emptyText: "尚無圖表資料",
      tooltipTitle: (items) => (items.length ? formatXAxisLabel(points[items[0].dataIndex].date, "full") : ""),
      tooltipLabel: (context) => {
        const item = series[context.datasetIndex];
        return `${item.label}: ${item.formatter(context.parsed.y)}`;
      },
      yFormatter: options.yFormatter,
    }),
  });
}

function drawBarChart(canvas, rows, series, options) {
  const xMode = options.xMode === "auto" ? "year" : options.xMode;
  const labels = rows.map((row) => formatXAxisLabel(annualXValue(row), xMode));
  const datasets = series.map((item) => ({
    label: item.label,
    data: rows.map((row) => Number(row[item.key] || 0)),
    backgroundColor: rows.map((row) => {
      const value = Number(row[item.key] || 0);
      return value < 0 && item.key !== "dividends" ? colors.negative : item.color;
    }),
    borderRadius: 4,
  }));
  createChart("annual", canvas, {
    type: "bar",
    data: { labels, datasets },
    plugins: [emptyChartPlugin],
    options: chartOptions({
      emptyText: "尚無年度資料",
      tooltipTitle: (items) => (items.length ? formatXAxisLabel(annualXValue(rows[items[0].dataIndex]), "full") : ""),
      tooltipLabel: (context) => {
        const item = series[context.datasetIndex];
        return `${item.label}: ${item.formatter(context.parsed.y)}`;
      },
      yFormatter: options.yFormatter,
    }),
  });
}

function drawAllocationPie(canvas, positions, currency) {
  const labels = positions.map((position) => `${position.symbol} · ${position.currency}`);
  const values = positions.map((position) => Number(position.market_value || 0));
  createChart("allocation", canvas, {
    type: "pie",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: positions.map((_position, index) => allocationColor(index)),
          borderColor: "#fff",
          borderWidth: 2,
          hoverOffset: 8,
        },
      ],
    },
    plugins: [emptyChartPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        emptyMessage: { text: "尚無持股資料" },
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => (items.length ? labels[items[0].dataIndex] : ""),
            label: (context) => {
              const position = positions[context.dataIndex];
              return [
                `市值: ${money(position.market_value, currency)}`,
                `占比: ${pct(position.allocation_pct)}`,
                `股數: ${number(position.quantity)}`,
              ];
            },
          },
        },
      },
    },
  });
}

function chartOptions({ emptyText, tooltipTitle, tooltipLabel, yFormatter }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      emptyMessage: { text: emptyText },
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: tooltipTitle,
          label: tooltipLabel,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: colors.text, maxRotation: 0, autoSkip: true },
      },
      y: {
        grid: { color: colors.grid },
        ticks: { color: colors.text, callback: (value) => yFormatter(Number(value)) },
      },
    },
  };
}

function createChart(key, canvas, config) {
  destroyChart(key);
  if (!window.Chart) {
    drawCanvasMessage(canvas, "Chart.js 載入失敗");
    return;
  }
  state.charts[key] = new window.Chart(canvas, config);
}

function destroyChart(key) {
  if (state.charts[key]) {
    state.charts[key].destroy();
    state.charts[key] = null;
  }
}

function drawCanvasMessage(canvas, text) {
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(320, Math.round(rect.width || 360));
  canvas.height = Math.max(260, Math.round(rect.height || 320));
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = colors.text;
  context.font = "14px Segoe UI, Noto Sans TC, Arial, sans-serif";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(text, canvas.width / 2, canvas.height / 2);
}

function byId(id) {
  return document.getElementById(id);
}

function setStatus(text) {
  byId("statusText").textContent = text;
}

function toInputDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function previousWeekday(date) {
  const current = new Date(date);
  while (current.getDay() === 0 || current.getDay() === 6) {
    current.setDate(current.getDate() - 1);
  }
  return current;
}

function money(value, currency = reportCurrency()) {
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency,
    currencyDisplay: "code",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function signedMoney(value, currency = reportCurrency()) {
  const amount = Number(value || 0);
  return `${amount < 0 ? "-" : ""}${money(Math.abs(amount), currency)}`;
}

function compactMoney(value, currency = reportCurrency()) {
  const compact = new Intl.NumberFormat("zh-TW", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
  return `${currency} ${compact}`;
}

function number(value) {
  return formatNumber(value, { maximumFractionDigits: 4 });
}

function pct(value) {
  return `${formatNumber(Number(value || 0) * 100, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function formatNumber(value, options) {
  return new Intl.NumberFormat("zh-TW", options).format(Number(value || 0));
}

function classFor(value) {
  return Number(value || 0) < 0 ? "negative" : "positive";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

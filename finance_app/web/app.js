const NEW_PORTFOLIO_VALUE = "__new__";

const state = {
  interval: "monthly",
  portfolios: [],
  records: { trades: [], dividends: [] },
  overview: null,
  summary: null,
  performance: { points: [], annual: [] },
  allocation: null,
  charts: { performance: null, annual: null, allocation: null },
  view: "dashboard",
  editingRecord: null,
  defaultRecordDate: "",
  firstActivity: null,
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
  setupViewTabs();
  setupDividendImportPanel();
  setupRecordsPage();
}

function setupViewTabs() {
  if (byId("viewTabs")) {
    return;
  }
  const header = document.querySelector(".app-header");
  const refreshButton = byId("refreshButton");
  const nav = document.createElement("nav");
  nav.id = "viewTabs";
  nav.className = "view-tabs";
  nav.setAttribute("aria-label", "主要頁面");
  nav.innerHTML = `
    <button class="active" type="button" data-view-tab="dashboard">績效總覽</button>
    <button type="button" data-view-tab="records">紀錄管理</button>`;
  header.insertBefore(nav, refreshButton);
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

function setupRecordsPanelLegacy() {
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

function setupRecordsPage() {
  const tableBody = byId("recordsBody");
  if (!tableBody || byId("recordsView")) {
    return;
  }
  const shell = document.querySelector(".app-shell");
  const panel = tableBody.closest(".table-panel");
  const tableWrap = tableBody.closest(".table-wrap");
  const recordsView = document.createElement("section");
  recordsView.id = "recordsView";
  recordsView.className = "records-view app-view hidden";
  shell.appendChild(recordsView);
  panel.classList.remove("compact");
  panel.classList.add("records-panel", "records-page");
  recordsView.appendChild(panel);
  panel.querySelector("h2").textContent = "紀錄管理";
  ["日期", "股票", "投組", "幣別", "類型", "金額", "操作"].forEach((label, index) => {
    const cell = panel.querySelectorAll("thead th")[index];
    if (cell) {
      cell.textContent = label;
    }
  });

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
  recordsView.insertAdjacentHTML(
    "beforeend",
    `
      <section class="form-panel record-edit-panel hidden" id="recordEditPanel">
        <header>
          <h2>編輯紀錄</h2>
        </header>
        <form id="recordEditForm" class="record-form">
          <input name="kind" type="hidden" />
          <input name="id" type="hidden" />
          <label>
            日期
            <input name="date" type="date" required />
          </label>
          <label>
            股票代號
            <input name="symbol" type="text" required />
          </label>
          <label>
            投資組合
            <select name="portfolio" data-portfolio-select required></select>
          </label>
          <label class="portfolio-new hidden">
            新投資組合
            <input name="new_portfolio" type="text" />
          </label>
          <label>
            幣別
            <select name="currency">
              <option value="TWD">TWD</option>
              <option value="USD">USD</option>
            </select>
          </label>
          <div class="record-form-group" data-edit-section="trade">
            <label>
              方向
              <select name="side">
                <option value="BUY">買進</option>
                <option value="SELL">賣出</option>
              </select>
            </label>
            <label>
              股數
              <input name="quantity" type="number" min="0" step="0.000001" />
            </label>
            <label>
              成交價
              <input name="price" type="number" min="0" step="0.000001" />
            </label>
            <label>
              手續費
              <input name="fees" type="number" min="0" step="0.000001" />
            </label>
          </div>
          <div class="record-form-group hidden" data-edit-section="dividend">
            <label>
              配息總額
              <input name="gross_amount" type="number" min="0" step="0.000001" />
            </label>
            <label>
              稅額
              <input name="tax" type="number" min="0" step="0.000001" />
            </label>
          </div>
          <label class="full">
            備註
            <input name="notes" type="text" />
          </label>
          <p class="form-error" hidden></p>
          <div class="form-actions">
            <button class="primary" type="submit">儲存修改</button>
            <button class="secondary" id="cancelRecordEditButton" type="button">取消</button>
          </div>
        </form>
      </section>`,
  );
}

function setDefaultDates(defaults = null) {
  const today = new Date();
  const fallbackStart = new Date(today.getFullYear(), 0, 1);
  const fallbackAsOf = previousWeekday(today);
  state.defaultRecordDate = defaults?.today || toInputDate(today);
  byId("asOfInput").value = defaults?.as_of || toInputDate(fallbackAsOf);
  byId("endInput").value = defaults?.end || toInputDate(today);
  byId("startInput").value = defaults?.start || toInputDate(fallbackStart);
  state.firstActivity = defaults?.first_activity || null;
  populateRangeScope();
  document.querySelectorAll("form input[name='date']").forEach((input) => {
    input.value = state.defaultRecordDate;
  });
}

// Fills the 範圍 dropdown with 全部 + each year from the first activity to now.
// Defaults to the current year (matching the default 今年 date range); preserves the
// user's choice on subsequent refreshes.
function populateRangeScope() {
  const select = byId("rangeScope");
  if (!select) {
    return;
  }
  const currentYear = new Date().getFullYear();
  const desired = select.dataset.populated ? select.value : String(currentYear);
  const firstYear = state.firstActivity ? Number(state.firstActivity.slice(0, 4)) : currentYear;
  const startYear = Math.min(firstYear, currentYear);
  const options = ['<option value="all">全部</option>'];
  for (let year = currentYear; year >= startYear; year -= 1) {
    options.push(`<option value="${year}">${year === currentYear ? `今年（${year}）` : year}</option>`);
  }
  select.innerHTML = options.join("");
  select.value = desired;
  if (!select.value) {
    select.value = String(currentYear);
  }
  select.dataset.populated = "true";
}

// Translates the 範圍 selection into start/end (and as_of) dates, then reloads.
// 全部 spans the first activity to today; a year spans Jan 1 to Dec 31 (or today for
// the current year). The start/end inputs stay editable for manual fine-tuning.
function applyRangeScope() {
  const select = byId("rangeScope");
  if (!select) {
    return;
  }
  const today = new Date();
  const todayStr = toInputDate(today);
  if (select.value === "all") {
    byId("startInput").value = state.firstActivity || toInputDate(new Date(today.getFullYear(), 0, 1));
    byId("endInput").value = todayStr;
    byId("asOfInput").value = todayStr;
  } else {
    const year = Number(select.value);
    const end = year === today.getFullYear() ? todayStr : `${year}-12-31`;
    byId("startInput").value = `${year}-01-01`;
    byId("endInput").value = end;
    byId("asOfInput").value = end;
  }
  refreshData();
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
  document.querySelectorAll("[data-view-tab]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.viewTab));
  });
  ["asOfInput", "startInput", "endInput", "portfolioFilter", "currencyFilter"].forEach((id) => {
    byId(id).addEventListener("change", refreshData);
  });
  byId("rangeScope").addEventListener("change", applyRangeScope);

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
  byId("recordEditForm").addEventListener("submit", submitRecordEdit);
  byId("cancelRecordEditButton").addEventListener("click", cancelRecordEdit);
  const toggleRecordsButton = byId("toggleRecordsButton");
  if (toggleRecordsButton) {
    toggleRecordsButton.addEventListener("click", toggleRecordsPanel);
  }
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
  await runRefresh(async () => {
    await refreshPortfolios();
    await refreshDashboardData();
  });
}

async function refreshData() {
  await runRefresh(refreshDashboardData);
}

async function runRefresh(task) {
  setStatus("更新中");
  try {
    await task();
    const warnings = state.summary?.warnings || [];
    setStatus(warnings.length ? warnings.join(" ") : "已更新");
  } catch (error) {
    setStatus(error.message || "更新失敗");
  }
}

async function refreshDashboardData() {
  const tasks = [refreshOverview(), refreshSummary().then(refreshAllocation), refreshPerformance()];
  if (state.recordsVisible) {
    tasks.push(refreshRecords());
  }
  await Promise.all(tasks);
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

async function refreshOverview() {
  // Fixed headline KPIs (all-time + YTD); independent of the 範圍 date selector.
  state.overview = await apiGet(`/api/overview?${currencyQuery().slice(1)}${portfolioQuery()}`);
  renderOverview();
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
  const summary = state.summary;
  state.allocation = summary
    ? {
        as_of: summary.as_of,
        start: summary.start,
        end: summary.end,
        portfolio: summary.portfolio,
        currency: summary.currency,
        selected: summary,
        overall: summary,
        portfolios: [],
      }
    : null;
  renderAllocation();
}

async function submitTrade(event) {
  event.preventDefault();
  const form = event.currentTarget;
  setFormError(form, "");
  let payload;
  try {
    payload = formPayloadWithPortfolio(form);
  } catch (error) {
    setFormError(form, error.message);
    setStatus(error.message);
    return;
  }
  payload.quantity = Number(payload.quantity);
  payload.price = Number(payload.price);
  payload.fees = Number(payload.fees || 0);
  try {
    await apiPost("/api/trades", payload);
  } catch (error) {
    setFormError(form, error.message || "新增交易失敗");
    return;
  }
  resetRecordForm(form);
  await refreshAll();
}

async function submitDividend(event) {
  event.preventDefault();
  const form = event.currentTarget;
  setFormError(form, "");
  let payload;
  try {
    payload = formPayloadWithPortfolio(form);
  } catch (error) {
    setFormError(form, error.message);
    setStatus(error.message);
    return;
  }
  payload.gross_amount = Number(payload.gross_amount);
  payload.tax = Number(payload.tax || 0);
  try {
    await apiPost("/api/dividends", payload);
  } catch (error) {
    setFormError(form, error.message || "新增配息失敗");
    return;
  }
  resetRecordForm(form);
  await refreshAll();
}

async function submitRecordEdit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  setFormError(form, "");
  const kind = form.elements.kind.value;
  const id = form.elements.id.value;
  let payload;
  try {
    payload = formPayloadWithPortfolio(form);
  } catch (error) {
    setFormError(form, error.message);
    setStatus(error.message);
    return;
  }
  delete payload.kind;
  delete payload.id;
  const path = kind === "trade" ? `/api/trades/${encodeURIComponent(id)}` : `/api/dividends/${encodeURIComponent(id)}`;
  if (kind === "trade") {
    payload.quantity = Number(payload.quantity);
    payload.price = Number(payload.price);
    payload.fees = Number(payload.fees || 0);
    delete payload.gross_amount;
    delete payload.tax;
  } else {
    payload.gross_amount = Number(payload.gross_amount);
    payload.tax = Number(payload.tax || 0);
    delete payload.side;
    delete payload.quantity;
    delete payload.price;
    delete payload.fees;
  }
  try {
    await apiPut(path, payload);
  } catch (error) {
    setFormError(form, error.message || "儲存修改失敗");
    return;
  }
  cancelRecordEdit();
  await refreshAll();
}

async function deleteRecord(kind, id) {
  const record = (state.records.records || []).find((item) => item.kind === kind && item.id === id);
  const label = record ? `${record.date} ${record.symbol} ${recordTypeLabel(record)}` : "這筆紀錄";
  if (!window.confirm(`確定要刪除 ${label}？`)) {
    return;
  }
  if (state.editingRecord?.kind === kind && state.editingRecord?.id === id) {
    cancelRecordEdit();
  }
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
    setImportStatus(importResultText("交易", payload));
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
    setImportStatus(importResultText("配息", payload));
    await refreshAll();
  } catch (error) {
    setImportStatus(error.message || "配息匯入失敗");
  }
}

// Fixed headline KPIs shown like a broker dashboard. Total return / market value /
// annualized / dividends are all-time; YTD and realized cover the current year. These do
// NOT follow the 範圍 selector (which only drives the charts and holdings below).
function renderOverview() {
  const overview = state.overview;
  if (!overview) {
    return;
  }
  const currency = overview.currency || reportCurrency();
  const year = overview.year;
  byId("metricGrid").innerHTML = [
    metric("總報酬率", pct(overview.total_return_pct), `${signedMoney(overview.total_gain, currency)} · 全部`, overview.total_gain),
    metric("YTD績效", signedMoney(overview.ytd_gain, currency), `${pct(overview.ytd_return_pct)} · ${year}`, overview.ytd_gain),
    metric("今年已實現", signedMoney(overview.ytd_realized_gain, currency), `${year} 落袋 · ${currency}`, overview.ytd_realized_gain),
    metric("總市值", money(overview.market_value, currency), `目前持有 · ${currency}`, overview.market_value),
    metric(
      "年化報酬率",
      overview.annualized_return_pct == null ? "—" : pct(overview.annualized_return_pct),
      "XIRR · 全部",
      overview.annualized_return_pct,
    ),
    metric("累計配息", money(overview.dividends, currency), `稅後 · ${currency}`, overview.dividends),
  ].join("");
}

function renderSummary() {
  const summary = state.summary || {};
  const currency = summary.currency || reportCurrency();

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

function renderRecordsLegacy() {
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

function renderRecords() {
  const tableBody = byId("recordsBody");
  if (!tableBody || !state.recordsVisible) {
    return;
  }

  const rows = state.records.records || [];
  tableBody.innerHTML = rows.length
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
          <td>
            <div class="row-actions">
              <button class="secondary" type="button" data-edit-kind="${escapeHtml(row.kind)}" data-edit-id="${escapeHtml(row.id)}">編輯</button>
              <button class="danger" type="button" data-delete-kind="${escapeHtml(row.kind)}" data-delete-id="${escapeHtml(row.id)}">刪除</button>
            </div>
          </td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="7">尚無紀錄</td></tr>`;

  byId("recordPageText").textContent = `${state.records.page || 1} / ${state.records.total_pages || 1} · ${state.records.total || 0} 筆`;
  byId("recordPrevPage").disabled = (state.records.page || 1) <= 1;
  byId("recordNextPage").disabled = (state.records.page || 1) >= (state.records.total_pages || 1);
  document.querySelectorAll("[data-edit-id]").forEach((button) => {
    button.addEventListener("click", () => startRecordEdit(button.dataset.editKind, button.dataset.editId));
  });
  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", () => deleteRecord(button.dataset.deleteKind, button.dataset.deleteId));
  });
}

function recordTypeLabelLegacy(row) {
  if (row.kind === "dividend") {
    return "配息";
  }
  return row.type === "BUY" ? "買進" : "賣出";
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

function switchView(view) {
  state.view = view === "records" ? "records" : "dashboard";
  state.recordsVisible = state.view === "records";
  document.querySelectorAll("[data-view-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewTab === state.view);
  });
  document.querySelector(".workspace").classList.toggle("hidden", state.view !== "dashboard");
  document.querySelector(".side-rail").classList.toggle("hidden", state.view !== "dashboard");
  byId("recordsView").classList.toggle("hidden", state.view !== "records");
  document.querySelector(".app-shell").classList.toggle("records-mode", state.view === "records");
  if (state.recordsVisible) {
    refreshRecords();
  }
}

function startRecordEdit(kind, id) {
  const record = (state.records.records || []).find((item) => item.kind === kind && item.id === id);
  if (!record) {
    return;
  }
  state.editingRecord = record;
  const panel = byId("recordEditPanel");
  const form = byId("recordEditForm");
  panel.classList.remove("hidden");
  form.elements.kind.value = record.kind;
  form.elements.id.value = record.id;
  form.elements.date.value = record.date || "";
  form.elements.symbol.value = record.symbol || "";
  form.elements.portfolio.value = record.portfolio || selectedPortfolioForForm();
  form.elements.currency.value = record.currency || inferCurrency(record.symbol);
  form.elements.notes.value = record.notes || "";
  form.elements.side.value = record.side || record.type || "BUY";
  form.elements.quantity.value = record.quantity ?? "";
  form.elements.price.value = record.price ?? "";
  form.elements.fees.value = record.fees ?? 0;
  form.elements.gross_amount.value = record.gross_amount ?? "";
  form.elements.tax.value = record.tax ?? 0;
  syncNewPortfolioField(form);
  setEditSections(record.kind);
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelRecordEdit() {
  state.editingRecord = null;
  const panel = byId("recordEditPanel");
  const form = byId("recordEditForm");
  if (form) {
    form.reset();
    syncNewPortfolioField(form);
    setFormError(form, "");
  }
  if (panel) {
    panel.classList.add("hidden");
  }
}

function setEditSections(kind) {
  const isTrade = kind === "trade";
  document.querySelector('[data-edit-section="trade"]').classList.toggle("hidden", !isTrade);
  document.querySelector('[data-edit-section="dividend"]').classList.toggle("hidden", isTrade);
  ["side", "quantity", "price"].forEach((name) => {
    byId("recordEditForm").elements[name].required = isTrade;
  });
  byId("recordEditForm").elements.gross_amount.required = !isTrade;
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
  if (state.performance.max_drawdown_pct != null) {
    byId("performanceLegend").insertAdjacentHTML(
      "beforeend",
      `<span class="legend-item">最大回撤 ${pct(state.performance.max_drawdown_pct)}</span>`,
    );
  }

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

async function apiPut(path, payload) {
  return api(path, {
    method: "PUT",
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
      record._row_number = index + 2;
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
      record._row_number = index + 2;
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

function setFormError(form, message) {
  const element = form.querySelector(".form-error");
  if (!element) {
    return;
  }
  element.textContent = message || "";
  element.hidden = !message;
}

function importResultTextLegacy(label, payload) {
  const skipped = payload.skipped_duplicates || 0;
  const base = `已匯入 ${payload.imported_count} 筆${label}`;
  return skipped ? `${base}，略過 ${skipped} 筆重複` : base;
}

function importResultText(label, payload) {
  const skipped = payload.skipped_duplicates || 0;
  const base = `已匯入 ${payload.imported_count} 筆${label}`;
  if (!skipped) {
    return base;
  }
  const duplicates = payload.duplicate_records || [];
  const details = duplicates.slice(0, 10).map((item) => {
    const reason = duplicateReasonLabel(item.reason);
    const portfolio = item.portfolio ? ` / ${item.portfolio}` : "";
    return `第 ${item.row} 列：${item.date} ${item.symbol}${portfolio}，${reason}`;
  });
  const suffix = duplicates.length > details.length ? `\n另有 ${duplicates.length - details.length} 筆重複未列出` : "";
  return `${base}，略過 ${skipped} 筆重複\n${details.join("\n")}${suffix}`;
}

function duplicateReasonLabel(reason) {
  if (reason === "duplicate_in_file") {
    return "同一檔案內重複";
  }
  return "已存在";
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
  form.elements.date.value = state.defaultRecordDate || byId("endInput").value;
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

const state = {
  interval: "monthly",
  portfolios: [],
  records: { trades: [], dividends: [] },
  summary: null,
  performance: { points: [], annual: [] },
  allocation: null,
};

const colors = {
  market: "#2563eb",
  gain: "#0f9f6e",
  dividend: "#d97706",
  realized: "#7c3aed",
  negative: "#d14343",
  grid: "#d8dee6",
  text: "#667085",
};

document.addEventListener("DOMContentLoaded", () => {
  setDefaultDates();
  bindEvents();
  refreshAll();
});

function setDefaultDates() {
  const today = new Date();
  const oneYearAgo = new Date(today);
  oneYearAgo.setFullYear(today.getFullYear() - 1);
  byId("asOfInput").value = toInputDate(today);
  byId("endInput").value = toInputDate(today);
  byId("startInput").value = toInputDate(oneYearAgo);
  document.querySelectorAll("form input[name='date']").forEach((input) => {
    input.value = toInputDate(today);
  });
}

function bindEvents() {
  byId("refreshButton").addEventListener("click", refreshAll);
  ["asOfInput", "startInput", "endInput", "portfolioFilter"].forEach((id) => byId(id).addEventListener("change", refreshAll));

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

  byId("tradeForm").addEventListener("submit", submitTrade);
  byId("dividendForm").addEventListener("submit", submitDividend);
}

async function refreshAll() {
  setStatus("更新中");
  try {
    await refreshPortfolios();
    await Promise.all([refreshRecords(), refreshSummary(), refreshPerformance(), refreshAllocation()]);
    setStatus("已更新");
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
  state.records = await apiGet("/api/records");
  renderRecords();
}

async function refreshSummary() {
  const asOf = byId("asOfInput").value;
  state.summary = await apiGet(`/api/summary?as_of=${encodeURIComponent(asOf)}${portfolioQuery()}`);
  renderSummary();
}

async function refreshPerformance() {
  const start = byId("startInput").value;
  const end = byId("endInput").value;
  state.performance = await apiGet(
    `/api/performance?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&interval=${state.interval}${portfolioQuery()}`,
  );
  renderPerformance();
}

async function refreshAllocation() {
  const asOf = byId("asOfInput").value;
  state.allocation = await apiGet(`/api/allocation?as_of=${encodeURIComponent(asOf)}`);
  renderAllocation();
}

async function submitTrade(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formToPayload(form);
  payload.quantity = Number(payload.quantity);
  payload.price = Number(payload.price);
  payload.fees = Number(payload.fees || 0);
  await apiPost("/api/trades", payload);
  form.reset();
  form.elements.date.value = byId("asOfInput").value;
  form.elements.portfolio.value = selectedPortfolioForForm();
  form.elements.fees.value = "0";
  await refreshAll();
}

async function submitDividend(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = formToPayload(form);
  payload.gross_amount = Number(payload.gross_amount);
  payload.tax = Number(payload.tax || 0);
  await apiPost("/api/dividends", payload);
  form.reset();
  form.elements.date.value = byId("asOfInput").value;
  form.elements.portfolio.value = selectedPortfolioForForm();
  form.elements.tax.value = "0";
  await refreshAll();
}

async function deleteRecord(kind, id) {
  const path = kind === "trade" ? `/api/trades/${encodeURIComponent(id)}` : `/api/dividends/${encodeURIComponent(id)}`;
  await apiDelete(path);
  await refreshAll();
}

function renderSummary() {
  const summary = state.summary || {};
  byId("metricGrid").innerHTML = [
    metric("市值", money(summary.market_value), "Yahoo 收盤價"),
    metric("總損益", signedMoney(summary.total_gain), pct(summary.return_pct)),
    metric("已實現", signedMoney(summary.realized_gain), "賣出損益"),
    metric("累計配息", money(summary.dividends), "稅後"),
  ].join("");

  const rows = summary.positions || [];
  byId("positionsBody").innerHTML = rows.length
    ? rows
        .map(
          (row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${number(row.quantity)}</td>
          <td>${money(row.average_cost)}</td>
          <td>${money(row.last_price)}</td>
          <td>${money(row.market_value)}</td>
          <td>${pct(row.allocation_pct)}</td>
          <td class="${classFor(row.unrealized_gain)}">${signedMoney(row.unrealized_gain)}</td>
          <td>${money(row.dividends)}</td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="8">尚無持股</td></tr>`;

  if (summary.warnings && summary.warnings.length) {
    setStatus(summary.warnings.join(" "));
  }
}

function renderRecords() {
  const trades = (state.records.trades || []).map((trade) => ({
    date: trade.date,
    symbol: trade.symbol,
    portfolio: trade.portfolio,
    type: trade.side === "BUY" ? "買進" : "賣出",
    amount: trade.quantity * trade.price + Number(trade.fees || 0),
    id: trade.id,
    kind: "trade",
  }));
  const dividends = (state.records.dividends || []).map((dividend) => ({
    date: dividend.date,
    symbol: dividend.symbol,
    portfolio: dividend.portfolio,
    type: "配息",
    amount: dividend.net_amount,
    id: dividend.id,
    kind: "dividend",
  }));
  const rows = trades.concat(dividends).sort((a, b) => b.date.localeCompare(a.date) || a.symbol.localeCompare(b.symbol));

  byId("recordsBody").innerHTML = rows.length
    ? rows
        .map(
          (row) => `
        <tr>
          <td>${escapeHtml(row.date)}</td>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.portfolio)}</td>
          <td>${escapeHtml(row.type)}</td>
          <td>${money(row.amount)}</td>
          <td><button class="danger" type="button" data-delete-kind="${row.kind}" data-delete-id="${row.id}">刪除</button></td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="6">尚無紀錄</td></tr>`;

  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", () => deleteRecord(button.dataset.deleteKind, button.dataset.deleteId));
  });
}

function renderPortfolioOptions() {
  const select = byId("portfolioFilter");
  const current = select.value || "All";
  const portfolios = state.portfolios.length ? state.portfolios : ["General"];
  select.innerHTML = `<option value="All">全部</option>${portfolios
    .map((portfolio) => `<option value="${escapeHtml(portfolio)}">${escapeHtml(portfolio)}</option>`)
    .join("")}`;
  select.value = portfolios.includes(current) || current === "All" ? current : "All";
  byId("portfolioOptions").innerHTML = portfolios
    .map((portfolio) => `<option value="${escapeHtml(portfolio)}"></option>`)
    .join("");
  document.querySelectorAll("form input[name='portfolio']").forEach((input) => {
    if (!input.value) {
      input.value = select.value === "All" ? "General" : select.value;
    }
  });
}

function renderAllocation() {
  const allocation = state.allocation;
  if (!allocation) {
    byId("allocationGrid").innerHTML = "";
    return;
  }
  const groups = [
    { title: "整體", market_value: allocation.overall.market_value, positions: allocation.overall.positions || [] },
    ...(allocation.portfolios || []).map((portfolio) => ({
      title: portfolio.portfolio,
      market_value: portfolio.market_value,
      positions: portfolio.positions || [],
    })),
  ];
  byId("allocationGrid").innerHTML = groups.map(renderAllocationGroup).join("");
}

function renderAllocationGroup(group) {
  const positions = [...group.positions].sort((a, b) => Number(b.allocation_pct || 0) - Number(a.allocation_pct || 0));
  const rows = positions.length
    ? positions
        .map(
          (position) => `
      <div class="allocation-row">
        <span class="allocation-symbol">${escapeHtml(position.symbol)}</span>
        <span class="allocation-track"><span class="allocation-fill" style="width:${Math.max(0, Number(position.allocation_pct || 0) * 100)}%"></span></span>
        <span class="allocation-percent">${pct(position.allocation_pct)}</span>
      </div>`,
        )
        .join("")
    : `<p class="empty">尚無持股</p>`;
  return `<section class="allocation-group"><h3>${escapeHtml(group.title)} <span>${money(group.market_value)}</span></h3>${rows}</section>`;
}

function renderPerformance() {
  renderLegend("performanceLegend", [
    ["市值", colors.market],
    ["總損益", colors.gain],
    ["累計配息", colors.dividend],
  ]);
  renderLegend("annualLegend", [
    ["年度損益", colors.gain],
    ["年度配息", colors.dividend],
  ]);

  drawLineChart(byId("performanceChart"), state.performance.points || [], [
    { key: "market_value", label: "市值", color: colors.market },
    { key: "total_gain", label: "總損益", color: colors.gain },
    { key: "dividends", label: "累計配息", color: colors.dividend },
  ]);
  drawBarChart(byId("annualChart"), state.performance.annual || []);
}

function drawLineChart(svg, points, series) {
  clearSvg(svg);
  const width = 720;
  const height = 300;
  const pad = { top: 22, right: 24, bottom: 42, left: 68 };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!points.length) {
    drawEmpty(svg, width, height, "尚無圖表資料");
    return;
  }

  const values = points.flatMap((point) => series.map((item) => Number(point[item.key] || 0)));
  const [minY, maxY] = extent(values);
  drawGrid(svg, width, height, pad, minY, maxY);

  series.forEach((item) => {
    const path = points
      .map((point, index) => {
        const x = scale(index, 0, Math.max(points.length - 1, 1), pad.left, width - pad.right);
        const y = scale(Number(point[item.key] || 0), minY, maxY, height - pad.bottom, pad.top);
        return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
    addSvg(svg, "path", {
      d: path,
      fill: "none",
      stroke: item.color,
      "stroke-width": "3",
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    });
  });

  drawXAxisLabels(svg, points, width, height, pad);
}

function drawBarChart(svg, rows) {
  clearSvg(svg);
  const width = 560;
  const height = 300;
  const pad = { top: 22, right: 24, bottom: 42, left: 68 };
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!rows.length) {
    drawEmpty(svg, width, height, "尚無年度資料");
    return;
  }

  const values = rows.flatMap((row) => [Number(row.gain || 0), Number(row.dividends || 0)]);
  const [minY, maxY] = extent(values.concat([0]));
  drawGrid(svg, width, height, pad, minY, maxY);
  const groupWidth = (width - pad.left - pad.right) / rows.length;
  const barWidth = Math.min(34, groupWidth / 3);
  const zeroY = scale(0, minY, maxY, height - pad.bottom, pad.top);

  rows.forEach((row, index) => {
    const center = pad.left + groupWidth * index + groupWidth / 2;
    drawBar(svg, center - barWidth, row.gain, barWidth, minY, maxY, zeroY, height, pad, row.gain >= 0 ? colors.gain : colors.negative);
    drawBar(svg, center + 4, row.dividends, barWidth, minY, maxY, zeroY, height, pad, colors.dividend);
    addSvg(svg, "text", {
      x: center,
      y: height - 14,
      "text-anchor": "middle",
      fill: colors.text,
      "font-size": "12",
    }).textContent = row.year;
  });
}

function drawBar(svg, x, value, width, minY, maxY, zeroY, height, pad, color) {
  const y = scale(Number(value || 0), minY, maxY, height - pad.bottom, pad.top);
  const rectY = Math.min(y, zeroY);
  const rectHeight = Math.max(1, Math.abs(zeroY - y));
  addSvg(svg, "rect", {
    x: x.toFixed(2),
    y: rectY.toFixed(2),
    width: width.toFixed(2),
    height: rectHeight.toFixed(2),
    fill: color,
    rx: "4",
  });
}

function drawGrid(svg, width, height, pad, minY, maxY) {
  for (let i = 0; i <= 4; i += 1) {
    const value = minY + ((maxY - minY) * i) / 4;
    const y = scale(value, minY, maxY, height - pad.bottom, pad.top);
    addSvg(svg, "line", {
      x1: pad.left,
      x2: width - pad.right,
      y1: y,
      y2: y,
      stroke: colors.grid,
      "stroke-width": "1",
    });
    addSvg(svg, "text", {
      x: pad.left - 10,
      y: y + 4,
      "text-anchor": "end",
      fill: colors.text,
      "font-size": "12",
    }).textContent = compactMoney(value);
  }
}

function drawXAxisLabels(svg, points, width, height, pad) {
  const indexes = uniqueIndexes([0, Math.floor((points.length - 1) / 2), points.length - 1]);
  indexes.forEach((index) => {
    const x = scale(index, 0, Math.max(points.length - 1, 1), pad.left, width - pad.right);
    addSvg(svg, "text", {
      x,
      y: height - 14,
      "text-anchor": "middle",
      fill: colors.text,
      "font-size": "12",
    }).textContent = points[index].date;
  });
}

function drawEmpty(svg, width, height, label) {
  addSvg(svg, "text", {
    x: width / 2,
    y: height / 2,
    "text-anchor": "middle",
    fill: colors.text,
    "font-size": "14",
  }).textContent = label;
}

function renderLegend(id, items) {
  byId(id).innerHTML = items
    .map(([label, color]) => `<span class="legend-item"><span class="swatch" style="background:${color}"></span>${label}</span>`)
    .join("");
}

function metric(label, value, subtext) {
  return `<article class="metric"><span>${label}</span><strong class="${value.startsWith("-") ? "negative" : ""}">${value}</strong><small>${subtext}</small></article>`;
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

function formToPayload(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function portfolioQuery() {
  const portfolio = byId("portfolioFilter").value;
  return portfolio && portfolio !== "All" ? `&portfolio=${encodeURIComponent(portfolio)}` : "";
}

function selectedPortfolioForForm() {
  const portfolio = byId("portfolioFilter").value;
  return portfolio && portfolio !== "All" ? portfolio : "General";
}

function byId(id) {
  return document.getElementById(id);
}

function setStatus(text) {
  byId("statusText").textContent = text;
}

function toInputDate(date) {
  return date.toISOString().slice(0, 10);
}

function money(value) {
  return formatNumber(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function signedMoney(value) {
  const amount = Number(value || 0);
  return `${amount < 0 ? "-" : ""}${money(Math.abs(amount))}`;
}

function compactMoney(value) {
  return new Intl.NumberFormat("zh-TW", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
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

function clearSvg(svg) {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

function addSvg(svg, name, attrs) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
  svg.appendChild(element);
  return element;
}

function extent(values) {
  let min = Math.min(...values, 0);
  let max = Math.max(...values, 0);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const padding = (max - min) * 0.08;
  return [min - padding, max + padding];
}

function scale(value, domainMin, domainMax, rangeMin, rangeMax) {
  if (domainMax === domainMin) {
    return (rangeMin + rangeMax) / 2;
  }
  return rangeMin + ((value - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
}

function uniqueIndexes(indexes) {
  return [...new Set(indexes.filter((index) => index >= 0))];
}

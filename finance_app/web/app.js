const NEW_PORTFOLIO_VALUE = "__new__";

const state = {
  interval: "monthly",
  portfolios: [],
  records: { trades: [], dividends: [] },
  summary: null,
  performance: { points: [], annual: [] },
  allocation: null,
  resizeTimer: null,
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

  window.addEventListener("resize", scheduleChartRender);
  byId("tradeForm").addEventListener("submit", submitTrade);
  byId("dividendForm").addEventListener("submit", submitDividend);
  byId("downloadTradeTemplateButton").addEventListener("click", downloadTradeTemplate);
  byId("importTradesButton").addEventListener("click", importTradesFromFile);
}

async function refreshAll() {
  setStatus("更新中");
  try {
    await refreshPortfolios();
    await Promise.all([refreshRecords(), refreshSummary(), refreshPerformance(), refreshAllocation()]);
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
  state.records = await apiGet("/api/records");
  renderRecords();
}

async function refreshSummary() {
  const asOf = byId("asOfInput").value;
  state.summary = await apiGet(`/api/summary?as_of=${encodeURIComponent(asOf)}${portfolioQuery()}${currencyQuery()}`);
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
  const asOf = byId("asOfInput").value;
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

function renderSummary() {
  const summary = state.summary || {};
  const currency = summary.currency || reportCurrency();
  byId("metricGrid").innerHTML = [
    metric("市值", money(summary.market_value, currency), `Yahoo 收盤價 · ${currency}`, summary.market_value),
    metric("總損益", signedMoney(summary.total_gain, currency), pct(summary.return_pct), summary.total_gain),
    metric("已實現", signedMoney(summary.realized_gain, currency), `賣出損益 · ${currency}`, summary.realized_gain),
    metric("累計配息", money(summary.dividends, currency), `稅後 · ${currency}`, summary.dividends),
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
  const trades = (state.records.trades || []).map((trade) => ({
    date: trade.date,
    symbol: trade.symbol,
    portfolio: trade.portfolio,
    currency: trade.currency,
    type: trade.side === "BUY" ? "買進" : "賣出",
    amount: trade.quantity * trade.price + Number(trade.fees || 0),
    id: trade.id,
    kind: "trade",
  }));
  const dividends = (state.records.dividends || []).map((dividend) => ({
    date: dividend.date,
    symbol: dividend.symbol,
    portfolio: dividend.portfolio,
    currency: dividend.currency,
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
          <td>${escapeHtml(row.currency)}</td>
          <td>${escapeHtml(row.type)}</td>
          <td>${money(row.amount, row.currency)}</td>
          <td><button class="danger" type="button" data-delete-kind="${row.kind}" data-delete-id="${row.id}">刪除</button></td>
        </tr>`,
        )
        .join("")
    : `<tr><td class="empty" colspan="7">尚無紀錄</td></tr>`;

  document.querySelectorAll("[data-delete-id]").forEach((button) => {
    button.addEventListener("click", () => deleteRecord(button.dataset.deleteKind, button.dataset.deleteId));
  });
}

function renderPortfolioOptions() {
  const filter = byId("portfolioFilter");
  const filterCurrent = filter.value || "All";
  const portfolios = state.portfolios.length ? state.portfolios : ["General"];
  filter.innerHTML = `<option value="All">全部</option>${portfolios
    .map((portfolio) => `<option value="${escapeHtml(portfolio)}">${escapeHtml(portfolio)}</option>`)
    .join("")}`;
  filter.value = portfolios.includes(filterCurrent) || filterCurrent === "All" ? filterCurrent : "All";

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
    container.innerHTML = "";
    return;
  }
  const currency = allocation.currency || reportCurrency();
  const selected = allocation.selected || allocation.overall || {};
  const positions = [...(selected.positions || [])]
    .filter((position) => Number(position.market_value || 0) > 0)
    .sort((a, b) => Number(b.allocation_pct || 0) - Number(a.allocation_pct || 0));
  const scope = allocation.portfolio && allocation.portfolio !== "All" ? allocation.portfolio : "整體投資";

  container.innerHTML = `
    <div class="allocation-summary">
      <span>範圍</span>
      <strong>${escapeHtml(scope)}</strong>
      <small>${money(selected.market_value, currency)}</small>
    </div>
    <div class="allocation-pie-stage">
      <svg id="allocationPieChart" class="allocation-pie-chart" role="img" aria-label="持股占比圓餅圖"></svg>
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

function drawAllocationPie(svg, positions, currency) {
  clearSvg(svg);
  const { width, height } = chartSize(svg, 480);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const total = positions.reduce((sum, position) => sum + Number(position.market_value || 0), 0);
  if (!positions.length || total <= 0) {
    drawEmpty(svg, width, height, "尚無持股資料");
    return;
  }

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.max(86, Math.min(width, height) * 0.36);
  const hoverGroup = addSvg(svg, "g", { "pointer-events": "none" });
  let startAngle = -90;

  positions.forEach((position, index) => {
    const value = Number(position.market_value || 0);
    const endAngle = index === positions.length - 1 ? 270 : startAngle + (value / total) * 360;
    const segmentAngle = endAngle - startAngle;
    const color = allocationColor(index);
    const segment =
      segmentAngle >= 359.99
        ? addSvg(svg, "circle", { cx: centerX, cy: centerY, r: radius, fill: color })
        : addSvg(svg, "path", { d: pieSlicePath(centerX, centerY, radius, startAngle, endAngle), fill: color });
    segment.classList.add("allocation-slice");
    segment.setAttribute("stroke", "#fff");
    segment.setAttribute("stroke-width", "2");
    segment.setAttribute("tabindex", "0");
    segment.setAttribute(
      "aria-label",
      `${position.symbol} ${pct(position.allocation_pct)} ${money(position.market_value, currency)}`,
    );

    const midpoint = startAngle + segmentAngle / 2;
    const fallbackPoint = {
      x: centerX + Math.cos((midpoint * Math.PI) / 180) * radius * 0.58,
      y: centerY + Math.sin((midpoint * Math.PI) / 180) * radius * 0.58,
    };
    const showTooltip = (event) => {
      document.querySelectorAll(".allocation-slice.active").forEach((item) => item.classList.remove("active"));
      segment.classList.add("active");
      const point = event && "clientX" in event ? svgPointer(svg, event, width, height) : fallbackPoint;
      drawPieHover(hoverGroup, {
        x: point.x,
        y: point.y,
        width,
        height,
        title: `${position.symbol} · ${position.currency}`,
        rows: [
          { label: "市值", value: money(position.market_value, currency), color },
          { label: "占比", value: pct(position.allocation_pct), color },
          { label: "股數", value: number(position.quantity), color },
          { label: "原幣", value: position.currency, color },
        ],
      });
    };
    const clearTooltip = () => {
      segment.classList.remove("active");
      clearSvg(hoverGroup);
    };
    segment.addEventListener("mouseenter", showTooltip);
    segment.addEventListener("mousemove", showTooltip);
    segment.addEventListener("focus", showTooltip);
    segment.addEventListener("mouseleave", clearTooltip);
    segment.addEventListener("blur", clearTooltip);
    startAngle = endAngle;
  });
}

function drawPieHover(group, config) {
  clearSvg(group);
  addSvg(group, "circle", {
    cx: config.x,
    cy: config.y,
    r: "4",
    fill: "#17202a",
    stroke: "#fff",
    "stroke-width": "2",
  });

  const textRows = [config.title, ...config.rows.map((row) => `${row.label}: ${row.value}`)];
  const tooltipWidth = Math.max(180, Math.min(300, Math.max(...textRows.map((text) => text.length)) * 8 + 30));
  const tooltipHeight = 30 + config.rows.length * 20;
  const preferredX = config.x + 14;
  const preferredY = config.y + 14;
  const x = clamp(
    preferredX + tooltipWidth > config.width - 8 ? config.x - tooltipWidth - 14 : preferredX,
    8,
    config.width - tooltipWidth - 8,
  );
  const y = clamp(
    preferredY + tooltipHeight > config.height - 8 ? config.y - tooltipHeight - 14 : preferredY,
    8,
    config.height - tooltipHeight - 8,
  );

  addSvg(group, "rect", {
    x,
    y,
    width: tooltipWidth,
    height: tooltipHeight,
    rx: "6",
    fill: colors.tooltipBg,
    stroke: colors.tooltipStroke,
    "stroke-width": "1",
  });
  addSvg(group, "text", {
    x: x + 12,
    y: y + 20,
    fill: "#17202a",
    "font-size": "12",
    "font-weight": "700",
  }).textContent = config.title;
  config.rows.forEach((row, index) => {
    addSvg(group, "circle", {
      cx: x + 12,
      cy: y + 40 + index * 20,
      r: "4",
      fill: row.color,
    });
    addSvg(group, "text", {
      x: x + 24,
      y: y + 44 + index * 20,
      fill: "#17202a",
      "font-size": "12",
    }).textContent = `${row.label}: ${row.value}`;
  });
}

function pieSlicePath(centerX, centerY, radius, startAngle, endAngle) {
  const start = polarPoint(centerX, centerY, radius, startAngle);
  const end = polarPoint(centerX, centerY, radius, endAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return [
    `M ${centerX.toFixed(2)} ${centerY.toFixed(2)}`,
    `L ${start.x.toFixed(2)} ${start.y.toFixed(2)}`,
    `A ${radius.toFixed(2)} ${radius.toFixed(2)} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`,
    "Z",
  ].join(" ");
}

function polarPoint(centerX, centerY, radius, angle) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: centerX + radius * Math.cos(radians),
    y: centerY + radius * Math.sin(radians),
  };
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

function drawLineChart(svg, points, series, options) {
  clearSvg(svg);
  const { width, height } = chartSize(svg, 720);
  const pad = chartPadding(width);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!points.length) {
    drawEmpty(svg, width, height, "尚無圖表資料");
    return;
  }

  const values = points.flatMap((point) => series.map((item) => Number(point[item.key] || 0)));
  const [minY, maxY] = extent(values);
  drawGrid(svg, width, height, pad, minY, maxY, options.yFormatter);

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

  drawXAxisLabels(svg, points, width, height, pad, options.xMode, (point) => point.date);
  addLineInteraction(svg, points, series, { width, height, pad, minY, maxY, xMode: options.xMode });
}

function drawBarChart(svg, rows, series, options) {
  clearSvg(svg);
  const { width, height } = chartSize(svg, 560);
  const pad = chartPadding(width);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!rows.length) {
    drawEmpty(svg, width, height, "尚無年度資料");
    return;
  }

  const values = rows.flatMap((row) => series.map((item) => Number(row[item.key] || 0)));
  const [minY, maxY] = extent(values.concat([0]));
  drawGrid(svg, width, height, pad, minY, maxY, options.yFormatter);
  const groupWidth = (width - pad.left - pad.right) / rows.length;
  const barWidth = Math.max(8, Math.min(34, groupWidth / (series.length + 1)));
  const zeroY = scale(0, minY, maxY, height - pad.bottom, pad.top);

  rows.forEach((row, index) => {
    const center = pad.left + groupWidth * index + groupWidth / 2;
    const startX = center - (series.length * barWidth + (series.length - 1) * 4) / 2;
    series.forEach((item, seriesIndex) => {
      const value = Number(row[item.key] || 0);
      const color = value < 0 && item.key !== "dividends" ? colors.negative : item.color;
      drawBar(svg, startX + seriesIndex * (barWidth + 4), value, barWidth, minY, maxY, zeroY, height, pad, color);
    });
  });

  drawXAxisLabels(svg, rows, width, height, pad, options.xMode === "auto" ? "year" : options.xMode, annualXValue);
  addBarInteraction(svg, rows, series, { width, height, pad, minY, maxY, xMode: options.xMode });
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

function drawGrid(svg, width, height, pad, minY, maxY, yFormatter) {
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
    }).textContent = yFormatter(value);
  }
}

function drawXAxisLabels(svg, rows, width, height, pad, mode, valueGetter) {
  const indexes = xLabelIndexes(rows.length, width);
  indexes.forEach((index) => {
    const x = scale(index, 0, Math.max(rows.length - 1, 1), pad.left, width - pad.right);
    const anchor = index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle";
    addSvg(svg, "text", {
      x,
      y: height - 18,
      "text-anchor": anchor,
      fill: colors.text,
      "font-size": "12",
    }).textContent = formatXAxisLabel(valueGetter(rows[index]), mode);
  });
}

function addLineInteraction(svg, points, series, chart) {
  const hoverGroup = addSvg(svg, "g", { "pointer-events": "none" });
  const overlay = addSvg(svg, "rect", {
    x: chart.pad.left,
    y: chart.pad.top,
    width: chart.width - chart.pad.left - chart.pad.right,
    height: chart.height - chart.pad.top - chart.pad.bottom,
    fill: "transparent",
    class: "chart-overlay",
  });

  overlay.addEventListener("mousemove", (event) => {
    const pointer = svgPointer(svg, event, chart.width, chart.height);
    const rawIndex = scale(pointer.x, chart.pad.left, chart.width - chart.pad.right, 0, Math.max(points.length - 1, 1));
    const index = clamp(Math.round(rawIndex), 0, points.length - 1);
    const point = points[index];
    const x = scale(index, 0, Math.max(points.length - 1, 1), chart.pad.left, chart.width - chart.pad.right);
    const rows = series.map((item) => ({
      label: item.label,
      color: item.color,
      value: item.formatter(Number(point[item.key] || 0)),
      raw: Number(point[item.key] || 0),
    }));
    drawHover(hoverGroup, {
      x,
      title: formatXAxisLabel(point.date, "full"),
      rows,
      chart,
      yForRow: (row) => scale(row.raw, chart.minY, chart.maxY, chart.height - chart.pad.bottom, chart.pad.top),
    });
  });
  overlay.addEventListener("mouseleave", () => clearSvg(hoverGroup));
}

function addBarInteraction(svg, rows, series, chart) {
  const hoverGroup = addSvg(svg, "g", { "pointer-events": "none" });
  const overlay = addSvg(svg, "rect", {
    x: chart.pad.left,
    y: chart.pad.top,
    width: chart.width - chart.pad.left - chart.pad.right,
    height: chart.height - chart.pad.top - chart.pad.bottom,
    fill: "transparent",
    class: "chart-overlay",
  });
  const groupWidth = (chart.width - chart.pad.left - chart.pad.right) / rows.length;

  overlay.addEventListener("mousemove", (event) => {
    const pointer = svgPointer(svg, event, chart.width, chart.height);
    const index = clamp(Math.floor((pointer.x - chart.pad.left) / groupWidth), 0, rows.length - 1);
    const row = rows[index];
    const center = chart.pad.left + groupWidth * index + groupWidth / 2;
    const tooltipRows = series.map((item) => ({
      label: item.label,
      color: item.color,
      value: item.formatter(Number(row[item.key] || 0)),
      raw: Number(row[item.key] || 0),
    }));
    drawHover(hoverGroup, {
      x: center,
      title: formatXAxisLabel(annualXValue(row), "full"),
      rows: tooltipRows,
      chart,
      yForRow: (item) => scale(item.raw, chart.minY, chart.maxY, chart.height - chart.pad.bottom, chart.pad.top),
    });
  });
  overlay.addEventListener("mouseleave", () => clearSvg(hoverGroup));
}

function drawHover(group, config) {
  clearSvg(group);
  addSvg(group, "line", {
    x1: config.x,
    x2: config.x,
    y1: config.chart.pad.top,
    y2: config.chart.height - config.chart.pad.bottom,
    stroke: "#94a3b8",
    "stroke-width": "1",
    "stroke-dasharray": "4 4",
  });
  config.rows.forEach((row) => {
    addSvg(group, "circle", {
      cx: config.x,
      cy: config.yForRow(row),
      r: "4",
      fill: row.color,
      stroke: "#fff",
      "stroke-width": "2",
    });
  });

  const textRows = [config.title, ...config.rows.map((row) => `${row.label}: ${row.value}`)];
  const tooltipWidth = Math.max(150, Math.min(260, Math.max(...textRows.map((text) => text.length)) * 7 + 28));
  const tooltipHeight = 24 + config.rows.length * 20;
  const preferredX = config.x + 14;
  const x = preferredX + tooltipWidth > config.chart.width - 8 ? config.x - tooltipWidth - 14 : preferredX;
  const y = config.chart.pad.top + 8;
  addSvg(group, "rect", {
    x,
    y,
    width: tooltipWidth,
    height: tooltipHeight,
    rx: "6",
    fill: colors.tooltipBg,
    stroke: colors.tooltipStroke,
    "stroke-width": "1",
  });
  addSvg(group, "text", {
    x: x + 12,
    y: y + 18,
    fill: "#17202a",
    "font-size": "12",
    "font-weight": "700",
  }).textContent = config.title;
  config.rows.forEach((row, index) => {
    addSvg(group, "circle", {
      cx: x + 12,
      cy: y + 38 + index * 20,
      r: "4",
      fill: row.color,
    });
    addSvg(group, "text", {
      x: x + 24,
      y: y + 42 + index * 20,
      fill: "#17202a",
      "font-size": "12",
    }).textContent = `${row.label}: ${row.value}`;
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

function inferCurrency(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  return normalized.endsWith(".TW") || normalized.endsWith(".TWO") ? "TWD" : "USD";
}

function scheduleChartRender() {
  clearTimeout(state.resizeTimer);
  state.resizeTimer = setTimeout(() => {
    renderPerformance();
    renderAllocation();
  }, 120);
}

function chartSize(svg, fallbackWidth) {
  const rect = svg.getBoundingClientRect();
  return {
    width: Math.max(320, Math.round(rect.width || fallbackWidth)),
    height: Math.max(260, Math.round(rect.height || 320)),
  };
}

function chartPadding(width) {
  return width < 520
    ? { top: 26, right: 18, bottom: 58, left: 72 }
    : { top: 28, right: 34, bottom: 62, left: 94 };
}

function xLabelIndexes(length, width) {
  if (length <= 1) {
    return [0];
  }
  if (width < 520) {
    return uniqueIndexes([0, length - 1]);
  }
  return uniqueIndexes([0, Math.floor((length - 1) / 2), length - 1]);
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

function svgPointer(svg, event, viewBoxWidth, viewBoxHeight) {
  const rect = svg.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * viewBoxWidth,
    y: ((event.clientY - rect.top) / rect.height) * viewBoxHeight,
  };
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
  const padding = (max - min) * 0.12;
  return [min - padding, max + padding];
}

function scale(value, domainMin, domainMax, rangeMin, rangeMax) {
  if (domainMax === domainMin) {
    return (rangeMin + rangeMax) / 2;
  }
  return rangeMin + ((value - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function uniqueIndexes(indexes) {
  return [...new Set(indexes.filter((index) => index >= 0))];
}

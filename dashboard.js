const CHART_COLORS = {
  finance: '#0071e3',
  economics: '#248a3d',
  psychology: '#8a4baf',
  green: '#248a3d',
  amber: '#c76c00',
  red: '#d70015',
};

const THEME_CHART_COLORS = {
  light: { grid: '#e8e8ed', tick: '#6e6e73', doughnutBorder: '#ffffff' },
  dark: { grid: '#38383a', tick: '#98989d', doughnutBorder: '#1c1c1e' },
};

function getCurrentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function chartDefaults() {
  const c = THEME_CHART_COLORS[getCurrentTheme()];
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { grid: { display: false }, ticks: { color: c.tick, font: { size: 11 } } },
      y: { grid: { color: c.grid }, ticks: { color: c.tick, font: { size: 11 } }, border: { display: false } },
    },
  };
}

// For horizontal bars (indexAxis:'y'), Chart.js keeps the scale keys 'x'/'y'
// but swaps their role: 'x' becomes the value axis, 'y' the category axis —
// so grid visibility needs to be the mirror image of chartDefaults().
function horizontalBarDefaults() {
  const c = THEME_CHART_COLORS[getCurrentTheme()];
  return {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { grid: { color: c.grid }, ticks: { color: c.tick, font: { size: 11 } }, border: { display: false } },
      y: { grid: { display: false }, ticks: { color: c.tick, font: { size: 11 } } },
    },
    plugins: { legend: { display: false } },
  };
}

function signColors(values) {
  return values.map((v) => ((v || 0) >= 0 ? CHART_COLORS.green : CHART_COLORS.red));
}

// Chart.js sizes a canvas at creation time, so charts inside a panel that
// starts hidden (display:none) render at 0x0 until resized after becoming
// visible — track instances per panel so showTab() can fix that up.
const PANEL_CHARTS = { finance: [], economics: [], psychology: [], strategy: [] };
const ALL_CHARTS = [];

function trackChart(panel, chart) {
  PANEL_CHARTS[panel].push(chart);
  ALL_CHARTS.push(chart);
  return chart;
}

function showTab(name, tabEl) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach((p) => p.classList.remove('active'));
  tabEl.classList.add('active');
  document.querySelector(`.panel[data-panel="${name}"]`).classList.add('active');
  PANEL_CHARTS[name].forEach((chart) => chart.resize());
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);

  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀' : '◐';

  const c = THEME_CHART_COLORS[theme];
  ALL_CHARTS.forEach((chart) => {
    if (chart.options.scales && chart.options.scales.x) {
      chart.options.scales.x.grid.color = c.grid;
      chart.options.scales.x.ticks.color = c.tick;
      chart.options.scales.y.grid.color = c.grid;
      chart.options.scales.y.ticks.color = c.tick;
    }
    if (chart.options.plugins && chart.options.plugins.legend && chart.options.plugins.legend.labels) {
      chart.options.plugins.legend.labels.color = c.tick;
    }
    if (chart.config.type === 'doughnut') {
      chart.data.datasets[0].borderColor = c.doughnutBorder;
    }
    chart.update();
  });
}

function toggleTheme() {
  applyTheme(getCurrentTheme() === 'dark' ? 'light' : 'dark');
}

// The inline head script already set data-theme before paint; just sync the icon.
document.getElementById('themeToggle').textContent = getCurrentTheme() === 'dark' ? '☀' : '◐';

function regimeBadgeClass(regime) {
  const r = (regime || '').toLowerCase();
  if (r.includes('risk-on')) return 'risk-on';
  if (r.includes('risk-off')) return 'risk-off';
  return 'neutral';
}

function scoreBadgeClass(score) {
  if (score > 0.15) return 'risk-on';
  if (score < -0.15) return 'risk-off';
  return 'neutral';
}

function pillarSignalHTML(label, score, title) {
  if (score === undefined || score === null) return '';
  const titleAttr = title ? ` title="${title}"` : '';
  return `<span class="sbadge ${scoreBadgeClass(score)}"${titleAttr}>${label} ${score >= 0 ? '+' : ''}${score.toFixed(2)}</span>`;
}

function tiltBadgeClass(tilt) {
  if (tilt === 'Overweight') return 'risk-on';
  if (tilt === 'Underweight') return 'risk-off';
  return 'neutral';
}

function cycleStageBadgeClass(stage) {
  if (stage === 'Expansion') return 'risk-on';
  if (stage === 'Contraction') return 'risk-off';
  return 'neutral'; // Late-Cycle or Unknown
}

function renderCycleStage(cycleStage) {
  const listEl = document.getElementById('cycleStageList');
  if (!cycleStage) {
    listEl.innerHTML = '';
    return;
  }
  listEl.innerHTML = `<div class="tilt-item">
    <div class="tilt-item-header">
      <span class="tilt-item-name">Cycle Stage</span>
      <span class="sbadge ${cycleStageBadgeClass(cycleStage.stage)}">${cycleStage.stage}</span>
    </div>
    <p class="tilt-rationale">${cycleStage.rationale}</p>
  </div>`;
}

function tiltItemHTML(name, data) {
  return `<div class="tilt-item">
    <div class="tilt-item-header">
      <span class="tilt-item-name">${name}</span>
      <span class="sbadge ${tiltBadgeClass(data.tilt)}">${data.tilt}</span>
    </div>
    <p class="tilt-rationale">${data.rationale}</p>
  </div>`;
}

function renderAllocationTilts(tilts) {
  const disclaimerEl = document.getElementById('tiltDisclaimer');
  const assetListEl = document.getElementById('assetTiltList');
  const sectorListEl = document.getElementById('sectorTiltList');

  if (!tilts) {
    disclaimerEl.textContent = '';
    assetListEl.innerHTML = '';
    sectorListEl.innerHTML = '';
    return;
  }

  disclaimerEl.textContent = tilts.disclaimer;
  assetListEl.innerHTML = Object.entries(tilts.asset_classes || {})
    .map(([name, data]) => tiltItemHTML(name, data)).join('');
  sectorListEl.innerHTML = Object.entries(tilts.sectors || {})
    .map(([name, data]) => tiltItemHTML(name, data)).join('');
}

function strategyItemHTML(strategy) {
  return `<div class="tilt-item">
    <div class="tilt-item-header">
      <span class="tilt-item-name">${strategy.name}</span>
      <span class="sbadge ${strategy.indicated ? 'risk-on' : 'neutral'}">${strategy.indicated ? 'Indicated now' : 'Not indicated now'}</span>
    </div>
    <p class="tilt-rationale">${strategy.rationale}</p>
  </div>`;
}

function renderStrategies(strategies) {
  const listEl = document.getElementById('strategyList');
  listEl.innerHTML = (strategies || []).map(strategyItemHTML).join('');
}

// Each metric's "improving" direction, used to color the day-over-day
// diff chips consistently with how the same metric feeds the composite
// score (e.g. a rising VIX is colored as unfavorable, a rising PMI as
// favorable) — not asserting good/bad in general, just reusing the same
// direction already baked into compute_composite() on the backend.
const DIFF_METRICS = [
  { key: 'composite_score', label: 'Composite', decimals: 2, threshold: 0.05, higherIsBetter: true },
  { key: 'vix', label: 'VIX', decimals: 2, threshold: 1.5, higherIsBetter: false },
  { key: 'put_call_ratio', label: 'Put/Call', decimals: 2, threshold: 0.1, higherIsBetter: false },
  { key: 'sp500_pe', label: 'S&P 500 P/E', decimals: 1, threshold: 0.5, higherIsBetter: false },
  { key: 'ism_pmi', label: 'ISM PMI', decimals: 1, threshold: 0.5, higherIsBetter: true },
];

function computeDiffs(entries) {
  if (!entries || entries.length < 2) return [];
  const prev = entries[entries.length - 2];
  const curr = entries[entries.length - 1];

  const diffs = [];
  for (const m of DIFF_METRICS) {
    const prevVal = prev[m.key];
    const currVal = curr[m.key];
    if (prevVal === undefined || prevVal === null || currVal === undefined || currVal === null) continue;

    const delta = currVal - prevVal;
    if (Math.abs(delta) < m.threshold) continue;

    const improved = m.higherIsBetter ? delta > 0 : delta < 0;
    diffs.push({
      label: m.label,
      text: `${m.label} ${prevVal.toFixed(m.decimals)} → ${currVal.toFixed(m.decimals)}`,
      className: improved ? 'risk-on' : 'risk-off',
    });
  }
  return diffs;
}

function renderDiffs(entries) {
  const label = document.getElementById('diffLabel');
  const row = document.getElementById('diffRow');
  const diffs = computeDiffs(entries);

  if (!entries || entries.length < 2) {
    label.style.display = 'none';
    row.innerHTML = '';
    return;
  }

  label.style.display = '';
  if (diffs.length === 0) {
    row.innerHTML = '<span class="sbadge neutral">No material changes since yesterday</span>';
  } else {
    row.innerHTML = diffs.map((d) => `<span class="sbadge ${d.className}">${d.text}</span>`).join('');
  }
}

async function loadSnapshot() {
  // cache: 'no-store' + a cache-busting param so a stale CDN/browser cache
  // never masks a real update between polls.
  const res = await fetch(`data/snapshot.json?t=${Date.now()}`, { cache: 'no-store' });
  return res.json();
}

async function loadHistory() {
  try {
    const res = await fetch(`data/history.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return { entries: [] };
    return res.json();
  } catch {
    return { entries: [] };
  }
}

function renderTrend(entries) {
  const wrap = document.getElementById('trendChartWrap');
  const label = document.getElementById('trendLabel');

  if (!entries || entries.length < 2) {
    wrap.style.display = 'none';
    label.textContent = 'Trend builds up daily as the pipeline runs — check back tomorrow for a real read.';
    return;
  }

  wrap.style.display = '';
  label.textContent = `Composite score, last ${entries.length} days`;

  const trendOptions = chartDefaults();
  trendOptions.scales.x.display = false;
  trendOptions.scales.y.display = false;
  trendOptions.plugins = { legend: { display: false } };
  trendOptions.elements = { point: { radius: 0 }, line: { tension: 0.3 } };

  ALL_CHARTS.push(new Chart(document.getElementById('trendChart'), {
    type: 'line',
    data: {
      labels: entries.map((e) => e.date),
      datasets: [{
        data: entries.map((e) => e.composite_score),
        borderColor: CHART_COLORS.finance,
        backgroundColor: 'rgba(0, 113, 227, 0.12)',
        borderWidth: 2,
        fill: true,
      }],
    },
    options: trendOptions,
  }));
}

// Generic mini sparkline for a single history.json field, scoped to a tab
// panel (so its chart gets resized correctly when that panel becomes
// visible — see the PANEL_CHARTS comment above). Hides itself entirely
// when there isn't enough history yet, rather than showing a redundant
// "check back tomorrow" message (the main banner already covers that).
function renderMiniTrend(panel, labelId, wrapId, canvasId, entries, field, labelText, borderColor, fillColor) {
  const labelEl = document.getElementById(labelId);
  const wrap = document.getElementById(wrapId);

  if (!entries || entries.length < 2) {
    labelEl.style.display = 'none';
    wrap.style.display = 'none';
    return;
  }

  labelEl.style.display = '';
  wrap.style.display = '';
  labelEl.textContent = `${labelText}, last ${entries.length} days`;

  const opts = chartDefaults();
  opts.scales.x.display = false;
  opts.scales.y.display = false;
  opts.plugins = { legend: { display: false } };
  opts.elements = { point: { radius: 0 }, line: { tension: 0.3 } };

  trackChart(panel, new Chart(document.getElementById(canvasId), {
    type: 'line',
    data: {
      labels: entries.map((e) => e.date),
      datasets: [{
        data: entries.map((e) => e[field]),
        borderColor,
        backgroundColor: fillColor,
        borderWidth: 2,
        fill: true,
      }],
    },
    options: opts,
  }));
}

function renderRealRateChart(economics) {
  const fedFunds = economics.fed_funds_rate;
  const cpi = economics.cpi_yoy;
  if (fedFunds === undefined || fedFunds === null || cpi === undefined || cpi === null) return;

  const opts = horizontalBarDefaults();
  opts.plugins.tooltip = { callbacks: { label: (ctx) => `${ctx.parsed.x}%` } };

  trackChart('economics', new Chart(document.getElementById('realRateChart'), {
    type: 'bar',
    data: {
      labels: ['Fed Funds Rate', 'CPI YoY'],
      datasets: [{
        data: [fedFunds, cpi],
        backgroundColor: [CHART_COLORS.finance, CHART_COLORS.amber],
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 32,
      }],
    },
    options: opts,
  }));
}

function destroyAllCharts() {
  ALL_CHARTS.forEach((chart) => chart.destroy());
  ALL_CHARTS.length = 0;
  PANEL_CHARTS.finance.length = 0;
  PANEL_CHARTS.economics.length = 0;
  PANEL_CHARTS.psychology.length = 0;
  PANEL_CHARTS.strategy.length = 0;
}

let isFirstLoad = true;
const MIN_LOADING_DISPLAY_MS = 550; // long enough to read as deliberate, short enough not to annoy

function hideLoadingOverlay() {
  const overlay = document.getElementById('loadingOverlay');
  if (!overlay) return;
  overlay.classList.add('hidden');
  overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
}

async function refreshDashboard() {
  const loadStartedAt = Date.now();
  const [snapshot, history] = await Promise.all([loadSnapshot(), loadHistory()]);
  destroyAllCharts();
  const pillarScores = (snapshot.composite && snapshot.composite.pillar_scores) || {};
  renderComposite(snapshot.composite, snapshot.meta.last_updated);
  renderDiffs(history.entries);
  renderTrend(history.entries);
  renderFinance(snapshot.finance, pillarScores.finance);
  renderAllocationTilts(snapshot.allocation_tilts);
  renderEconomics(snapshot.economics, pillarScores.economics, history.entries, snapshot.cycle_stage);
  renderPsychology(snapshot.psychology, pillarScores.psychology, history.entries);
  renderStrategies(snapshot.strategies);
  // Re-render always rebuilds the active panel's chart at full size; other
  // panels' charts get fixed up on next tab switch same as on first load.
  const activeTab = document.querySelector('.tab.active');
  if (activeTab) PANEL_CHARTS[activeTab.dataset.tab].forEach((chart) => chart.resize());

  // Only the very first load shows the overlay — background auto-refreshes
  // every 5 minutes shouldn't re-flash a loading screen over live data.
  if (isFirstLoad) {
    isFirstLoad = false;
    const remaining = MIN_LOADING_DISPLAY_MS - (Date.now() - loadStartedAt);
    setTimeout(hideLoadingOverlay, Math.max(0, remaining));
  }
}

function metricHTML(value, label, suffix = '') {
  const display = (value === null || value === undefined) ? '—' : `${value}${suffix}`;
  return `<div class="metric">
    <div class="metric-value">${display}</div>
    <div class="metric-label">${label}</div>
  </div>`;
}

function renderComposite(composite, lastUpdated) {
  document.getElementById('compositeRegime').textContent = composite.regime;

  const narrativeEl = document.getElementById('compositeNarrative');
  const paragraphs = Array.isArray(composite.narrative) ? composite.narrative : [composite.narrative];
  narrativeEl.innerHTML = paragraphs.map((p) => `<p>${p}</p>`).join('');

  const badge = document.getElementById('compositeBadge');
  badge.textContent = composite.regime;
  badge.className = `sbadge ${regimeBadgeClass(composite.regime)}`;

  const [min, max] = composite.score_range;
  const pct = ((composite.score - min) / (max - min)) * 100;
  document.getElementById('scoreMarker').style.left = `${pct}%`;

  const pillarScores = composite.pillar_scores || {};
  document.getElementById('pillarScoreRow').innerHTML =
    pillarSignalHTML('Finance', pillarScores.finance, 'Yield curve, valuation vs. history, and sector breadth, averaged (-1 to +1)') +
    pillarSignalHTML('Economics', pillarScores.economics, 'ISM PMI, real policy rate, and unemployment vs. full employment, averaged (-1 to +1)') +
    pillarSignalHTML('Psychology', pillarScores.psychology, 'VIX, put/call ratio, and AAII spread, standardized and averaged (-1 to +1)');

  // Fundamentals-only baseline vs. the full psychology-adjusted composite —
  // per the theoretical framework, that gap is the headline insight, not
  // any single pillar score, so it gets its own row rather than being
  // buried only in the narrative prose.
  document.getElementById('gapRow').innerHTML =
    pillarSignalHTML('Fundamentals baseline', composite.baseline_score, 'What Finance + Economics alone would suggest, with no psychology overlay') +
    pillarSignalHTML('Psychology gap', composite.psychology_gap, 'How far current psychology is pulling the read from that fundamentals baseline');

  document.getElementById('lastUpdated').textContent =
    `Last updated: ${new Date(lastUpdated).toLocaleString()}`;
}

function renderFinance(finance, score) {
  document.getElementById('financeSignal').innerHTML = pillarSignalHTML('Signal', score, 'This pillar\'s -1 to +1 score, feeding into the composite regime read');

  const metrics = document.getElementById('financeKeyMetrics');
  metrics.innerHTML =
    metricHTML(finance.sp500_pe, 'S&P 500 P/E') +
    metricHTML(finance.yield_curve_10y_2y, '10y-2y Spread', '%');

  const sectorValues = Object.values(finance.sector_returns_1m);
  trackChart('finance', new Chart(document.getElementById('sectorChart'), {
    type: 'bar',
    data: {
      labels: Object.keys(finance.sector_returns_1m),
      datasets: [{
        label: '1M Sector Return (%)',
        data: sectorValues,
        backgroundColor: signColors(sectorValues),
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 28,
      }],
    },
    options: horizontalBarDefaults(),
  }));

  const assetValues = Object.values(finance.asset_class_returns_1m);
  trackChart('finance', new Chart(document.getElementById('assetClassChart'), {
    type: 'bar',
    data: {
      labels: Object.keys(finance.asset_class_returns_1m),
      datasets: [{
        label: '1M Asset Class Return (%)',
        data: assetValues,
        backgroundColor: signColors(assetValues),
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 28,
      }],
    },
    options: horizontalBarDefaults(),
  }));
}

function renderEconomics(economics, score, historyEntries, cycleStage) {
  document.getElementById('economicsSignal').innerHTML = pillarSignalHTML('Signal', score, 'This pillar\'s -1 to +1 score, feeding into the composite regime read');

  const metrics = document.getElementById('economicsKeyMetrics');
  metrics.innerHTML =
    metricHTML(economics.cpi_yoy, 'CPI YoY', '%') +
    metricHTML(economics.ism_pmi, 'ISM PMI') +
    metricHTML(economics.unemployment_rate, 'Unemployment', '%') +
    metricHTML(economics.fed_funds_rate, 'Fed Funds Rate', '%');

  renderCycleStage(cycleStage);

  renderMiniTrend(
    'economics', 'pmiTrendLabel', 'pmiTrendWrap', 'pmiTrendChart',
    historyEntries, 'ism_pmi', 'ISM PMI', CHART_COLORS.economics, 'rgba(36, 138, 61, 0.12)',
  );
  renderRealRateChart(economics);
}

function renderPsychology(psychology, score, historyEntries) {
  document.getElementById('psychologySignal').innerHTML = pillarSignalHTML('Fear/Greed', score, 'This pillar\'s -1 (fear) to +1 (greed) score, feeding into the composite regime read');

  const metrics = document.getElementById('psychologyKeyMetrics');
  metrics.innerHTML =
    metricHTML(psychology.vix, 'VIX') +
    metricHTML(psychology.put_call_ratio, 'Put/Call Ratio');

  const gaugeMarker = document.getElementById('psychGaugeMarker');
  if (score !== undefined && score !== null) {
    gaugeMarker.style.left = `${((score - -1) / 2) * 100}%`;
  }

  renderMiniTrend(
    'psychology', 'vixTrendLabel', 'vixTrendWrap', 'vixTrendChart',
    historyEntries, 'vix', 'VIX', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  const aaii = psychology.aaii_sentiment || {};
  trackChart('psychology', new Chart(document.getElementById('sentimentChart'), {
    type: 'doughnut',
    data: {
      labels: ['Bullish', 'Neutral', 'Bearish'],
      datasets: [{
        data: [aaii.bullish, aaii.neutral, aaii.bearish],
        backgroundColor: [CHART_COLORS.green, CHART_COLORS.amber, CHART_COLORS.red],
        borderColor: THEME_CHART_COLORS[getCurrentTheme()].doughnutBorder,
        borderWidth: 2,
        borderRadius: 6,
        spacing: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: THEME_CHART_COLORS[getCurrentTheme()].tick,
            font: { size: 11 },
            padding: 14,
            boxWidth: 8,
            usePointStyle: true,
            pointStyle: 'circle',
          },
        },
      },
    },
  }));
}

const AUTO_REFRESH_MS = 5 * 60 * 1000;

refreshDashboard();
setInterval(refreshDashboard, AUTO_REFRESH_MS);

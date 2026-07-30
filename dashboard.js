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
const PANEL_CHARTS = { finance: [], economics: [], psychology: [], strategy: [], backtesting: [] };
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

function regimeLineColor(regime) {
  if (regime === 'Risk-On') return CHART_COLORS.green;
  if (regime === 'Risk-Off') return CHART_COLORS.red;
  if (regime === 'Neutral') return CHART_COLORS.amber;
  return CHART_COLORS.finance; // warm-up months before the psychology pillar has enough history
}

function renderRegimeChart(monthlySeries) {
  const labels = monthlySeries.map((m) => m.date);
  const spyValues = monthlySeries.map((m) => m.spy_growth);
  const regimes = monthlySeries.map((m) => m.regime);

  const opts = chartDefaults();
  opts.scales.x.ticks.maxTicksLimit = 9;
  opts.plugins = {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx) => `SPY: ${ctx.parsed.y.toFixed(1)} (${regimes[ctx.dataIndex] || 'warm-up period'})`,
      },
    },
  };
  opts.elements = { point: { radius: 0 } };

  trackChart('backtesting', new Chart(document.getElementById('regimeChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: spyValues,
        borderWidth: 2,
        fill: false,
        segment: { borderColor: (ctx) => regimeLineColor(regimes[ctx.p1DataIndex]) },
      }],
    },
    options: opts,
  }));
}

function renderDecileChart(gapDeciles) {
  const labels = gapDeciles.map((d) => `D${d.decile}`);
  const c = THEME_CHART_COLORS[getCurrentTheme()];
  const opts = chartDefaults();
  opts.plugins = { legend: { display: true, position: 'top', labels: { color: c.tick, font: { size: 11 }, boxWidth: 10 } } };

  trackChart('backtesting', new Chart(document.getElementById('decileChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '1M fwd. return %', data: gapDeciles.map((d) => d.fwd_1m), backgroundColor: CHART_COLORS.finance, borderRadius: 4 },
        { label: '3M fwd. return %', data: gapDeciles.map((d) => d.fwd_3m), backgroundColor: CHART_COLORS.economics, borderRadius: 4 },
        { label: '6M fwd. return %', data: gapDeciles.map((d) => d.fwd_6m), backgroundColor: CHART_COLORS.psychology, borderRadius: 4 },
      ],
    },
    options: opts,
  }));
}

function significanceBadge(pvalue) {
  if (pvalue < 0.05) return '<span class="sbadge risk-on">p &lt; 0.05</span>';
  if (pvalue < 0.10) return '<span class="sbadge neutral">p &lt; 0.10</span>';
  return '<span class="sbadge risk-off">not significant</span>';
}

const HORIZON_LABELS = { fwd_1m: '1 month', fwd_3m: '3 months', fwd_6m: '6 months' };
const REGRESSION_SIGNAL_LABELS = {
  gap_vs_forward_return: 'Fundamentals-psychology gap',
  adaptive_composite_vs_forward_return: 'Adaptive composite (15-55%)',
  fixed_composite_vs_forward_return: 'Fixed composite (35%)',
};

function renderRegressionTable(regressions) {
  let rows = '';
  for (const [horizon, signals] of Object.entries(regressions)) {
    for (const [signalKey, stats] of Object.entries(signals)) {
      rows += `<tr>
        <td>${HORIZON_LABELS[horizon] || horizon}</td>
        <td>${REGRESSION_SIGNAL_LABELS[signalKey] || signalKey}</td>
        <td>${stats.beta}</td>
        <td>${stats.beta_tstat}</td>
        <td>${stats.beta_pvalue}</td>
        <td>${stats.r_squared}</td>
        <td>${significanceBadge(stats.beta_pvalue)}</td>
      </tr>`;
    }
  }
  document.getElementById('regressionTable').innerHTML =
    '<thead><tr><th>Horizon</th><th>Signal</th><th>&beta;</th><th>t-stat</th><th>p-value</th><th>R&sup2;</th><th>Result</th></tr></thead>' +
    `<tbody>${rows}</tbody>`;
}

function computeVerdict(regressions) {
  let minP = 1;
  for (const signals of Object.values(regressions)) {
    for (const stats of Object.values(signals)) {
      if (stats.beta_pvalue < minP) minP = stats.beta_pvalue;
    }
  }
  if (minP < 0.05) return { text: `Significant result found (min p = ${minP.toFixed(3)})`, className: 'risk-on' };
  if (minP < 0.10) return { text: `Borderline signal only (min p = ${minP.toFixed(3)}, not p<0.05)`, className: 'neutral' };
  return { text: `No significant predictive edge found (min p = ${minP.toFixed(3)})`, className: 'risk-off' };
}

const BACKTEST_CAVEATS = [
  'ISM PMI has no free historical source anywhere — the Economics pillar runs on only 2 of its usual 3 components for the entire backtest, and the VIX cycle-stage adjustment never activates historically (it requires PMI to classify the cycle stage).',
  'HY OAS\'s free FRED history only starts 2023-07-28 — excluded from the reconstruction before that date.',
  'Cboe\'s downloadable put/call archives stop at 2019-10-04 — despite the live daily scraper working fine today, no free bulk file bridges 2019-2026, so put/call is excluded from that stretch.',
  'The window is ~27 years (1999-2026), not the full 30 years initially targeted — bounded by the 5 sector ETFs\' 1998-12-22 inception.',
  'Monthly/weekly series (CPI, unemployment, fed funds, consumer sentiment, AAII, NAAIM, S&P 500 P/E) are forward-filled with an assumed publication lag, not each series\' actual historical release calendar.',
  'CPI and unemployment use today\'s revised FRED values throughout history, not the real-time-as-then vintages that would actually have been known on each date.',
  'Extreme-decile results are dominated by a handful of crisis episodes (2008, 2020, etc.), not many independent events — daily observations are highly serially correlated, which is why Newey-West errors were used for the regressions above.',
];

function renderBacktesting(data) {
  const verdict = computeVerdict(data.regressions);
  document.getElementById('backtestVerdict').innerHTML =
    `<span class="sbadge ${verdict.className}">${verdict.text}</span>`;

  const [startYear] = data.meta.start_date.split('-');
  const [endYear] = data.meta.end_date.split('-');
  let significantCount = 0, totalCount = 0;
  for (const signals of Object.values(data.regressions)) {
    for (const stats of Object.values(signals)) {
      totalCount += 1;
      if (stats.beta_pvalue < 0.05) significantCount += 1;
    }
  }
  document.getElementById('backtestKeyMetrics').innerHTML =
    metricHTML(`${startYear}–${endYear}`, 'Sample Period', '', 'The full window this backtest reconstructs the composite over, bounded by the earliest date every required input has real data (the five sector ETFs, inception 1998-12-22, are the binding constraint). A longer, more diverse sample gives more confidence that any pattern found isn\'t just an artifact of one market regime — take findings from a short or single-regime sample with real caution.') +
    metricHTML(data.meta.n_trading_days.toLocaleString(), 'Trading Days', '', 'Total daily observations behind every stat on this page. A large count sounds reassuring, but daily observations are highly serially correlated — the effective number of independent "events" (distinct market episodes) is much smaller, which is exactly why Newey-West errors are used for the regressions rather than treating each day as fully independent evidence.') +
    metricHTML(`${significantCount} / ${totalCount}`, 'Significant Results (p<0.05)', '', 'How many of the 9 regressions (3 signals × 3 horizons) cleared the conventional p < 0.05 significance bar. A low count is the headline finding of this whole study: it means you shouldn\'t currently size real positions off this composite\'s gap reading alone — treat it as one input among many, not a standalone timing signal.') +
    metricHTML(`${data.regime_disagreement.pct}%`, 'Adaptive vs. Fixed Disagreement', '', 'Share of trading days the adaptive-weight (15-55%) and fixed-35%-weight composites would have called a different regime (Risk-On/Neutral/Risk-Off). A high disagreement rate with no accompanying edge in the regression table (see above) means the adaptive-weighting mechanism changes the read fairly often without demonstrably improving it in this sample — worth knowing before leaning on the adaptive weight as if it were proven to add value.');

  renderRegimeChart(data.monthly_series);
  renderDecileChart(data.gap_deciles);
  renderRegressionTable(data.regressions);

  document.getElementById('disagreementNote').textContent =
    `Across this ~${endYear - startYear}-year backtest, the adaptive and fixed-weight composites called a different regime on ${data.regime_disagreement.pct}% of trading days ` +
    `(${data.regime_disagreement.days.toLocaleString()} of ${data.regime_disagreement.total_days.toLocaleString()}). Neither showed a statistically significant return edge over the ` +
    'other at any horizon in this sample — see the regression table above.';

  document.getElementById('caveatsList').innerHTML =
    BACKTEST_CAVEATS.map((c) => `<li>${c}</li>`).join('');
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
  { key: 'consumer_sentiment', label: 'Consumer Sentiment', decimals: 1, threshold: 1.0, higherIsBetter: true },
  { key: 'hy_oas', label: 'HY Credit Spread', decimals: 2, threshold: 0.1, higherIsBetter: false },
  { key: 'news_sentiment', label: 'News Sentiment', decimals: 2, threshold: 0.03, higherIsBetter: true },
  { key: 'naaim_exposure', label: 'NAAIM Exposure', decimals: 1, threshold: 5.0, higherIsBetter: true },
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
      prevVal, currVal, delta,
      text: `${m.label} ${prevVal.toFixed(m.decimals)} → ${currVal.toFixed(m.decimals)}`,
      className: improved ? 'risk-on' : 'risk-off',
    });
  }
  return diffs;
}

// Auto-generated "what changed since yesterday" sentence (Will's memo item
// 5) — descriptive (rose/fell), not evaluative, since "improved/worsened"
// framing is already carried separately by the chip colors below.
function diffNarrativeText(diffs) {
  if (diffs.length === 0) {
    return 'No metric moved enough since yesterday to flag — conditions look essentially unchanged.';
  }
  const clauses = diffs.map((d) => {
    const direction = d.delta > 0 ? 'rose' : 'fell';
    return `${d.label} ${direction} from ${d.prevVal.toFixed(2)} to ${d.currVal.toFixed(2)}`;
  });
  const joined = clauses.length === 1
    ? clauses[0]
    : `${clauses.slice(0, -1).join(', ')}, and ${clauses[clauses.length - 1]}`;
  return `Since yesterday: ${joined}.`;
}

function renderDiffs(entries) {
  const label = document.getElementById('diffLabel');
  const row = document.getElementById('diffRow');
  const narrativeEl = document.getElementById('diffNarrative');
  const diffs = computeDiffs(entries);

  if (!entries || entries.length < 2) {
    label.style.display = 'none';
    row.innerHTML = '';
    narrativeEl.textContent = '';
    return;
  }

  label.style.display = '';
  narrativeEl.textContent = diffNarrativeText(diffs);
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

// Static research output (regenerated by scripts/backtest.py, not the daily
// live pipeline) — fetched once and cached, unlike snapshot/history which
// poll every 5 minutes for genuinely live data.
let cachedBacktestData = null;
async function loadBacktest() {
  if (cachedBacktestData) return cachedBacktestData;
  try {
    const res = await fetch('data/backtest_frontend.json', { cache: 'no-store' });
    if (!res.ok) return null;
    cachedBacktestData = await res.json();
    return cachedBacktestData;
  } catch {
    return null;
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
// when there isn't enough history *for this specific field* yet, rather
// than showing a redundant "check back tomorrow" message (the main banner
// already covers that) — a newly-added field only has today's entry
// populated, so gating on entries.length alone would draw a near-empty
// line (a single trailing point with undefined everywhere else).
function renderMiniTrend(panel, labelId, wrapId, canvasId, entries, field, labelText, borderColor, fillColor) {
  const labelEl = document.getElementById(labelId);
  const wrap = document.getElementById(wrapId);
  const points = (entries || []).filter((e) => e[field] !== undefined && e[field] !== null);

  if (points.length < 2) {
    labelEl.style.display = 'none';
    wrap.style.display = 'none';
    return;
  }

  labelEl.style.display = '';
  wrap.style.display = '';
  labelEl.textContent = `${labelText}, last ${points.length} days`;

  const opts = chartDefaults();
  opts.scales.x.display = false;
  opts.scales.y.display = false;
  opts.plugins = { legend: { display: false } };
  opts.elements = { point: { radius: 0 }, line: { tension: 0.3 } };

  trackChart(panel, new Chart(document.getElementById(canvasId), {
    type: 'line',
    data: {
      labels: points.map((e) => e.date),
      datasets: [{
        data: points.map((e) => e[field]),
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
  PANEL_CHARTS.backtesting.length = 0;
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
  const [snapshot, history, backtest] = await Promise.all([loadSnapshot(), loadHistory(), loadBacktest()]);
  destroyAllCharts();
  const pillarScores = (snapshot.composite && snapshot.composite.pillar_scores) || {};
  renderComposite(snapshot.composite, snapshot.meta.last_updated);
  renderHistoricalAnalogues(snapshot.historical_analogues, pillarScores);
  renderDiffs(history.entries);
  renderTrend(history.entries);
  renderFinance(snapshot.finance, pillarScores.finance, history.entries);
  renderAllocationTilts(snapshot.allocation_tilts);
  renderEconomics(snapshot.economics, pillarScores.economics, history.entries, snapshot.cycle_stage);
  renderPsychology(snapshot.psychology, pillarScores.psychology, history.entries);
  renderStrategies(snapshot.strategies);
  if (backtest) renderBacktesting(backtest);
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

// Manual "Refresh" button: forces an immediate re-fetch of whatever's
// currently published (same mechanism as the 5-minute auto-refresh, just
// on demand) — this re-checks for the latest published data, it does not
// trigger a brand-new scrape/fetch run on GitHub's side.
async function handleRefreshClick() {
  const btn = document.getElementById('refreshBtn');
  const label = btn.querySelector('.refresh-label');
  if (btn.disabled) return;

  const previousUpdatedAt = document.getElementById('lastUpdated').textContent;
  btn.disabled = true;
  btn.classList.add('spinning');
  label.textContent = 'Refreshing…';

  try {
    await refreshDashboard();
    const newUpdatedAt = document.getElementById('lastUpdated').textContent;
    label.textContent = newUpdatedAt === previousUpdatedAt ? 'Up to date' : 'Updated';
  } catch (err) {
    console.error('Manual refresh failed:', err);
    label.textContent = 'Failed — retry';
  } finally {
    btn.classList.remove('spinning');
    setTimeout(() => {
      label.textContent = 'Refresh';
      btn.disabled = false;
    }, 1800);
  }
}

// `explain` is the "explain this signal" tooltip layer (Will's memo item
// 5, gated on item 2's teaching-audience decision) — a native title
// attribute rather than a custom widget, so it stays keyboard/AT-neutral
// and needs no new dependency.
// `explain` is the full "what this means, and what it implies for
// positioning" writeup — a clean dropdown per metric (native
// details/summary, same progressive-disclosure pattern as the composite
// banner's "Full breakdown" toggle), not just a hover tooltip.
function metricHTML(value, label, suffix = '', explain = '') {
  const display = (value === null || value === undefined) ? '—' : `${value}${suffix}`;
  const explainBlock = explain
    ? `<details class="metric-explain"><summary>What this means</summary><p>${explain}</p></details>`
    : '';
  return `<div class="metric">
    <div class="metric-value">${display}</div>
    <div class="metric-label">${label}</div>
    ${explainBlock}
  </div>`;
}

// Same dropdown pattern for a chart/visual that isn't backed by a single
// metric tile (sector returns, asset returns, AAII donut, Fear/Greed gauge).
function chartExplainHTML(explain) {
  return `<details class="metric-explain chart-explain"><summary>What this means</summary><p>${explain}</p></details>`;
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

  // Hero number, per Will's memo item 5: lead with the gap and current
  // posture, large, first on screen — everything else is progressive
  // disclosure below.
  const gap = composite.psychology_gap;
  const heroEl = document.getElementById('heroGapValue');
  if (gap !== undefined && gap !== null) {
    heroEl.textContent = `${gap >= 0 ? '+' : ''}${gap.toFixed(2)}`;
    heroEl.className = `hero-gap-value ${scoreBadgeClass(gap)}`;
  }

  // Weight gauge: where in the adaptive 15-55% band psychology currently
  // sits — the signature mechanism this dashboard is built on, made visible
  // rather than left implicit in the narrative prose.
  const weight = composite.psychology_weight;
  const [wMin, wMax] = composite.psychology_weight_range || [0.15, 0.55];
  if (weight !== undefined && weight !== null) {
    const wPct = ((weight - wMin) / (wMax - wMin)) * 100;
    document.getElementById('weightGaugeMarker').style.left = `${Math.max(0, Math.min(100, wPct))}%`;
    document.getElementById('weightGaugeCurrentLabel').textContent = `${Math.round(weight * 100)}% now`;
  }
  document.getElementById('weightGaugeMinLabel').textContent = `${Math.round(wMin * 100)}% (calm floor)`;
  document.getElementById('weightGaugeMaxLabel').textContent = `${Math.round(wMax * 100)}% (extreme ceiling)`;

  const pillarScores = composite.pillar_scores || {};
  document.getElementById('pillarScoreRow').innerHTML =
    pillarSignalHTML('Finance', pillarScores.finance, 'Yield curve, valuation vs. history, and sector breadth, averaged (-1 to +1)') +
    pillarSignalHTML('Economics', pillarScores.economics, 'ISM PMI, real policy rate, and unemployment vs. full employment, averaged (-1 to +1)') +
    pillarSignalHTML('Psychology', pillarScores.psychology, 'VIX, put/call ratio, AAII spread, consumer sentiment, HY credit spread, news sentiment, and NAAIM exposure, standardized and averaged (-1 to +1)');

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

function formatAnalogueDate(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`);
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function signedPct(value) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

// Finds the 3 historical trading days (since 1999) whose Finance/Economics/
// Psychology mix most closely matched today's, and shows what the S&P 500
// did next — computed backend-side in compute_historical_analogues()
// against scripts/backtest.py's daily reconstruction. Shown as a one-line
// teaser plus an expandable comparison table, not a big new section, so it
// adds a genuinely interesting signal without undoing the "don't overwhelm
// on first look" cleanup elsewhere on this page.
function renderHistoricalAnalogues(matches, todayScores) {
  const block = document.getElementById('analogueBlock');
  if (!matches || matches.length === 0) {
    block.style.display = 'none';
    return;
  }
  block.style.display = '';

  const top = matches[0];
  document.getElementById('analogueTeaser').innerHTML =
    `Closest match: <strong>${formatAnalogueDate(top.date)}</strong> — the S&P 500 went on to return ` +
    `<strong>${signedPct(top.fwd_1m_return)}</strong> over the next month and <strong>${signedPct(top.fwd_6m_return)}</strong> over the next 6.`;

  const todayRow = `<tr class="analogue-today-row">
    <td>Today</td>
    <td>${(todayScores.finance ?? 0).toFixed(2)}</td>
    <td>${(todayScores.economics ?? 0).toFixed(2)}</td>
    <td>${(todayScores.psychology ?? 0).toFixed(2)}</td>
    <td>—</td><td>—</td><td>—</td>
  </tr>`;
  const matchRows = matches.map((m) => `<tr>
    <td>${formatAnalogueDate(m.date)}</td>
    <td>${m.finance_score.toFixed(2)}</td>
    <td>${m.economics_score.toFixed(2)}</td>
    <td>${m.psychology_score.toFixed(2)}</td>
    <td>${signedPct(m.fwd_1m_return)}</td>
    <td>${signedPct(m.fwd_3m_return)}</td>
    <td>${signedPct(m.fwd_6m_return)}</td>
  </tr>`).join('');

  document.getElementById('analogueTable').innerHTML =
    '<thead><tr><th>Date</th><th>Finance</th><th>Economics</th><th>Psychology</th><th>+1M</th><th>+3M</th><th>+6M</th></tr></thead>' +
    `<tbody>${todayRow}${matchRows}</tbody>`;
}

function renderFinance(finance, score, historyEntries) {
  document.getElementById('financeSignal').innerHTML = pillarSignalHTML('Signal', score, 'This pillar\'s -1 to +1 score, feeding into the composite regime read');

  const metrics = document.getElementById('financeKeyMetrics');
  metrics.innerHTML =
    metricHTML(finance.sp500_pe, 'S&P 500 P/E', '', 'The S&P 500\'s price-to-earnings ratio measures how much investors are paying for each dollar of trailing corporate earnings. A P/E meaningfully above its long-run average (~16.5x) signals stocks are priced for continued strong growth and leaves less margin for error — a valuation headwind that argues for a more cautious, quality-focused equity stance rather than chasing further multiple expansion. A P/E below the historical average suggests stocks are comparatively cheap, which has historically supported higher forward returns and a more constructive stance on adding equity exposure.') +
    metricHTML(finance.yield_curve_10y_2y, '10y-2y Spread', '%', 'This is the gap between the 10-year and 2-year U.S. Treasury yields — the classic yield curve. A positive, upward-sloping curve reflects a market pricing in continued growth and is historically consistent with a risk-on posture toward equities. An inverted curve (negative spread) has preceded nearly every U.S. recession since the 1970s and historically argues for de-risking toward quality and shorter-duration fixed income ahead of a potential downturn — though the lag before a recession actually arrives can run well over a year.');

  renderMiniTrend(
    'finance', 'peTrendLabel', 'peTrendWrap', 'peTrendChart',
    historyEntries, 'sp500_pe', 'S&P 500 P/E', CHART_COLORS.finance, 'rgba(0, 113, 227, 0.12)',
  );

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
    metricHTML(economics.cpi_yoy, 'CPI YoY', '%', 'The Consumer Price Index year-over-year captures the economy\'s headline inflation rate. Inflation running hot above the Fed\'s ~2% target pressures the Fed to keep policy restrictive, which is a headwind for both equity valuations and bond prices — supporting a tilt toward real assets (commodities, gold, TIPS) as an inflation hedge. Cooling inflation gives the Fed room to ease, which is typically supportive for both stocks and bonds and argues for adding duration and risk exposure.') +
    metricHTML(economics.ism_pmi, 'ISM PMI', '', 'The ISM Manufacturing Purchasing Managers\' Index is a monthly survey of manufacturing activity; a reading above 50 signals expansion, below 50 signals contraction. A PMI comfortably above 50 supports cyclical, economically-sensitive sectors (industrials, materials, financials) and a growth-oriented equity tilt. A PMI below 50 — especially if falling — is an early warning of economic slowing, historically favoring a defensive rotation into staples, healthcare, and utilities.') +
    metricHTML(economics.unemployment_rate, 'Unemployment', '%', 'The U.S. unemployment rate measures the share of the labor force without a job and actively looking for one. A rising rate signals a weakening labor market and slowing consumer spending power, arguing for defensive positioning and caution on consumer-discretionary and cyclical names. A very low rate is double-edged: it reflects a healthy economy, but can also indicate late-cycle labor-market tightness that risks overheating and keeps the Fed restrictive for longer — read this one relative to where the cycle stands, not in isolation.') +
    metricHTML(economics.fed_funds_rate, 'Fed Funds Rate', '%', 'The Federal Reserve\'s target interest rate is its primary lever for cooling or stimulating the economy. A high rate relative to inflation (a restrictive real rate) is a headwind for equities and long-duration bonds alike, and historically favors holding more cash/short-duration instruments and being selective on rate-sensitive sectors (real estate, high-growth tech). A rate that\'s falling, or low relative to inflation, is typically supportive of risk assets and argues for extending duration in fixed income and leaning into growth equities.');

  renderCycleStage(cycleStage);

  renderMiniTrend(
    'economics', 'pmiTrendLabel', 'pmiTrendWrap', 'pmiTrendChart',
    historyEntries, 'ism_pmi', 'ISM PMI', CHART_COLORS.economics, 'rgba(36, 138, 61, 0.12)',
  );
  renderMiniTrend(
    'economics', 'cpiTrendLabel', 'cpiTrendWrap', 'cpiTrendChart',
    historyEntries, 'cpi_yoy', 'CPI YoY', CHART_COLORS.economics, 'rgba(36, 138, 61, 0.12)',
  );
  renderMiniTrend(
    'economics', 'unemploymentTrendLabel', 'unemploymentTrendWrap', 'unemploymentTrendChart',
    historyEntries, 'unemployment_rate', 'Unemployment', CHART_COLORS.economics, 'rgba(36, 138, 61, 0.12)',
  );
  renderMiniTrend(
    'economics', 'fedFundsTrendLabel', 'fedFundsTrendWrap', 'fedFundsTrendChart',
    historyEntries, 'fed_funds_rate', 'Fed Funds Rate', CHART_COLORS.economics, 'rgba(36, 138, 61, 0.12)',
  );
  renderRealRateChart(economics);
}

function renderPsychology(psychology, score, historyEntries) {
  document.getElementById('psychologySignal').innerHTML = pillarSignalHTML('Fear/Greed', score, 'This pillar\'s -1 (fear) to +1 (greed) score, feeding into the composite regime read');

  const metrics = document.getElementById('psychologyKeyMetrics');
  metrics.innerHTML =
    metricHTML(psychology.vix, 'VIX', '', 'The VIX — the market\'s "fear gauge" — reflects the volatility investors expect priced into S&P 500 options over the next 30 days. A low, stable VIX reflects market calm and typically coincides with strong risk appetite, but persistently low volatility can also breed complacency (per Minsky\'s Financial Instability Hypothesis) that leaves portfolios vulnerable to a sharp reversal. A spiking VIX signals acute fear and de-risking — historically these spikes have also marked attractive entry points for contrarian investors willing to buy into panic, though timing the bottom is difficult.') +
    metricHTML(psychology.put_call_ratio, 'Put/Call Ratio', '', 'This compares the volume of put options (bets on/hedges against a decline) to call options (bets on a rise) traded across Cboe exchanges. A ratio meaningfully above 1 shows investors paying up for downside protection — a Prospect Theory-style loss-aversion signal that can mean either genuine fear (bearish) or, when extreme, an overly-hedged market poised for a relief rally as protection unwinds (a contrarian bullish tell). A low ratio shows call-heavy, optimistic positioning, supporting a risk-on stance but also flagging complacency if valuations are already stretched.') +
    metricHTML(psychology.consumer_sentiment, 'Consumer Sentiment (U. Mich.)', '', 'This monthly survey captures how optimistic U.S. consumers feel about the economy and their own finances. Rising sentiment supports continued consumer spending — the majority of U.S. GDP — and favors consumer-discretionary and broader risk-asset exposure. Falling sentiment, especially from already-depressed levels, warns on consumer-facing sectors and argues for a more defensive tilt, though extremely depressed sentiment has historically also coincided with market bottoms, since it often means the bad news is already priced in.') +
    metricHTML(psychology.hy_oas, 'HY Credit Spread (OAS)', '%', 'This measures the extra yield investors demand to hold high-yield ("junk") corporate bonds over safe Treasuries — effectively the bond market\'s price on default/credit risk. A widening spread signals the credit market pricing in more economic stress, often an earlier and more clear-eyed warning than equities, historically favoring de-risking equity exposure and rotating toward higher-quality credit. A tight spread reflects confidence in corporate health and generally supports a risk-on equity stance, though spreads this tight leave little cushion if sentiment turns.') +
    metricHTML(psychology.news_sentiment, 'SF Fed News Sentiment', '', 'A daily index built from NLP analysis of how positive or negative U.S. economic news coverage reads across major newspapers. Improving news sentiment tends to coincide with (and can reinforce) risk-on positioning as media narratives turn constructive. Deteriorating sentiment can precede or amplify broader risk-off moves, since negative narratives can become self-reinforcing — treat a sharp swing as a corroborating signal alongside the other Psychology readings rather than acting on it alone.') +
    metricHTML(psychology.naaim_exposure, 'NAAIM Manager Exposure', '', 'This is the actual self-reported average equity exposure of active investment managers, from -200% (fully leveraged short) to +200% (fully leveraged long) — real positioning, not just stated opinion like AAII. High exposure shows managers already leaning heavily long, which can be a bullish confirmation but also a contrarian caution flag when combined with stretched valuations, since there\'s less dry powder left to keep buying. Low or negative exposure shows managers defensively positioned, which can flag genuine caution — or, if fundamentals hold up despite the pessimism, a contrarian buying opportunity.');

  const gaugeMarker = document.getElementById('psychGaugeMarker');
  if (score !== undefined && score !== null) {
    gaugeMarker.style.left = `${((score - -1) / 2) * 100}%`;
  }

  renderMiniTrend(
    'psychology', 'vixTrendLabel', 'vixTrendWrap', 'vixTrendChart',
    historyEntries, 'vix', 'VIX', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'putCallTrendLabel', 'putCallTrendWrap', 'putCallTrendChart',
    historyEntries, 'put_call_ratio', 'Put/Call Ratio', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'aaiiSpreadTrendLabel', 'aaiiSpreadTrendWrap', 'aaiiSpreadTrendChart',
    historyEntries, 'aaii_spread', 'AAII Bull-Bear Spread', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'consumerSentimentTrendLabel', 'consumerSentimentTrendWrap', 'consumerSentimentTrendChart',
    historyEntries, 'consumer_sentiment', 'Consumer Sentiment', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'hyOasTrendLabel', 'hyOasTrendWrap', 'hyOasTrendChart',
    historyEntries, 'hy_oas', 'HY Credit Spread (OAS)', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'newsSentimentTrendLabel', 'newsSentimentTrendWrap', 'newsSentimentTrendChart',
    historyEntries, 'news_sentiment', 'SF Fed News Sentiment', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
  );

  renderMiniTrend(
    'psychology', 'naaimTrendLabel', 'naaimTrendWrap', 'naaimTrendChart',
    historyEntries, 'naaim_exposure', 'NAAIM Manager Exposure', CHART_COLORS.psychology, 'rgba(138, 75, 175, 0.12)',
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

// The composite trend chart lives inside a collapsed-by-default <details>
// (progressive disclosure, per Will's memo item 5) — Chart.js sizes a
// canvas at creation time, so a chart created while its container is
// display:none renders at 0x0 until something resizes it, same issue
// PANEL_CHARTS/showTab() already solves for tab switches.
document.getElementById('compositeDetails').addEventListener('toggle', (e) => {
  if (e.target.open) ALL_CHARTS.forEach((chart) => chart.resize());
});

// Same fix for each tab's collapsed "Historical trends" section — bundling
// every sparkline behind one toggle is the main "don't overwhelm on first
// look" change, but it means those charts are born hidden too.
['financeTrendsDetails', 'economicsTrendsDetails', 'psychologyTrendsDetails'].forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener('toggle', () => {
    if (el.open) ALL_CHARTS.forEach((chart) => chart.resize());
  });
});

refreshDashboard();
setInterval(refreshDashboard, AUTO_REFRESH_MS);

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

// Chart.js sizes a canvas at creation time, so charts inside a panel that
// starts hidden (display:none) render at 0x0 until resized after becoming
// visible — track instances per panel so showTab() can fix that up.
const PANEL_CHARTS = { finance: [], economics: [], psychology: [] };
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
    if (chart.options.scales) {
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

async function loadSnapshot() {
  const res = await fetch('data/snapshot.json');
  return res.json();
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
  document.getElementById('compositeNarrative').textContent = composite.narrative;

  const badge = document.getElementById('compositeBadge');
  badge.textContent = composite.regime;
  badge.className = `sbadge ${regimeBadgeClass(composite.regime)}`;

  const [min, max] = composite.score_range;
  const pct = ((composite.score - min) / (max - min)) * 100;
  document.getElementById('scoreMarker').style.left = `${pct}%`;

  document.getElementById('lastUpdated').textContent =
    `Last updated: ${new Date(lastUpdated).toLocaleString()}`;
}

function renderFinance(finance) {
  const metrics = document.getElementById('financeKeyMetrics');
  metrics.innerHTML =
    metricHTML(finance.sp500_pe, 'S&P 500 P/E') +
    metricHTML(finance.yield_curve_10y_2y, '10y-2y Spread', '%');

  trackChart('finance', new Chart(document.getElementById('sectorChart'), {
    type: 'bar',
    data: {
      labels: Object.keys(finance.sector_returns_1m),
      datasets: [{
        label: '1M Sector Return (%)',
        data: Object.values(finance.sector_returns_1m),
        backgroundColor: CHART_COLORS.finance,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 32,
      }],
    },
    options: { ...chartDefaults(), plugins: { legend: { display: false } } },
  }));

  trackChart('finance', new Chart(document.getElementById('assetClassChart'), {
    type: 'bar',
    data: {
      labels: Object.keys(finance.asset_class_returns_1m),
      datasets: [{
        label: '1M Asset Class Return (%)',
        data: Object.values(finance.asset_class_returns_1m),
        backgroundColor: CHART_COLORS.finance,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 32,
      }],
    },
    options: { ...chartDefaults(), plugins: { legend: { display: false } } },
  }));
}

function renderEconomics(economics) {
  const metrics = document.getElementById('economicsKeyMetrics');
  metrics.innerHTML =
    metricHTML(economics.cpi_yoy, 'CPI YoY', '%') +
    metricHTML(economics.ism_pmi, 'ISM PMI') +
    metricHTML(economics.unemployment_rate, 'Unemployment', '%') +
    metricHTML(economics.fed_funds_rate, 'Fed Funds Rate', '%');
}

function renderPsychology(psychology) {
  const metrics = document.getElementById('psychologyKeyMetrics');
  metrics.innerHTML =
    metricHTML(psychology.vix, 'VIX') +
    metricHTML(psychology.put_call_ratio, 'Put/Call Ratio');

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

loadSnapshot().then((snapshot) => {
  renderComposite(snapshot.composite, snapshot.meta.last_updated);
  renderFinance(snapshot.finance);
  renderEconomics(snapshot.economics);
  renderPsychology(snapshot.psychology);
});

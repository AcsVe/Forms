/* يرسم كل <canvas data-chart='{"type","labels","series":[{label,data}],"opts"}'> بمكتبة Chart.js.
   الألوان بترتيب ثابت (لوحة مُتحقَّق منها لعمى الألوان)، والسلسلة الواحدة بلون واحد دون مفتاح. */
(function () {
  'use strict';
  const PALETTE = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
  const RTL = document.documentElement.dir === 'rtl';
  window.CHART_PALETTE = PALETTE;
  function setup() {
    if (!window.Chart) return;
    Chart.defaults.font.family = "'Tajawal', system-ui, sans-serif";
    Chart.defaults.font.size = 13;
    Chart.defaults.color = '#52514e';
    Chart.defaults.borderColor = '#e9eef5';
    Chart.defaults.plugins.tooltip.rtl = RTL;
    Chart.defaults.plugins.legend.rtl = RTL;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
  }
  function build(canvas, cfg) {
    const many = cfg.series.length > 1;
    const round = cfg.type === 'doughnut' || cfg.type === 'pie';
    const stacked = !!(cfg.opts && cfg.opts.stacked);
    const datasets = cfg.series.map((s, i) => {
      const color = s.color || PALETTE[i % PALETTE.length];
      const d = { label: s.label, data: s.data };
      if (round) {
        d.backgroundColor = cfg.labels.map((_, j) => PALETTE[j % PALETTE.length]);
        d.borderColor = '#fff'; d.borderWidth = 2;
      } else if (cfg.type === 'line') {
        Object.assign(d, { borderColor: color, backgroundColor: color + '22', borderWidth: 2, pointRadius: 3,
          pointHoverRadius: 6, tension: 0.25, fill: !many });
      } else {
        Object.assign(d, { backgroundColor: color, borderRadius: 4, borderSkipped: 'start', maxBarThickness: 34,
          borderColor: '#fff', borderWidth: stacked ? 1 : 0 });
      }
      return d;
    });
    const horizontal = cfg.opts && cfg.opts.indexAxis === 'y';
    const pct = cfg.opts && cfg.opts.percent;
    const options = {
      responsive: true, indexAxis: horizontal ? 'y' : 'x', interaction: { mode: round ? 'nearest' : 'index', intersect: false },
      plugins: { legend: { display: many || round, position: 'bottom' },
        tooltip: { callbacks: pct ? { label: (c) => `${c.dataset.label}: ${c.parsed[horizontal ? 'x' : 'y']}%` } : {} } },
    };
    if (!round) {
      const val = { beginAtZero: true, ticks: { precision: 0 }, stacked, grid: { color: '#eef2f7' } };
      if (pct) { val.max = stacked ? 100 : undefined; val.ticks.callback = (v) => v + '%'; }
      const cat = { stacked, grid: { display: false }, reverse: RTL && !horizontal,
        ticks: { autoSkip: true, maxRotation: 0, callback: function (v) { const l = this.getLabelForValue(v); return String(l).length > 22 ? String(l).slice(0, 21) + '…' : l; } } };
      options.scales = horizontal ? { x: Object.assign(val, { reverse: RTL }), y: Object.assign(cat, { reverse: false, position: RTL ? 'right' : 'left' }) }
        : { x: cat, y: Object.assign(val, { position: RTL ? 'right' : 'left' }) };
    } else {
      options.cutout = cfg.type === 'doughnut' ? '58%' : 0;
    }
    if (canvas._chart) canvas._chart.destroy();
    canvas._chart = new Chart(canvas, { type: cfg.type, data: { labels: cfg.labels, datasets }, options });
  }
  function init(root) {
    setup();
    (root || document).querySelectorAll('canvas[data-chart]').forEach((c) => {
      if (c._chart) return;
      try { build(c, JSON.parse(c.dataset.chart)); } catch (e) { console.warn('chart', e); }
    });
  }
  window.drawCharts = init;
  window.buildChart = build;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => init()); else init();
  document.addEventListener('tab-shown', () => init());
})();

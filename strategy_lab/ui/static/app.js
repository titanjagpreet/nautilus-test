// Strategy Lab front-end: tabs, and charts for backtests, lab reports and comparisons.
// Lightweight Charts 4.2 (equity, price + trade markers) and Plotly 2.35 (heat-map, histogram).
(function () {
  "use strict";

  const COLORS = { text: "#e6edf3", muted: "#8b949e", grid: "#222a35", accent: "#4f9cf9", pos: "#3fb950", neg: "#f85149", warn: "#d29922", grey: "#6e7681", purple: "#a371f7" };
  const PALETTE = [COLORS.accent, COLORS.warn, COLORS.pos, COLORS.purple, COLORS.neg, "#39c5cf"];

  function data(id) {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  }

  function chart(el) {
    el.innerHTML = "";
    const c = LightweightCharts.createChart(el, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: COLORS.muted },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      rightPriceScale: { borderColor: COLORS.grid },
      // fitContent() must show the whole run: by default a point needs >= 0.5 px, so a long backtest (e.g. 8 years
      // of 4h equity) was cut to its most recent years; and keep the fitted range when autoSize resizes the chart.
      timeScale: { borderColor: COLORS.grid, timeVisible: true, minBarSpacing: 0.001, lockVisibleTimeRangeOnResize: true },
      crosshair: { mode: 0 },
    });
    return c;
  }

  function points(pairs) {
    // [[time, value], ...] -> LWC line data, strictly increasing time
    const out = [];
    for (const [time, value] of pairs) {
      if (value === null) continue;
      if (out.length && time <= out[out.length - 1].time) continue;
      out.push({ time, value });
    }
    return out;
  }

  function lines(el, series) {
    if (!el) return;
    const c = chart(el);
    for (const s of series) {
      if (!s.data || !s.data.length) continue;
      const line = c.addLineSeries({ color: s.color, lineWidth: s.width || 2, title: s.name, priceLineVisible: false, lastValueVisible: true });
      line.setData(points(s.data));
    }
    c.timeScale().fitContent();
  }

  function price(el, price, trades) {
    if (!el || !price.bars.length) return;
    const c = chart(el);
    const candles = c.addCandlestickSeries({ upColor: COLORS.pos, downColor: COLORS.neg, borderVisible: false, wickUpColor: COLORS.pos, wickDownColor: COLORS.neg });
    candles.setData(price.bars.map(([time, open, high, low, close]) => ({ time, open, high, low, close })));
    const step = { "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400 }[price.timeframe];
    const markers = [];
    for (const t of trades.slice(0, 2000)) {
      const long = t.side === "long";
      markers.push({ time: Math.floor(t.entry_time / step) * step, position: long ? "belowBar" : "aboveBar", color: long ? COLORS.pos : COLORS.neg, shape: long ? "arrowUp" : "arrowDown", text: long ? "L" : "S" });
      markers.push({ time: Math.floor(t.exit_time / step) * step, position: long ? "aboveBar" : "belowBar", color: t.pnl_net > 0 ? COLORS.pos : COLORS.grey, shape: "circle", text: t.exit_reason });
    }
    markers.sort((a, b) => a.time - b.time);
    candles.setMarkers(markers);
    c.timeScale().fitContent();
  }

  function epochCells(root) {
    for (const td of root.querySelectorAll("[data-epoch]")) {
      td.textContent = new Date(Number(td.dataset.epoch) * 1000).toISOString().slice(0, 16).replace("T", " ");
    }
  }

  const plotLayout = (extra) => Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: COLORS.muted, size: 11 },
    margin: { l: 60, r: 20, t: 10, b: 50 },
  }, extra);

  const StrategyLab = {
    backtest(id) {
      const d = data("bt-" + id);
      if (!d) return;
      lines(document.getElementById("equity-" + id), [
        { name: "strategy", color: COLORS.accent, data: d.equity },
        { name: "buy & hold", color: COLORS.grey, data: d.buy_hold, width: 1 },
      ]);
      price(document.getElementById("price-" + id), d.price, d.trades);
      epochCells(document.getElementById("equity-" + id).closest("section"));
    },

    lab(id) {
      const r = data("lab-" + id);
      if (!r) return;
      lines(document.getElementById("lab-curves-" + id), [
        { name: "whole period", color: COLORS.accent, data: r.curves.equity },
        { name: "buy & hold", color: COLORS.grey, data: r.curves.buy_hold, width: 1 },
        { name: "out-of-sample (tuned)", color: COLORS.warn, data: r.curves.oos_equity },
        { name: "walk-forward (chained OOS)", color: COLORS.purple, data: r.curves.walk_forward_equity },
      ]);
      const hm = r.heatmap;
      const heatEl = document.getElementById("lab-heat-" + id);
      if (hm && heatEl && window.Plotly) {
        const y = hm.y ? hm.y_values : [""];
        const traces = [{ type: "heatmap", x: hm.x_values.map(String), y: y.map(String), z: hm.objective, colorscale: [[0, COLORS.neg], [0.5, "#30363d"], [1, COLORS.pos]], zmid: 0, hoverongaps: false,
                          colorbar: { title: { text: r.objective, side: "right" } }, text: hm.trades, hovertemplate: "%{x} / %{y}<br>" + r.objective + " %{z:.2f}<br>trades %{text}<extra></extra>" }];
        const marks = [];
        if (hm.best) marks.push({ x: String(hm.x_values[hm.best[1]]), y: String(y[hm.best[0]]), text: "★" });
        marks.push({ x: String(hm.x_values[hm.current[1]]), y: String(y[hm.current[0]]), text: "○" });
        traces.push({ type: "scatter", mode: "text", x: marks.map((m) => m.x), y: marks.map((m) => m.y), text: marks.map((m) => m.text), textfont: { size: 18, color: COLORS.text }, hoverinfo: "skip", showlegend: false });
        Plotly.newPlot(heatEl, traces, plotLayout({ xaxis: { title: { text: hm.x }, type: "category" }, yaxis: { title: { text: hm.y || "" }, type: "category" } }), { displayModeBar: false, responsive: true });
      }
      const mcEl = document.getElementById("lab-mc-" + id);
      if (mcEl && window.Plotly && r.monte_carlo.final_returns.length) {
        const p = r.monte_carlo.final_return_pct;
        const shapes = ["p5", "p50", "p95"].map((k) => ({ type: "line", x0: p[k], x1: p[k], yref: "paper", y0: 0, y1: 1, line: { color: k === "p50" ? COLORS.text : COLORS.warn, dash: "dot" } }));
        Plotly.newPlot(mcEl, [{ type: "histogram", x: r.monte_carlo.final_returns, nbinsx: 50, marker: { color: COLORS.accent } }],
          plotLayout({ xaxis: { title: { text: "final return %" } }, yaxis: { title: { text: "resamples" } }, shapes, bargap: 0.05 }), { displayModeBar: false, responsive: true });
      }
    },

    compare() {
      const curves = data("compare-data");
      if (!curves) return;
      const series = Object.entries(curves).map(([id, pairs], i) => {
        const base = pairs.length ? pairs[0][1] : 1;
        return { name: "#" + id, color: PALETTE[i % PALETTE.length], data: pairs.map(([t, v]) => [t, (v / base) * 100]) };
      });
      lines(document.getElementById("compare-chart"), series);
    },

    tabs(root) {
      for (const group of root.querySelectorAll("[data-tabs]")) {
        for (const tab of group.querySelectorAll(".tab")) {
          tab.addEventListener("click", (event) => {
            event.preventDefault();
            for (const other of group.querySelectorAll(".tab")) {
              other.classList.toggle("active", other === tab);
              document.getElementById(other.dataset.tab).classList.toggle("hidden", other !== tab);
            }
          });
        }
      }
    },
  };

  window.StrategyLab = StrategyLab;
  document.addEventListener("DOMContentLoaded", () => StrategyLab.tabs(document));
})();

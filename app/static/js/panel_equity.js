// app/static/js/panel.js
// SIGMOM — Equity Module (STRICT: backend fields only)
// Uses only `timestamp` and `realized_pnl` from backend rows.
// Locale-aware, fixed START_CAPITAL, no CAP button, no quote inference.
(() => {
  // ---- CONFIG ----
  const START_CAPITAL = 1000;    // fixed starting capital (edit in code)
  const MIN_CAGR_DAYS = 21;      // don't show annual return for shorter spans
  const MAX_ANNUAL_PCT = 5000;   // cap display to +/- 5000% to avoid silly numbers

  // ---- Access gate (frontend UX) ----
  function checkEquityAllowed() {
    if (typeof window.EQUITY_ALLOWED === 'boolean') return window.EQUITY_ALLOWED;
    if (typeof window.EQUITY_ALLOWED === 'string') return window.EQUITY_ALLOWED.toLowerCase() === 'true';
    return false;
  }

  function lockEquityUI() {
    // KPI grid
    const kpi = document.getElementById('equity-kpi');
    if (kpi) kpi.style.display = 'none';

    // Grafik kartı (canvas'ın en yakın kartını veya konteynerini sakla)
    const c = document.getElementById('equityChart');
    const card = c?.closest('.card') || c?.parentElement || null;
    if (card) card.style.display = 'none';

    // İsteğe bağlı kısa bilgi notu
    const holder = (kpi && kpi.parentElement) || document.body;
    const note = document.createElement('div');
    note.className = 'mt-4 text-sm text-slate-500 dark:text-slate-400';
    note.textContent = 'Bazı bölümlere erişim referans onayı gerektirir.';
    holder.appendChild(note);
  }

  // ---- Locale ----
  const LOCALE =
    (navigator.languages && navigator.languages[0]) ||
    navigator.language ||
    "en-US";
  const nf2 = new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  // ---- DOM (hooks are optional) ----
  const $ = (s) => document.querySelector(s);
  const els = {
    statBal: $("#stat-balance"),
    statNet: $("#stat-net"),
    statWin: $("#stat-win"),
    statSharpe: $("#stat-sharpe"),
    statMdd: $("#stat-mdd"),
    statCagr: $("#stat-cagr"),
    chart: $("#equityChart"),
  };

  // ---- Utils ----
  const unwrap = (d) =>
    Array.isArray(d) ? d : d?.items || d?.results || d?.data || d?.records || [];
  const toDate = (v) => {
    if (v == null) return null;
    if (typeof v === "number") return new Date(v < 1e12 ? v * 1000 : v);
    const s = String(v);
    if (/^\d{10}$/.test(s)) return new Date(Number(s) * 1000);
    if (/^\d{13}$/.test(s)) return new Date(Number(s));
    const d = new Date(s);
    return isNaN(d) ? null : d;
  };
  const toNum = (v) => {
    if (v == null) return 0;
    const n = Number(String(v).replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  };

  // STRICT normalization: only backend fields (`timestamp`, `realized_pnl`)
  function normalizeTrade(t) {
    const ts = toDate(t?.timestamp);
    const pnl = toNum(t?.realized_pnl);
    return ts ? { ...t, __ts: ts, __pnl: pnl } : null;
  }

  // ---- Stats helpers ----
  function groupDailyPnL(rows) {
    const map = new Map(); // yyyy-mm-dd -> pnl
    rows.forEach((t) => {
      const d = t.__ts;
      const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(
        2,
        "0"
      )}-${String(d.getDate()).padStart(2, "0")}`;
      map.set(k, (map.get(k) || 0) + (Number.isFinite(t.__pnl) ? t.__pnl : 0));
    });
    const days = Array.from(map.keys()).sort(
      (a, b) => new Date(a) - new Date(b)
    );
    return { days, dayPnls: days.map((k) => map.get(k) || 0) };
  }

  function computeStats(rows) {
    const cap = START_CAPITAL;
    const sorted = rows.slice().sort((a, b) => a.__ts - b.__ts);
    const sum = sorted.reduce(
      (a, b) => a + (Number.isFinite(b.__pnl) ? b.__pnl : 0),
      0
    );
    const balance = cap + sum;
    const win = sorted.length
      ? (sorted.filter((x) => (x.__pnl || 0) > 0).length / sorted.length) * 100
      : 0;

    // Sharpe (daily)
    const { days, dayPnls } = groupDailyPnL(sorted);
    let sharpe = 0;
    if (dayPnls.length > 1) {
      let bal = cap;
      const rets = [];
      dayPnls.forEach((p) => {
        const prev = bal || 1e-9;
        bal += p;
        rets.push(p / prev);
      });
      const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
      const sd = Math.sqrt(
        rets.reduce((a, r) => a + (r - mean) * (r - mean), 0) /
          (rets.length - 1 || 1)
      );
      if (sd > 0) sharpe = (mean / sd) * Math.sqrt(365);
    }

    // Max Drawdown via equity curve
    let peak = cap,
      mdd = 0,
      run = cap;
    sorted.forEach((t) => {
      run += Number.isFinite(t.__pnl) ? t.__pnl : 0;
      peak = Math.max(peak, run);
      const dd = (peak - run) / (peak || 1);
      if (dd > mdd) mdd = dd;
    });

    // Annualized return with guard
    const spanDays = days.length
      ? Math.max(
          (new Date(days[days.length - 1]) - new Date(days[0])) / 86400000,
          0
        )
      : 0;
    let cagr = null;
    if (spanDays >= MIN_CAGR_DAYS) {
      const years = spanDays / 365;
      const ratio = Math.max(balance / cap, 1e-9);
      const v = years > 0 ? Math.pow(ratio, 1 / years) - 1 : 0;
      if (Number.isFinite(v)) cagr = v;
    }

    return { balance, net: sum, win, sharpe, mdd, cagr, spanDays };
  }

  function fmtAnnualPct(cagr) {
    if (cagr == null) return "—";
    const pct = Math.min(Math.max(cagr * 100, -MAX_ANNUAL_PCT), MAX_ANNUAL_PCT);
    return nf2.format(pct) + "%";
  }

  // ---- Equity series ----
  function buildEquity(rows) {
    const cap = START_CAPITAL;
    const sorted = rows.slice().sort((a, b) => a.__ts - b.__ts);
    const pts = [];
    let bal = cap;
    sorted.forEach((t) => {
      bal += Number.isFinite(t.__pnl) ? t.__pnl : 0;
      pts.push({ x: t.__ts, y: bal });
    });
    if (!pts.length) {
      const now = Date.now();
      pts.push(
        { x: new Date(now - 6 * 3600 * 1000), y: cap },
        { x: new Date(now), y: cap }
      );
    }
    return pts;
  }

  // ---- Chart.js drawing ----
  let chart;
  function drawChart(points) {
    if (!els.chart || typeof Chart === "undefined") return;
    if (chart) chart.destroy();
    chart = new Chart(els.chart.getContext("2d"), {
      type: "line",
      data: {
        datasets: [
          {
            label: "Balance",
            data: points,
            parsing: true,
            borderWidth: 2,
            stepped: true,
            pointRadius: 2,
            tension: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: "time", time: { tooltipFormat: "DD.MM.YYYY HH:mm" } },
          y: { ticks: { callback: (v) => nf2.format(v) } },
        },
        plugins: {
          tooltip: {
            mode: "nearest",
            intersect: false,
            callbacks: {
              title: (items) =>
                items?.[0]?.parsed?.x
                  ? new Date(items[0].parsed.x).toLocaleString(LOCALE)
                  : "",
              label: (ctx) => `Balance: ${nf2.format(ctx.parsed.y)}`,
            },
          },
        },
      },
    });
  }

  // ---- Data loaders ----
  async function getJSON(url) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 10000);
    try {
      const r = await fetch(url, { signal: ctrl.signal, credentials: "include" });
      if (!r.ok) throw new Error("api");
      return await r.json();
    } finally {
      clearTimeout(t);
    }
  }
  async function loadTrades() {
    const raw = await getJSON(`/api/me/recent-trades?limit=200`);
    return unwrap(raw).map(normalizeTrade).filter(Boolean);
  }

  // ---- Render loop ----
  async function refresh() {
    try {
      const rows = await loadTrades();
      const stats = computeStats(rows);
      const equity = buildEquity(rows);

      if (els.statBal) els.statBal.textContent = nf2.format(stats.balance);
      if (els.statNet)
        els.statNet.textContent =
          (stats.net >= 0 ? "+" : "-") + nf2.format(Math.abs(stats.net));
      if (els.statWin) els.statWin.textContent = nf2.format(stats.win) + "%";
      if (els.statSharpe) els.statSharpe.textContent = nf2.format(stats.sharpe);
      if (els.statMdd) els.statMdd.textContent = nf2.format(stats.mdd * 100) + "%";
      if (els.statCagr) els.statCagr.textContent = fmtAnnualPct(stats.cagr);

      drawChart(equity);
    } catch (e) {
      console.error("equity refresh failed", e);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const allowed = checkEquityAllowed();
    if (!allowed) { lockEquityUI(); return; }

    refresh();
  });
})();

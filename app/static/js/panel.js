// panel.js — lightweight-charts + tema + referral verify (tam)
(() => {
  // ==== Helpers ====
  const $ = (sel) => document.querySelector(sel);
  const isDark = () => document.documentElement.classList.contains('dark');
  const setText = (sel, v) => { const el = $(sel); if (el) el.textContent = v; };
  const fmtPct = (v) => (v == null ? '—' : (Math.round(v * 10) / 10) + '%');
  const fmtNum = (v) => (v == null ? '—' : Number(v).toLocaleString('tr-TR'));
  const fmtPnl = (v) => (v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2));

  // ==== Tema ====
  const themeBtn = document.querySelector('[data-theme-toggle]');
  themeBtn?.addEventListener('click', () => {
    const nextDark = !isDark();
    document.documentElement.classList.toggle('dark', nextDark);
    localStorage.setItem('theme', nextDark ? 'dark' : 'light');
    applyChartTheme(nextDark);
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const wantDark = e.matches;
    document.documentElement.classList.toggle('dark', wantDark);
    localStorage.setItem('theme', wantDark ? 'dark' : 'light');
    applyChartTheme(wantDark);
  });

  // ==== Grafik ====
  const chartEl = document.getElementById('chart');
  /** @type {import('lightweight-charts').IChartApi} */ let chart;
  /** @type {import('lightweight-charts').ISeriesApi<"Candlestick">} */ let candle;

  function makeChart() {
    chartEl.innerHTML = '';
    chart = LightweightCharts.createChart(chartEl, {
      autoSize: true,
      timeScale: { rightOffset: 3, barSpacing: 6, borderVisible: false },
      crosshair: { mode: 1 },
      grid: { vertLines: { visible: true }, horzLines: { visible: true } },
      layout: { background: { type: 'solid', color: '#ffffff' }, textColor: '#334155' },
    });
    candle = chart.addCandlestickSeries({
      upColor: '#16a34a', downColor: '#dc2626',
      wickUpColor: '#16a34a', wickDownColor: '#dc2626',
      borderVisible: false, priceLineVisible: false,
    });
    applyChartTheme(isDark());
    new ResizeObserver(() => chart?.timeScale().fitContent()).observe(chartEl);
  }

  function applyChartTheme(dark) {
    chart?.applyOptions({
      layout: {
        background: { type: 'solid', color: dark ? '#0f172a' : '#ffffff' },
        textColor: dark ? '#cbd5e1' : '#334155',
      },
      grid: {
        vertLines: { color: dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.16)' },
        horzLines: { color: dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.16)' },
      },
    });
    candle?.applyOptions({
      upColor: dark ? '#10b981' : '#16a34a',
      downColor: dark ? '#ef4444' : '#dc2626',
      wickUpColor: dark ? '#10b981' : '#16a34a',
      wickDownColor: dark ? '#ef4444' : '#dc2626',
    });
  }

  // ==== Veri ====
  async function loadKlines({ symbol = 'BTCUSDT', tf = '15m', limit = 500 } = {}) {
    try {
      const r = await fetch(`/api/market/klines?symbol=${symbol}&tf=${tf}&limit=${limit}`, { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error('no api');
      const data = await r.json();
      const rows = Array.isArray(data) ? data : data.items || [];
      const series = rows.map(row => {
        if (Array.isArray(row)) {
          const ts = Math.floor((row[0] ?? row.t) / 1000);
          return { time: ts, open: +row[1], high: +row[2], low: +row[3], close: +row[4] };
        } else {
          const ts = Math.floor((row.t ?? row.ts) / 1000);
          return { time: ts, open: +row.o, high: +row.h, low: +row.l, close: +row.c };
        }
      });
      if (series.length) candle.setData(series);
      return series;
    } catch {
      const demo = makeDemoSeries();
      candle.setData(demo);
      return demo;
    }
  }

  async function loadSignals({ symbol = 'BTCUSDT', limit = 200 } = {}) {
    try {
      const r = await fetch(`/api/me/signals?symbol=${symbol}&limit=${limit}`, { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error('no api');
      const d = await r.json();
      const items = Array.isArray(d) ? d : d.items || [];
      const markers = items.map(s => {
        const t = Math.floor(new Date(s.ts || s.time).getTime() / 1000);
        const isOpen = (s.mode || s.type || '').toLowerCase() === 'open';
        const isLong = (s.side || '').toUpperCase() === 'LONG';
        const pos = isOpen ? (isLong ? 'belowBar' : 'aboveBar') : (isLong ? 'aboveBar' : 'belowBar');
        const price = s.price ? Number(s.price) : undefined;
        return {
          time: t, position: pos,
          shape: isOpen ? (isLong ? 'arrowUp' : 'arrowDown') : 'circle',
          color: isOpen ? (isLong ? '#10b981' : '#ef4444') : '#0ea5e9',
          text: `${(s.symbol || '').replace('USDT','')} ${(s.side || '').toUpperCase()} ${(s.mode || '').toUpperCase()}`,
          ...(price ? { price } : {}),
        };
      });
      candle.setMarkers(markers);
      return markers;
    } catch {
      candle.setMarkers([]);
      return [];
    }
  }

  async function loadOverview() {
    try {
      const r = await fetch('/api/me/overview', { headers: { 'Accept': 'application/json' } });
      if (!r.ok) return;
      const d = await r.json();
      setText('#kpi-pnl', fmtPnl(d.pnl_7d));
      setText('#kpi-win', fmtPct(d.winrate_30d));
      setText('#kpi-open', fmtNum(d.open_trade_count));
      setText('#kpi-dd', fmtPct(d.max_dd_30d));
      setText('#kpi-sharpe', d.sharpe_30d ?? '—');
      setText('#kpi-last', d.last_signal_at ? new Date(d.last_signal_at).toLocaleString('tr-TR') : '—');
    } catch {}
  }

  function makeDemoSeries() {
    const out = [];
    let t = Math.floor(Date.now()/1000) - 60*15*500;
    let price = 64000;
    for (let i = 0; i < 500; i++) {
      const vol = (Math.sin(i/15) + Math.random()*0.5) * 60;
      const open = price;
      const close = price + (Math.random()-0.5)*vol;
      const high = Math.max(open, close) + Math.random()*20;
      const low = Math.min(open, close) - Math.random()*20;
      out.push({ time: t, open, high, low, close });
      t += 60*15;
      price = close;
    }
    return out;
  }

  // ==== Referral modal & verify ====
  const refBtn = $('#open-referral');
  const refDlg = $('#ref-modal');
  const refForm = $('#ref-form');
  const refInput = $('#ref-code');
  const refMsg = $('#ref-msg');
  const refSubmit = $('#ref-submit');
  const refCancel = $('#ref-cancel');

  function setRefMsg(text, type) {
    if (!refMsg) return;
    refMsg.textContent = text || '';
    refMsg.className = 'text-sm ' + (
      type === 'error'   ? 'text-rose-400' :
      type === 'success' ? 'text-emerald-400' :
                           'text-sky-400'
    );
  }

  function openReferral() {
    if (!refDlg) return;
    if (typeof refDlg.showModal === 'function') refDlg.showModal(); else refDlg.setAttribute('open', '');
    setRefMsg('', 'info');
    refInput.value = '';
    setTimeout(() => refInput?.focus(), 30);
  }
  function closeReferral() {
    if (!refDlg) return;
    if (typeof refDlg.close === 'function') refDlg.close(); else refDlg.removeAttribute('open');
    setRefMsg('', 'info');
    refSubmit.disabled = false;
  }

  refBtn?.addEventListener('click', openReferral);
  refCancel?.addEventListener('click', closeReferral);
  // backdrop click
  refDlg?.addEventListener('click', (e) => { if (e.target === refDlg) closeReferral(); });
  // ESC
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && refDlg?.open) closeReferral(); });

  // Biçimlendirme: AAAA-BBBB-CCCC
  refInput?.addEventListener('input', (e) => {
    let v = (e.target.value || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    v = v.slice(0, 12);
    const parts = [v.slice(0,4), v.slice(4,8), v.slice(8,12)].filter(Boolean);
    e.target.value = parts.join('-');
  });

  refForm?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const code = (refInput.value || '').toUpperCase().trim();
    if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) {
      setRefMsg('Kod biçimi geçersiz. Örn: AB12-CDEF-3456', 'error');
      return;
    }

    try {
      refSubmit.disabled = true;
      setRefMsg('Doğrulanıyor...', 'info');

      const r = await fetch('/referral/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ code }),
      });

      if (r.status === 401) { window.location.href = '/auth/google/login'; return; }

      if (!r.ok) {
        let detail = 'Kod bulunamadı veya size tahsisli/aktif değil.';
        try { const j = await r.json(); detail = j.detail || detail; } catch {}
        setRefMsg(detail, 'error');
        refSubmit.disabled = false;
        return;
      }

      // Başarılı
      setRefMsg('Başarılı! Asil üyelik etkinleştiriliyor…', 'success');
      const chip = $('#role-chip');
      if (chip) {
        chip.textContent = 'Asil Üye';
        chip.className = 'chip bg-emerald-50 dark:bg-emerald-900/20 border-emerald-300/50 text-emerald-700 dark:text-emerald-300';
      }
      const access = $('#access-level'); if (access) access.textContent = 'Asil (tam)';
      setTimeout(() => { closeReferral(); window.location.reload(); }, 700);

    } catch {
      setRefMsg('Ağ hatası. Lütfen tekrar deneyin.', 'error');
      refSubmit.disabled = false;
    }
  });

  // ==== Çalıştır ====
  makeChart();
  loadKlines().then(() => loadSignals());
  loadOverview();

  setInterval(() => { loadKlines(); loadSignals(); }, 30000);
  setInterval(loadOverview, 25000);

  const fs = document.getElementById('feed-status');
  if (fs) fs.textContent = 'Bağlantı: kapalı';
})();

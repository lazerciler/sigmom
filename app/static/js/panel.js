// panel.js — grafik/marker + otomatik sembol seçimli panel
(() => {
  // ==== helpers ====
  const $ = (sel) => document.querySelector(sel);
  const isDark = () => document.documentElement.classList.contains('dark');
  const setText = (sel, v) => { const el = $(sel); if (el) el.textContent = v; };
  const fmtPct = (v) => (v == null ? '—' : (Math.round(v * 10) / 10) + '%');
  let fmtNum  = (v) => (v == null ? '—' : String(v));
  let fmtPnl  = (v) => {
    if (v == null) return '—';
    const x = Number(v); return (x >= 0 ? '+' : '-') + Math.abs(x).toFixed(2);
  };

  // ==== tema ====
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

  // ==== grafik ====
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
    // Zaman etiketlerinde saat/dk/sn gösterimi
    chart.applyOptions({
      timeScale: { timeVisible: true, secondsVisible: true },
      localization: {
        locale: LOCALE, // dosyada tanımlı (i18n helpers)
        timeFormatter: (ts) => {
          const d = new Date(ts * 1000);
          return new Intl.DateTimeFormat(LOCALE, {
            year: '2-digit', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
          }).format(d);
        },
      },
    });
    candle = chart.addCandlestickSeries({
      upColor: '#16a34a', downColor: '#dc2626',
      wickUpColor: '#16a34a', wickDownColor: '#dc2626',
      borderVisible: false, priceLineVisible: false,
    });
    applyChartTheme(isDark());
    new ResizeObserver(() => chart?.timeScale().fitContent()).observe(chartEl);
    ensureJumpBtn();
    chart.timeScale().subscribeVisibleTimeRangeChange(updateJumpBtnVisibility);
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

  // ==== "En son çubuğa kaydır" butonu ====
  let _jumpBtn = null;
  function ensureJumpBtn() {
    if (_jumpBtn || !chartEl) return _jumpBtn;
    _jumpBtn = document.createElement('button');
    _jumpBtn.id = 'jump-latest';
    _jumpBtn.type = 'button';

    // Sağ ortada
    _jumpBtn.className =
      'hidden absolute right-3 bottom-3 z-10 ' +
      'h-8 w-8 grid place-items-center rounded-md ' +
      'bg-slate-700/80 text-white hover:bg-slate-600 ' +
      'shadow-md focus:outline-none focus:ring-2 focus:ring-sky-500';
    _jumpBtn.innerHTML = '<span aria-hidden="true" class="text-lg">→</span>';
    _jumpBtn.title = 'En son çubuğa kaydır (Alt+Shift+→)';
    _jumpBtn.setAttribute('aria-label', 'En son çubuğa kaydır');
    _jumpBtn.addEventListener('click', () => jumpToLatest());
    // overlay için
    const s = getComputedStyle(chartEl);
    if (s.position === 'static') chartEl.style.position = 'relative';
    chartEl.appendChild(_jumpBtn);
    return _jumpBtn;
  }
  function updateJumpBtnVisibility() {
    const btn = ensureJumpBtn();
    if (!btn || !chart || !seriesLastTime) return;
    try {
      const r = chart.timeScale().getVisibleRange();
      // Son bar eşiği: aktif TF’e göre yarım bar payı bırak.
      const barSec = (TF_SEC[klTf] || 900);
      const pad = 0.5 * barSec;
      const show = !!(r && typeof r.to === 'number' && r.to < (seriesLastTime - pad));
      btn.classList.toggle('hidden', !show);
    } catch {}
  }

  function jumpToLatest() {
    if (!chart) return;
    chart.timeScale().scrollToRealTime();
    // Gerçek son bara kilitle ve görünürlüğü güncelle
    chart.timeScale().applyOptions({ rightOffset: 0 });
    chart.timeScale().scrollToRealTime();
    updateJumpBtnVisibility();
  }

  // Kısayol: Alt+Shift+Sağ ok
  window.addEventListener('keydown', (e) => {
    if (e.altKey && e.shiftKey && (e.key === 'ArrowRight' || e.code === 'ArrowRight')) {
      e.preventDefault();
      jumpToLatest();
    }
  });

  // ==== global durum ====
  let klTf = '15m';
  let klLimit = 1000;
  let seriesFirstTime = null;
  let seriesLastTime  = null; // grafikte en son barın zamanı (ghost sonrası kesin mevcut)
  let activeSymbol = null;
  // bar süresi (sn) tablosu
  const TF_SEC = { '1m':60, '5m':300, '15m':900, '1h':3600, '4h':14400, '1d':86400 };
  // Açık işlemin çizim politikası:
  // 'hybrid'   : canlı OPEN son mumda; kapanınca tarihsel OPEN + CLOSE görünür.
  // 'live-only': yalnız açıkken son mumda; kapanınca OPEN çizilmez (sadece CLOSE).
  // 'historical': her zaman tarihsel barında.
  const OPEN_MARKER_MODE = 'hybrid';

  // ==== i18n helpers ====
  // Kullanıcının tarayıcı diline göre sayı formatı
  const LOCALE = (navigator.languages && navigator.languages[0]) || navigator.language || 'en-US';
  const nf0 = new Intl.NumberFormat(LOCALE);
  const nf2 = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  // NOT: Yukarıda let olarak tanımlananlara burada atama yapıyoruz
  fmtNum = (v) => (v == null ? '—' : nf0.format(Number(v)));
  fmtPnl = (v) => {
    if (v == null) return '—';
    const n = Number(v); const sign = n >= 0 ? '+' : '-';
    return sign + nf2.format(Math.abs(n));
  };
  // ISO string timezone içermiyorsa UTC varsay; yerel + UTC beraber göster
  const parseIsoAsUtc = (s) => {
    if (!s) return null;
    const hasTZ = /[zZ]|[+-]\d{2}:\d{2}$/.test(s);
    return new Date(hasTZ ? s : s + 'Z');
  };
  const fmtDateLocalPlusUTC = (iso) => {
    if (!iso) return '—';
    const d = parseIsoAsUtc(iso);
    const local = d.toLocaleString(LOCALE);
    const utc   = new Intl.DateTimeFormat(LOCALE, { timeZone: 'UTC', dateStyle: 'short', timeStyle: 'medium' }).format(d);
    return `${local} · ${utc} UTC`;
  };

  // ==== market verisi ====
  async function loadKlines({ symbol = activeSymbol, tf = klTf, limit = klLimit } = {}) {
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
      if (series.length) {
        candle.setData(series);
        seriesFirstTime = series[0].time;
        const barSec = TF_SEC[tf] || 900;
        const last = series[series.length - 1];
        let lastTime = last?.time || null;
        const nowBar = Math.floor((Date.now() / 1000) / barSec) * barSec;
        if (last && last.time < nowBar) {
          const c = last.close;
          candle.update({ time: nowBar, open: c, high: c, low: c, close: c });
          lastTime = nowBar;
        }
        seriesLastTime = lastTime;
        updateJumpBtnVisibility();
      }
      const fs = document.getElementById('feed-status');
      if (fs) { fs.textContent = 'Bağlantı: açık'; fs.className = 'chip bg-emerald-50 dark:bg-emerald-900/20 border-emerald-300/50 text-emerald-700 dark:text-emerald-300'; }
      return series;
    } catch {
      const fs = document.getElementById('feed-status');
      if (fs) { fs.textContent = 'Bağlantı: kapalı'; fs.className = 'chip bg-slate-100 dark:bg-slate-800/60'; }
      return [];
    }
  }

  // ==== son sinyal hangi sembolde? ====
  async function getLatestMarkerSymbol() {
    try {
      const q = new URLSearchParams({ tf: klTf });
      const r = await fetch('/api/me/markers?' + q.toString(), { credentials: 'include' });
      if (!r.ok) return null;
      const items = await r.json();

      if (!Array.isArray(items) || !items.length) return null;
      // YALNIZCA HÂLÂ AÇIK pozisyonların OPEN marker'ını dikkate al (id'de ':' YOK).
      // Canlı OPEN yoksa, sembolü DEĞİŞTİRME (null dön).
    const liveOpens = items.filter(m =>
      String(m.kind).toLowerCase() === 'open' && m.is_live === true
    );
    if (!liveOpens.length) return null;
    const chosen = liveOpens.reduce(
      (a,b) => ((+(a.time_bar ?? a.time) || 0) > (+(b.time_bar ?? b.time) || 0) ? a : b)
    );
      return (String(chosen.symbol || '').toUpperCase().trim()) || null;

    } catch { return null; }
  }

  let _autoSwitchLock = false;
  async function autoSwitchSymbolIfNeeded() {
    if (_autoSwitchLock) return;
    _autoSwitchLock = true;
    try {
      const latestSym = await getLatestMarkerSymbol();
      if (latestSym && latestSym !== activeSymbol) {
        setActiveSymbol(latestSym);
        console.debug('[auto-switch] activeSymbol ->', latestSym);
      }
    } finally { _autoSwitchLock = false; }
  }

  // ==== markers ====
  async function loadMarkers({ symbols = [], since = null } = {}) {
    try {
      const params = new URLSearchParams();
      const list = symbols.length ? symbols : (activeSymbol ? [activeSymbol] : []);
      if (list.length) params.set('symbols', list.join(','));
      if (since) params.set('since', String(since));
      params.set('tf', klTf);

      const res = await fetch(`/api/me/markers?${params.toString()}`, { credentials: 'include' });
      if (!res.ok) throw new Error('markers api fail');
      /** @type {{symbol:string,time:number,position?:'aboveBar'|'belowBar',text:string,price?:number,id:string,kind:'open'|'close',side?:'long'|'short'}[]} */
      const items = await res.json();

      // aktif sembol filtresi (grafik tek sembol)
      const sym = (activeSymbol || '').toUpperCase().trim();
      const data = sym
        ? items.filter(m => String(m.symbol || '').toUpperCase().trim() === sym)
        : items;

      // Not: Eski sinyaller çok gerideyse klines'i genişletme.
      // Yalnızca görünür aralık içindeki marker'ları çizeceğiz.

      const out = [];
      for (const m of data) {
        const isClose = m.kind === 'close';
        const textU = String(m.text || '').toUpperCase();
        const sideU = String(m.side || (textU.includes('SHORT') ? 'SHORT' : (textU.includes('LONG') ? 'LONG' : ''))).toUpperCase();
        const isLong  = sideU === 'LONG';
        const pos = isClose
          ? (isLong ? 'aboveBar' : 'belowBar')
          : (m.position || (isLong ? 'belowBar' : 'aboveBar'));
        const txt   = isClose ? 'Close' : (isLong ? 'Long' : 'Short');
        const color = isLong ? '#10b981' : '#ef4444';
        const shape = isClose ? 'circle' : (isLong ? 'arrowUp' : 'arrowDown');
        // Zaman: backend TF'e göre normalize veriyor
        const whenBar = Number(m.time_bar ?? m.time);
        let   tOut    = whenBar;
        if (m.kind === 'open') {
          const isLive = m.is_live === true;
          if (OPEN_MARKER_MODE === 'live-only') {
            if (!isLive) continue; // kapanmış OPEN'ı hiç çizme
            tOut = (typeof seriesLastTime === 'number') ? seriesLastTime : whenBar;
          } else if (OPEN_MARKER_MODE === 'hybrid') {
            if (isLive) tOut = (typeof seriesLastTime === 'number') ? seriesLastTime : whenBar;
          } // 'historical' ise tOut=whenBar
        }
        const size = txt.length > 2 ? 1 : 2;
        const base = { time: tOut, position: pos, text: txt, color, shape, size };
        out.push(base);
      }

      // (Option A) Sadece görünür kline aralığındaki marker'ları çiz
      const from = (typeof seriesFirstTime === 'number') ? seriesFirstTime : -Infinity;
      const to   = (typeof seriesLastTime  === 'number') ? seriesLastTime  : +Infinity;
      const inRange = out.filter(m => m.time >= from && m.time <= to);
      candle.setMarkers(inRange);
      console.debug('[markers]', sym, 'inRange=', inRange.length, 'total=', out.length);
      return inRange;

    } catch (e) {
      console.error('loadMarkers failed', e);
      candle.setMarkers([]);
      return [];
    }
  }
  // konsoldan debug edebilmek için
  window.loadMarkers = loadMarkers;

  // ==== açık pozisyonlar (tüm semboller) ====
  async function loadOpenTrades() {
    try {
      const res = await fetch(`/api/me/open-trades`, { credentials: 'include' });
      if (!res.ok) throw new Error('api');
      const items = await res.json();
      const el = document.querySelector('#open-positions');
      if (!el) return items;
      if (!Array.isArray(items) || items.length === 0) { el.textContent = '—'; return []; }
      const rows = items.map(t => {
        const ts = fmtDateLocalPlusUTC(t.timestamp);
        return `
          <div class="grid grid-cols-6 gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40">
            <div class="col-span-2 font-medium">${t.symbol}</div>
            <div class="${t.side === 'long' ? 'text-emerald-500' : 'text-rose-400'}">${t.side.toUpperCase()}</div>
            <div>EP: ${fmtNum(t.entry_price)}</div>
            <div>Lev: ${t.leverage}x</div>
            <div class="text-xs text-slate-500">${ts}</div>
          </div>`;
      }).join('');
      el.innerHTML = `
        <div class="text-xs text-slate-500 mb-1 grid grid-cols-6 gap-2">
          <div class="col-span-2">Sembol</div><div>Yön</div><div>Fiyat</div><div>Kald.</div><div>Tarih</div>
        </div>
        <div>${rows}</div>`;
      return items;
    } catch {
      const el = document.querySelector('#open-positions');
      if (el) el.textContent = '—';
      return [];
    }
  }

  // ==== kapanan işlemler (tüm semboller) ====
  async function loadRecentTrades() {
    try {
      const res = await fetch(`/api/me/recent-trades?limit=50`, { credentials: 'include' });
      if (!res.ok) throw new Error('api');
      const items = await res.json();
      const el = document.querySelector('#recent-trades');
      if (!el) return items;
      if (!Array.isArray(items) || items.length === 0) { el.textContent = '—'; return []; }
      const rows = items.map(t => {
        const ts = fmtDateLocalPlusUTC(t.timestamp);
        const pnl = Number(t.realized_pnl);
        const pnlTxt = fmtPnl(pnl);
        const pnlCls = pnl >= 0 ? 'text-emerald-500' : 'text-rose-400';
        return `
          <div class="grid grid-cols-6 gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40">
            <div class="col-span-2 font-medium">${t.symbol}</div>
            <div class="${t.side === 'long' ? 'text-emerald-500' : 'text-rose-400'}">${t.side.toUpperCase()}</div>
            <div>EP: ${fmtNum(t.entry_price)}</div>
            <div>XP: ${fmtNum(t.exit_price)}</div>
            <div class="${pnlCls}">${pnlTxt}</div>
            <div class="text-xs text-slate-500">${ts}</div>
          </div>`;
      }).join('');
      el.innerHTML = `
        <div class="text-xs text-slate-500 mb-1 grid grid-cols-6 gap-2">
          <div class="col-span-2">Sembol</div><div>Yön</div><div>EP</div><div>XP</div><div>PnL</div><div>Tarih</div>
        </div>
        <div>${rows}</div>`;
      return items;
    } catch {
      const el = document.querySelector('#recent-trades');
      if (el) el.textContent = '—';
      return [];
    }
  }

  // ==== genel özet ====
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
      setText('#kpi-last', d.last_signal_at ? fmtDateLocalPlusUTC(d.last_signal_at) : '—');
    } catch {}
  }

  // ==== sembol yönetimi ====
  // BASE/QUOTE akıllı yazım (BTCUSDT, ETHFDUST, BTC/USDC, BTC-USD, …)
  function formatPair(sym) {
    const s = String(sym || '').toUpperCase().trim();
    if (!s) return '';
    if (s.includes('/') || s.includes('-') || s.includes('_')) return s.replace(/[-_]/g, '/');
    const QUOTES = ['FDUST','FDUSD','USDT','USDC','BUSD','TUSD','DAI','EUR','USD','TRY','BTC','ETH'];
    const q = QUOTES.find(q => s.endsWith(q));
    if (q) return `${s.slice(0, s.length - q.length)}/${q}`;
    return s.length > 4 ? `${s.slice(0, s.length - 4)}/${s.slice(-4)}` :
           s.length > 3 ? `${s.slice(0, 3)}/${s.slice(3)}` : s;
  }
  function updateSymbolLabel(sym) {
    const el = document.querySelector('#symbol-label');
    if (el && sym) el.textContent = formatPair(sym);
  }
  async function loadSymbols() {
    try { const r = await fetch('/api/me/symbols', { credentials: 'include' }); if (!r.ok) return []; const j = await r.json(); return Array.isArray(j.symbols) ? j.symbols : []; }
    catch { return []; }
  }
  function setActiveSymbol(sym) {
    activeSymbol = (sym || 'BTCUSDT').toUpperCase();
    updateSymbolLabel(activeSymbol);
    loadKlines({ symbol: activeSymbol }).then(() => loadMarkers({ symbols: [activeSymbol] }));
  }

  // ==== TF yönetimi ====
  // Aktif TF butonunu vurgulamak için yardımcı
  function highlightActiveTf(tf) {
    const btns = document.querySelectorAll('#tf-controls [data-tf]');
    btns.forEach(b => {
      if (b.getAttribute('data-tf') === tf) b.setAttribute('aria-current', 'true');
      else b.removeAttribute('aria-current');
    });
  }

  // Kullanıcı TF seçtiğinde: klTf güncellenir, seri temizlenir, klines+markers yeni TF ile yüklenir
  async function setTimeframe(tf) {
    if (!tf || tf === klTf) return;
    klTf = tf;
    klLimit = 1000;
    seriesFirstTime = null;
    highlightActiveTf(tf);
    await loadKlines({ symbol: activeSymbol, tf: klTf, limit: klLimit });
    await loadMarkers({ symbols: [activeSymbol] });
  }
  // HTML tarafında data-tf="1m|5m|15m|1h|4h|1d" butonlarını yakala
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-tf]');
    if (!btn) return;
    const tf = String(btn.dataset.tf || '').trim();
    setTimeframe(tf);
  });

  // ==== çalıştır ====
  // İlk açılışta mevcut TF’yi işaretle
  highlightActiveTf(klTf);
  makeChart();
  (async () => {
    const qp = new URLSearchParams(location.search);
    const fromUrl = qp.get('symbol');
    const known   = await loadSymbols();

    let initial = (fromUrl && fromUrl.toUpperCase()) || known[0] || 'BTCUSDT';
    if (!fromUrl) {
      const latest = await getLatestMarkerSymbol();
      if (latest) initial = latest;
    }

    activeSymbol = initial;
    updateSymbolLabel(activeSymbol);

    // await loadKlines({ symbol: activeSymbol });
    // await loadMarkers({ symbols: [activeSymbol] });
    // İlk yüklemede de son işaretçiye senkron ol
    await autoSwitchSymbolIfNeeded();
    await loadKlines({ symbol: activeSymbol });
    await loadMarkers({ symbols: [activeSymbol] });


    loadOpenTrades();      // tüm semboller
    loadRecentTrades();    // tüm semboller
    loadOverview();

    // periyodik
    // setInterval(() => { loadKlines({ symbol: activeSymbol }); loadMarkers({ symbols: [activeSymbol] }); }, 30000);
    // periyodik: HER turda önce auto-switch, sonra klines+markers
    setInterval(async () => {
      await autoSwitchSymbolIfNeeded();
      await loadKlines({ symbol: activeSymbol });
      await loadMarkers({ symbols: [activeSymbol] });
    }, 5000);

    setInterval(() => loadOpenTrades(), 10000);
    setInterval(() => loadRecentTrades(), 15000);
    // setInterval(autoSwitchSymbolIfNeeded, 10000); // son sinyale göre otomatik sembol değişimi
    // autoSwitch ayrı döngüde artık gereksiz (üstte entegre)
  })();
})();

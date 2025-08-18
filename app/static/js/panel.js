// app/static/js/panel.js — grafik/marker + otomatik sembol seçimli panel
(() => {
  // ==== build flags & timings ====
  const DEBUG = false;
  const REFRESH_MS       = 5000;
  const OPEN_TRADES_MS   = 10000;
  const RECENT_TRADES_MS = 15000;

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
    if (!chartEl) return; // chart DOM'u yoksa grafik kurulmaz
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

    // Sağ altta
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

  // Kısa, yerel tarih (saniyesiz; "GG.AA SS:DD")
  const fmtDateLocalShort = (rawTs) => {
    if (!rawTs) return '—';
    const ms = (typeof rawTs === 'number' && rawTs < 1e12) ? rawTs * 1000 : rawTs;
    const d = new Date(ms);
    return d.toLocaleString(LOCALE, { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
  };
  // ==== market verisi ====
  async function loadKlines({ symbol = activeSymbol, tf = klTf, limit = klLimit } = {}) {
    try {
      if (!candle) return []; // grafik kurulmadıysa sessizce çık
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
        // Sadece state ve etiketi güncelle; fetch işlemi caller döngüde yapılır
        activeSymbol = latestSym;
        updateSymbolLabel(activeSymbol);
        if (DEBUG) console.debug('[auto-switch] activeSymbol ->', latestSym);
      }
    } finally { _autoSwitchLock = false; }
  }

  // ==== markers ====
  async function loadMarkers({ symbols = [], since = null } = {}) {
    try {
      if (!candle) return []; // grafik yoksa marker çizme
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
      if (candle) candle.setMarkers(inRange);
      if (DEBUG) console.debug('[markers]', sym, 'inRange=', inRange.length, 'total=', out.length);
      return inRange;

    } catch (e) {
      console.error('loadMarkers failed', e);
      if (candle) candle.setMarkers([]);
      return [];
    }
  }
  // konsoldan debug edebilmek için
  if (DEBUG) window.loadMarkers = loadMarkers;

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
        // EP/XP: null/boş/0 gelirse "—" göster (0 kapanış gibi görünmesin)
        const fmtMaybePrice = (v) => {
          if (v == null || v === '') return '—';
          const n = Number(v);
          return (Number.isFinite(n) && n > 0) ? nf2.format(n) : '—';
        };
        return `
          <div class="grid grid-cols-6 gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40">
            <div class="col-span-2 font-medium">${t.symbol}</div>
            <div class="${t.side === 'long' ? 'text-emerald-500' : 'text-rose-400'}">${t.side.toUpperCase()}</div>
            <div>EP: ${fmtMaybePrice(t.entry_price)}</div>
            <div>XP: ${fmtMaybePrice(t.exit_price)}</div>
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
  // (legacy formatPair tahmini) kaldırıldı; sembol backend'den geldiği gibi gösteriliyor.
  function formatPair(sym) { return String(sym ?? ''); }

  function updateSymbolLabel(sym) {
    const el = document.querySelector('#symbol-label');
//    if (el && sym) el.textContent = formatPair(sym);
    if (el) el.textContent = formatPair(sym);
  }
  async function loadSymbols() {
    try { const r = await fetch('/api/me/symbols', { credentials: 'include' }); if (!r.ok) return []; const j = await r.json(); return Array.isArray(j.symbols) ? j.symbols : []; }
    catch { return []; }
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
    }, REFRESH_MS);

    setInterval(() => loadOpenTrades(),  OPEN_TRADES_MS);
    setInterval(() => loadRecentTrades(), RECENT_TRADES_MS);
  })();

  // ===== HIZLI BAKİYE ÖZETİ =====
  (function wireQuickBalance(){
    // Kart yalnız Asil'de HTML'a basılıyor; bu yüzden sadece DOM varlığına bakmak yeterli.
    const elWallet = document.getElementById('qb-wallet');
    const elNet    = document.getElementById('qb-net');
    const elOpen = document.getElementById('qb-open');
    const elLast = document.getElementById('qb-last');
    const btnRef = document.getElementById('qb-refresh');
    const a11y   = document.getElementById('qb-a11y');
    const statusEl = document.getElementById('qb-status');
    if (!elNet || !elOpen || !elLast) return;

    // --- status helper: tek yerden yönet ---
    let _qbHideTimer = null;
    function showStatus(text, tone /* 'info'|'ok'|'err' */){
      if (!statusEl) return;
      // metin
      statusEl.textContent = text || '';
      // tüm olası ton ve opaklık sınıflarını sıfırla
      statusEl.classList.remove('text-sky-500','text-emerald-500','text-rose-500','opacity-0','opacity-100');
      // yeni tonu ver + görünür yap
      const toneCls = tone === 'ok' ? 'text-emerald-500'
                      : tone === 'err' ? 'text-rose-500'
                      : 'text-sky-500';
      statusEl.classList.add(toneCls,'opacity-100');
      // önceki gizleme zamanlayıcısını iptal et
      if (_qbHideTimer) { clearTimeout(_qbHideTimer); _qbHideTimer = null; }
      // kısa süre sonra şeffaflaştır (butonu itmeden çünkü width sabit)
      const delay = tone === 'ok' ? 1200 : (tone === 'err' ? 1800 : 0);
      if (delay > 0) {
        _qbHideTimer = setTimeout(() => {
          statusEl.classList.remove('opacity-100');
          statusEl.classList.add('opacity-0');
          _qbHideTimer = null;
        }, delay);
      }
    }

    const nf2 = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const fmt2 = (v) => nf2.format(v || 0);
    const safeNum = (v) => {
      if (v == null || v === '' || Number.isNaN(+v)) return 0;
      return +v;
    };
    // Öncelikli alan: realized_pnl; diğer isimler olursa temkinli fallback
    const pickPnl = (t) => (
      t?.realized_pnl ??
      t?.realized_pnl_usd ??
      t?.pnl_usdt ??
      t?.pnl ??
      0
    );

    async function loadQuickBalance(){
      try {
        // durum: yenileniyor
        showStatus('Yenileniyor…','info');
        // Başlangıç değerleri: boş kalmasın
        elNet.textContent = '0'; elOpen.textContent = '0'; elLast.textContent = '—';
        // 1) Kapanan işlemler -> toplam net PnL ve son işlem
        let net = 0, lastText = '—';
        try {
          const r = await fetch('/api/me/recent-trades?limit=100', { credentials: 'include', headers:{'Accept':'application/json'} });
          if (r.ok) {
            const arr = await r.json();
            if (Array.isArray(arr) && arr.length) {
              for (const t of arr) net += safeNum(pickPnl(t));
              const last = arr[0];
              const side = (last?.side || '').toString().toUpperCase();
              const sym  = last?.symbol || '';
              const lpnl = safeNum(pickPnl(last));
              const sign = lpnl >= 0 ? '+' : '';
              // Tarih: kısa/yerel göster
              const ts   = fmtDateLocalShort(last?.timestamp);
              lastText = `${sym} ${side} · ${sign}${fmt2(lpnl)} · ${ts}`;
            }
          }
        } catch {}

        // 2) Açık pozisyon sayısı
        let openCnt = 0;
        try {
          const r2 = await fetch('/api/me/open-trades', { credentials: 'include', headers:{'Accept':'application/json'} });
          if (r2.ok) {
            const arr2 = await r2.json();
            if (Array.isArray(arr2)) openCnt = arr2.length;
          }
        } catch {}

        elNet.textContent  = (net === 0 ? '0' : (net > 0 ? '+' : '−') + fmt2(Math.abs(net)));
        elOpen.textContent = String(openCnt);
        elLast.textContent = lastText;

        // Net PnL Renk: + yeşil / - kırmızı
        elNet.classList.remove('text-emerald-500','text-rose-400');
        if (net > 0) elNet.classList.add('text-emerald-500');
        else if (net < 0) elNet.classList.add('text-rose-400');

        // Cüzdan = START_CAPITAL + net
        if (elWallet) {
          const START_CAP = (typeof window.START_CAPITAL === 'number') ? window.START_CAPITAL : 1000;
          const wallet = START_CAP + net;
          elWallet.textContent = fmt2(wallet);
          // Cüzdan rengi: başlangıç üstü/altı
          elWallet.classList.remove('text-emerald-500','text-rose-400');
          if (wallet > START_CAP) elWallet.classList.add('text-emerald-500');
          else if (wallet < START_CAP) elWallet.classList.add('text-rose-400');
        }
        // a11y: güncellendi bilgisi
        if (a11y) a11y.textContent = 'Hızlı bakiye özeti güncellendi.';
        // durum: yenilendi (kısa süre göster)
        showStatus('Yenilendi','ok');
      } catch {
        // sessiz
        showStatus('Hata','err');
      }
    }

    btnRef?.addEventListener('click', (e) => {
      e.preventDefault();
      if (a11y) a11y.textContent = 'Yenileniyor…';
      loadQuickBalance();
    });
    // ilk yükleme
    loadQuickBalance();
  })();

  // ==== Referans Kodu Modalı (frontend) ====
  (function wireReferralModal(){
    const btnOpen  = document.getElementById('open-referral');
    const modal    = document.getElementById('ref-modal');
    const form     = document.getElementById('ref-form');
    const input    = document.getElementById('ref-code');
    const btnCancel= document.getElementById('ref-cancel');
    const msg      = document.getElementById('ref-msg');
    if (!btnOpen || !modal || !form || !input) return;

    // ok=true: başarı, ok=false: hata, ok=null: nötr bilgi
    function setMsg(t, ok = null){
      if (!msg) return;
      // erişilebilirlik
      if (!msg.hasAttribute('role')) {
        msg.setAttribute('role','status');
        msg.setAttribute('aria-live','polite');
      }
      if (!t) {                 // boş mesaj: tamamen gizle
        msg.textContent = '';
        msg.className = 'hidden';
        return;
      }
      msg.textContent = t;
      const base = 'text-sm mt-2 px-2 py-1 rounded border font-medium tracking-wide ';
      // light: koyu metin + açık arka plan, dark: açık metin + yarı saydam arka plan
      let tone = 'text-sky-700 bg-sky-50 border-sky-200 dark:text-sky-200 dark:bg-sky-500/15 dark:border-sky-300/40';   // nötr
      if (ok === true)  tone = 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-200 dark:bg-emerald-500/15 dark:border-emerald-300/40';
      if (ok === false) tone = 'text-rose-700 bg-rose-50 border-rose-200 dark:text-rose-200 dark:bg-rose-500/20 dark:border-rose-300/40';
      msg.className = base + tone;
    }

    const extractErrText = (d, status) => {
      try {
        if (!d) return `Hata ${status}`;
        if (typeof d === 'string') return d;
        if (typeof d.detail === 'string') return d.detail;
        if (Array.isArray(d.detail)) {
          const items = d.detail.map(e => e.msg || e.message || e.type).filter(Boolean);
          if (items.length) return items.join(' • ');
        }
        if (typeof d.message === 'string') return d.message;
        const s = JSON.stringify(d); // kontrollü kısalt
        return s.length > 160 ? s.slice(0,157) + '…' : s;
      } catch { return `Hata ${status}`; }
    };

    btnOpen.addEventListener('click', () => {
      setMsg('');                      // açılışta mesaj gizli
      input.value = '';
      if (modal.showModal) modal.showModal(); else modal.style.display = 'block';
      setTimeout(()=>input.focus(), 30);
    });
    btnCancel?.addEventListener('click', () => {
      setMsg('');                      // kapatırken de gizle
      if (modal.close) modal.close(); else modal.style.display = 'none';
    });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const code = (input.value || '').trim().toUpperCase();
      if (!code) { setMsg('Kod boş olamaz', false); return; }
      // İstemci tarafı biçim kontrolü (backend de aynı regex ile doğruluyor)
      if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) {
        setMsg('Kod formatı geçersiz. Örn: AB12-CDEF-3456', false);
        return;
      }
     try {
        setMsg('Doğrulanıyor…', null); // nötr ton
        const r = await fetch('/referral/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ code })
        });
        if (!r.ok) {
          let d=null; try { d = await r.json(); } catch {}
          throw new Error(extractErrText(d, r.status));
        }
        setMsg('Başarılı. Yenileniyor…', true);
        setTimeout(()=>location.reload(), 600);
      } catch (err) {
        setMsg(err?.message || 'Doğrulama başarısız', false);
      }
    });
  })();
})();

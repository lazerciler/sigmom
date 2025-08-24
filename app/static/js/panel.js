// app/static/js/panel.js
(() => {
  // ==== build flags & timings ====
  const DEBUG = false;
  const REFRESH_MS       = 5000;
  const OPEN_TRADES_MS   = 10000;
  const RECENT_TRADES_MS = 15000;
  const RECENT_TRADES_LIMIT = 50;
  const DEFAULT_SYMBOL = 'BTCUSDT';
  let usedFallbackSymbol = false;

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

// --- tarih yardımcıları ---
function parseTs(v){
  if (v == null || v === '') return null;
  if (typeof v === 'number') return v < 1e12 ? v * 1000 : v;   // saniye→ms
  const s = String(v).trim();

  // "YYYY-MM-DD HH:MM:SS" → UTC kabul et
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})$/);
  if (m) return Date.parse(`${m[1]}T${m[2]}Z`);

  // 10/13 haneli epoch
  if (/^\d{10}$/.test(s)) return Number(s) * 1000;
  if (/^\d{13}$/.test(s)) return Number(s);

  // Diğer ISO tarihleri
  const d = new Date(s);
  return isNaN(d) ? null : d.getTime();
}

// Kapanış zamanını seç (önce 'timestamp', sonra diğerleri)
function pickTradeCloseTs(t){
  const keys = [
    'timestamp',          // DB kapaniş saati (öncelik)
    'closed_at','exit_at','exit_time','closedAt',
    'executed_at','time'  // alternatif alanlar
  ];
  for (const k of keys){
    const ts = parseTs(t?.[k]);
    if (ts) return ts;
  }
  return Date.now();
}

function ensureDefaultNoticeEl() {
  let el = document.getElementById('default-note');
  if (!el) {
    el = document.createElement('div');
    el.id = 'default-note';
    el.className = 'chip bg-sky-50 border border-sky-200 text-sky-700 ' +
                   'dark:bg-sky-500/15 dark:border-sky-300/40 dark:text-sky-200 hidden';
    // Feed durum çipinin yakınına koy (yoksa chart üstüne)
    const anchor = document.getElementById('feed-status') || document.getElementById('chart');
    (anchor?.parentElement || document.body).insertBefore(el, anchor || null);
  }
  return el;
}

function showDefaultNotice(sym) {
  const el = ensureDefaultNoticeEl();
  el.textContent =  `Henüz sinyal yok`; // `Henüz sinyal yok: ${sym}`;
  el.classList.remove('hidden');
}
function hideDefaultNotice() {
  const el = document.getElementById('default-note');
  if (el) el.classList.add('hidden');
}


// === MA overlay katmanları ===
const MA = {}; // { key: LineSeries }

const PALETTE = {
  dark:  ['#38bdf8', '#a78bfa', '#f59e0b', '#34d399', '#f472b6'],
  light: ['#0284c7', '#7c3aed', '#b45309', '#059669', '#db2777'],
};
const MA_COLOR_BY_KEY = {}; // { 'SMA7': '#...', ... }

// Renk indeksini cache'le: tema değişse de aynı sıradaki renk eşlensin
const MA_COLOR_IDX = {}; // { 'SMA7': 0, 'EMA99': 2, ... }
function pickColor(key, idx, dark) {
  const pal = dark ? PALETTE.dark : PALETTE.light;
  const i = (MA_COLOR_IDX[key] ??= idx % pal.length);
  return pal[i];
}

function ensureLine(key, idx) {
  const color = pickColor(key, idx, isDark());
  if (!MA[key]) {
    MA[key] = chart.addLineSeries({
      color,
      lineWidth: 1.2,
      priceScaleId: 'right',
      lastValueVisible: false,      // değer etiketi yok
      priceLineVisible: false,      // ← MA’larda track price kapalı
      crosshairMarkerVisible: true,
    });
  } else {
    MA[key].applyOptions({ color, priceLineVisible: false });
  }
  return MA[key];
}

function recolorMAs(dark) {
  const keys = Object.keys(MA);
  keys.forEach((k, i) => {
    const c = pickColor(k, i, dark);  // cache’i günceller
    MA[k]?.applyOptions({ color: c });
  });
}

// Basit hareketli ortalama
function sma(values, period) {
  const out = Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// Üssel hareketli ortalama
function ema(values, period) {
  const out = Array(values.length).fill(null);
  const k = 2 / (period + 1);
  let prev = null;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (i === period - 1) {
      // ilk EMA'yı SMA ile başlat
      let s = 0; for (let j = 0; j < period; j++) s += values[j];
      prev = s / period;
      out[i] = prev;
    } else if (i >= period) {
      prev = v * k + prev * (1 - k);
      out[i] = prev;
    }
  }
  return out;
}

// Candlestick datasından MA serileri üret
function buildMAData(klSeries, arrValues) {
  const times = klSeries.map(b => b.time);
  return arrValues.map((v, i) => (v == null ? null : { time: times[i], value: v })).filter(Boolean);
}

function updateMAOverlays(klSeries, config = { sma: [20], ema: [] }) {
  const closes = klSeries.map(b => b.close);
  const keys = [
    ...(config.sma || []).map(p => `SMA${p}`),
    ...(config.ema || []).map(p => `EMA${p}`),
  ];
  keys.forEach((key, idx) => {
    const p = Number(key.replace(/^\D+/,''));
    const arr = key.startsWith('SMA') ? sma(closes, p) : ema(closes, p);
    ensureLine(key, idx).setData(buildMAData(klSeries, arr));
  });
}

// Varsayılan katmanlar (istediğin gibi değiştir)
const MA_CONFIG = { sma: [7, 25], ema: [99] }; // SMA20 mavi-yeşil ton, SMA50 mor ton
// Gizlemek istenirse:
// MA['SMA20']?.setData([]);  MA['EMA50']?.setData([]);

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
      upColor: '#16a34a',
      downColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
      borderVisible: false,
      priceLineVisible: true,
    });
    applyChartTheme(isDark());
    new ResizeObserver(() => chart?.timeScale().fitContent()).observe(chartEl);
    // chart kurulumu tamamlanınca
    // ensureJumpBtn();
    // chart.timeScale().subscribeVisibleTimeRangeChange(updateJumpBtnVisibility);
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
    recolorMAs(dark);
  }

//  // ==== "En son çubuğa kaydır" butonu ====
//  let _jumpBtn = null;
//  function ensureJumpBtn() {
//    if (_jumpBtn || !chartEl) return _jumpBtn;
//    _jumpBtn = document.createElement('button');
//    _jumpBtn.id = 'jump-latest';
//    _jumpBtn.type = 'button';
//
//    // Sağ altta
//    _jumpBtn.className =
//      'hidden absolute right-3 bottom-3 z-10 ' +
//      'h-8 w-8 grid place-items-center rounded-md ' +
//      'bg-slate-700/80 text-white hover:bg-slate-600 ' +
//      'shadow-md focus:outline-none focus:ring-2 focus:ring-sky-500';
//    _jumpBtn.innerHTML = '<span aria-hidden="true" class="text-lg">→</span>';
//    _jumpBtn.title = 'En son çubuğa kaydır (Alt+Shift+→)';
//    _jumpBtn.setAttribute('aria-label', 'En son çubuğa kaydır');
//    _jumpBtn.addEventListener('click', () => jumpToLatest());
//    // overlay için
//    const s = getComputedStyle(chartEl);
//    if (s.position === 'static') chartEl.style.position = 'relative';
//    chartEl.appendChild(_jumpBtn);
//    return _jumpBtn;
//  }
//  function updateJumpBtnVisibility() {
//    const btn = ensureJumpBtn();
//    if (!btn || !chart || !seriesLastTime) return;
//    try {
//      const r = chart.timeScale().getVisibleRange();
//      // Son bar eşiği: aktif TF’e göre yarım bar payı bırak.
//      const barSec = (TF_SEC[klTf] || 900);
//      const pad = 0.5 * barSec;
//      const show = !!(r && typeof r.to === 'number' && r.to < (seriesLastTime - pad));
//      btn.classList.toggle('hidden', !show);
//    } catch {}
//  }
//
//  function jumpToLatest() {
//    if (!chart) return;
//    chart.timeScale().scrollToRealTime();
//    // Gerçek son bara kilitle ve görünürlüğü güncelle
//    chart.timeScale().applyOptions({ rightOffset: 0 });
//    chart.timeScale().scrollToRealTime();
//    updateJumpBtnVisibility();
//  }
//
//  // Kısayol: Alt+Shift+Sağ ok
//  window.addEventListener('keydown', (e) => {
//    if (e.altKey && e.shiftKey && (e.key === 'ArrowRight' || e.code === 'ArrowRight')) {
//      e.preventDefault();
//      jumpToLatest();
//    }
//  });

  // ==== global durum ====
  let klTf = '15m';
  let klLimit = 1000;
  let seriesFirstTime = null;
  let seriesLastTime  = null; // grafikte en son barın zamanı (ghost sonrası kesin mevcut)
  let activeSymbol = null;
  let klTimes = [];            // seri bar zamanları (s)
  let klGridTimes = [];        // ilk→son bar arası TF adımlı grid

  const TF_SEC = { '1m':60, '5m':300, '15m':900, '1h':3600, '4h':14400, '1d':86400 };

async function bootstrapActiveSymbol() {
  // 1) Açık pozisyonlardan seç
  try {
    const r = await fetch('/api/me/open-trades', { credentials: 'include', headers: { 'Accept': 'application/json' } });
    if (r.ok) {
      const items = await r.json();
      if (Array.isArray(items) && items.length) {
        const sym = String(items[0]?.symbol || '').toUpperCase();
        if (sym) { activeSymbol = sym; return sym; }
      }
    }
  } catch {}
  // 2) Son işlemden seç
  try {
    const r2 = await fetch('/api/me/recent-trades?limit=1', { credentials: 'include', headers: { 'Accept': 'application/json' } });
    if (r2.ok) {
      const arr = await r2.json();
      const t = Array.isArray(arr) ? arr[0] : (arr && arr[0]);
      const sym = t?.symbol ? String(t.symbol).toUpperCase() : '';
      if (sym) { activeSymbol = sym; return sym; }
    }
  } catch {}
  // 3) UI seçicisinden (yoksa geçici)
  const el = document.querySelector('[data-symbol-picker]');
  activeSymbol = (el?.value ? String(el.value).toUpperCase() : '');

    if (!activeSymbol) {
      activeSymbol = DEFAULT_SYMBOL;
      usedFallbackSymbol = true;
      updateSymbolLabel(activeSymbol);
      showDefaultNotice(activeSymbol);
      // tooltip: çip üzerine sembol bilgisini koy
      const note = document.getElementById('default-note');
      if (note) note.title = `Öntanımlı sembol: ${activeSymbol}`;
    }
  return activeSymbol;
 }

  // Verilen ts (s/ms) → grafiğin bar grid'ine snap (<= ts olan en yakın bar başlangıcı)
  function snapToSeries(ts){
    const tfSec = TF_SEC[klTf] || 60;
    const v = Number(ts);
    const sec = v < 1e12 ? v : Math.floor(v / 1000);
    const times = (klGridTimes && klGridTimes.length) ? klGridTimes : klTimes;
    if (times && times.length){
      let lo=0, hi=times.length;           // upperBound
      while (lo < hi){ const mid=(lo+hi)>>1; (times[mid] <= sec) ? (lo=mid+1) : (hi=mid); }
      const idx = Math.max(0, lo-1);
      return times[idx];
    }
    return Math.floor(sec / tfSec) * tfSec;
  }

  // i18n — tarayıcı dilini erkenden al (makeChart içinde kullanılıyor)
  const LOCALE = (navigator.languages && navigator.languages[0]) || navigator.language || 'en-US';

  // ==== i18n helpers ====
  // Kullanıcının tarayıcı diline göre sayı formatı
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
  // * ISO string timezone içermiyorsa UTC varsay; borsa tarafında TEK saat: UTC
  const parseIsoAsUtc = (s) => {
    if (!s) return null;
    const hasTZ = /[zZ]|[+-]\d{2}:\d{2}$/.test(s);
    return new Date(hasTZ ? s : s + 'Z');
  };

  // * Borsa tarafı: her zaman UTC göster
  const fmtDateLocalPlusUTC = (iso) => {
    if (!iso) return '—';
    const d = parseIsoAsUtc(iso);
    const utc = new Intl.DateTimeFormat(LOCALE, {
      timeZone: 'UTC',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    }).format(d);
    return `${utc} UTC`;
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
     // Boş sembolde API'yi hiç çağırma → 422 spam durur
     if (!symbol) {
       const fs = document.getElementById('feed-status');
       if (fs) {
         fs.textContent = 'Bağlantı: beklemede';
         fs.className = 'chip bg-slate-100 dark:bg-slate-800/60';
        }
        return [];
      }
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
        klTimes = series.map(s => s.time);   // seriden gelen bar zamanları

        // Grafik verisini bas
        candle.setData(series);
        // MA overlay: kapanmış barlar üzerinden hesapla (son bar hariç → daha stabil)
        if (series.length > 1) {
          updateMAOverlays(series.slice(0, -1), MA_CONFIG);
        } else {
          try { Object.values(MA).forEach(s => s.setData([])); } catch {}
        }

        // Zaman/grid hesapları
        seriesFirstTime = series[0].time;

        const barSec = TF_SEC[tf] || 900;
        seriesLastTime = series[series.length - 1].time;
        // (varsa ghost/son bar güncellemesi burada yapılıyor)
        // seriesLastTime kesinleştikten sonra grid’i üret:
        klGridTimes = [];
        for (let t = seriesFirstTime; t <= seriesLastTime; t += barSec) klGridTimes.push(t);
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

// * Borsa tarafı: her zaman UTC göster (ISO ya da epoch kabul et)
const fmtDateUTC = (ts) => {
  if (ts == null) return '—';
  const ms = (typeof ts === 'number') ? ts : parseTs(ts); // ISO → ms
  const d  = new Date(ms);
  const yyyy = String(d.getUTCFullYear());
  const mm   = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd   = String(d.getUTCDate()).padStart(2, '0');
  const hh   = String(d.getUTCHours()).padStart(2, '0');
  const mi   = String(d.getUTCMinutes()).padStart(2, '0');
  const ss   = String(d.getUTCSeconds()).padStart(2, '0');
  return `${dd}.${mm}.${yyyy} ${hh}:${mi}:${ss} UTC`;
};

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
    const liveOpens = items.filter(m => {
      const kind   = String(m.kind || '').toLowerCase();
      const status = String(m.status || '').toLowerCase();
      const isLive = (m.is_live === true || m.is_live === 1 || m.is_live === '1' || status === 'open');
      return kind === 'open' && isLive;
    });
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

      if (latestSym) {
        // Sembol değişmişse güncelle; DEĞİŞMEDİYSE de canlı open var demektir → çipi gizle
        if (latestSym !== activeSymbol) {
          activeSymbol = latestSym;
          updateSymbolLabel(activeSymbol);
        }
        usedFallbackSymbol = false;
        hideDefaultNotice();
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
    /** @type {{symbol:string,time:number,position?:'aboveBar'|'belowBar',text?:string,price?:number,id?:string,kind:'open'|'close',side?:'long'|'short',status?:string,is_live?:any}[]} */
    const items = await res.json();

    // aktif sembol filtresi (grafik tek sembol)
    const sym = (activeSymbol || '').toUpperCase().trim();
    const data = sym ? items.filter(m => String(m.symbol || '').toUpperCase().trim() === sym) : items;

    // CANLI open’ı bul (çeşitli API varyantlarına dayanıklı)
    let liveOpen = null;
    for (const m of data) {
      const kind   = String(m.kind || '').toLowerCase();
      if (kind !== 'open') continue;
      const status = String(m.status || '').toLowerCase();
      const isLive = (m.is_live === true || m.is_live === 1 || m.is_live === '1' || status === 'open');
      if (!isLive) continue;

      // yön: side öncelikli, yoksa metinden çıkar
      let sideU = String(m.side || '').toUpperCase();
      if (!sideU) {
        const tu = String(m.text || '').toUpperCase();
        if (tu.includes('LONG')) sideU = 'LONG';
        else if (tu.includes('SHORT')) sideU = 'SHORT';
      }
      if (!sideU) continue; // yön yoksa çizmeyelim (yanlış ok göstermeyelim)
      liveOpen = { isLong: sideU === 'LONG' };
      // (birden fazla canlı open varsa, sonuncusu üstüne yazar; sorun değil)
    }

    // Canlı OPEN bulunduysa fallback mesajını gizle
    if (liveOpen) {
      usedFallbackSymbol = false;
      hideDefaultNotice();
    }

    // Sadece tek bir işaret: CANLI yön oku (son bar üstünde)
    let markers = [];
    if (liveOpen && typeof seriesLastTime === 'number') {
      markers = [{
        time: seriesLastTime,
        position: liveOpen.isLong ? 'belowBar' : 'aboveBar', // Long: bar altı ↑, Short: bar üstü ↓
        text: liveOpen.isLong ? 'Long' : 'Short',
        color: liveOpen.isLong ? '#10b981' : '#ef4444',
        shape: liveOpen.isLong ? 'arrowUp' : 'arrowDown',
        size: 2
      }];
    }

    candle.setMarkers(markers);
    return markers;
  } catch (e) {
    if (DEBUG) console.error('loadMarkers failed', e);
    try { candle && candle.setMarkers([]); } catch {}
    return [];
  }
}
if (DEBUG) window.loadMarkers = loadMarkers;


//  // ==== Açık pozisyonlar ====
//  async function loadOpenTrades() {
//    try {
//      const res = await fetch(`/api/me/open-trades`, { credentials: 'include' });
//      if (!res.ok) throw new Error('api');
//      const items = await res.json();
//     // Equity modülüne haber ver
//     try { document.dispatchEvent(new CustomEvent('sig:open-trades', { detail: { items } })); } catch {}
//
//      const el = document.querySelector('#open-positions');
//      if (!el) return items;
//
//      if (!Array.isArray(items) || items.length === 0) { el.textContent = '—'; return []; }
//      // Güvenli DOM: header + satırlar
//      el.textContent = '';
//      const $div = (cls, text) => { const d=document.createElement('div'); if (cls) d.className=cls; if (text!=null) d.textContent=String(text); return d; };
//      const frag = document.createDocumentFragment();
//      // Header
//      const header = $div('text-xs text-slate-500 dark:text-slate-400 mb-1 grid grid-cols-6 gap-2');
//      header.append(
//        $div('col-span-2','Sembol'), $div('','Yön'), $div('','Fiyat'), $div('','Kaldıraç'), $div('','Tarih')
//      );
//      frag.append(header);
//      // Rows
//      const wrap = document.createElement('div');
//      items.forEach(t => {
//        const row = $div('grid grid-cols-6 gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40');
//        const ts = fmtDateLocalPlusUTC(t.timestamp); // borsa tarafında tek saat (UTC formatlı)
//        // const ts = fmtDateLocalShort(t.timestamp);   // tarayıcı yerel saati
//        const side = String(t.side||'').toLowerCase();
//        const sideCls = side === 'long' ? 'text-emerald-500' : 'text-rose-400';
//        row.append(
//          $div('col-span-2 font-medium', t.symbol),
//          $div(sideCls, side.toUpperCase()),
//          $div('', fmtNum(t.entry_price)),
//          $div('', `${t.leverage}x`),
//          // $div('text-xs text-slate-500', ts)
//          $div('text-xs text-slate-500 whitespace-nowrap', fmtDateUTC(t.timestamp))
//        );
//        wrap.appendChild(row);
//      });
//      frag.append(wrap);
//      el.appendChild(frag);
//      return items;
//    } catch {
//      const el = document.querySelector('#open-positions');
//      if (el) el.textContent = '—';
//      return [];
//    }
//  }

// ==== Açık pozisyonlar ====
async function loadOpenTrades() {
  try {
    const res = await fetch(`/api/me/open-trades`, { credentials: 'include' });
    if (!res.ok) throw new Error('api');
    const items = await res.json();

    // Equity modülüne haber ver
    try {
      document.dispatchEvent(new CustomEvent('sig:open-trades', { detail: { items } }));
    } catch {}

    const el = document.querySelector('#open-positions');
    if (!el) return items;

    if (!Array.isArray(items) || items.length === 0) {
      el.textContent = '—';
      return [];
    }

    // Güvenli DOM: header + satırlar
    el.textContent = '';
    const $div = (cls, text) => {
      const d = document.createElement('div');
      if (cls) d.className = cls;
      if (text != null) d.textContent = String(text);
      return d;
    };
    const frag = document.createDocumentFragment();

    // Header — sağ tablo ile aynı kolon düzeni
    const header = $div('text-xs text-slate-500 dark:text-slate-400 mb-1 grid gap-2');
    header.style.gridTemplateColumns = 'repeat(5,minmax(0,1fr))';
    header.append(
      $div('', 'Sembol'),
      $div('', 'Yön'),
      $div('', 'Fiyat'),
      $div('', 'Kaldıraç'),
      $div('', 'Tarih')
    );
    frag.append(header);

    // Rows — sağ tablo ile hizalı
    const wrap = document.createElement('div');
    items.forEach(t => {
      const row = $div('grid gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40');
      row.style.gridTemplateColumns = 'repeat(5,minmax(0,1fr))';

      const side = String(t.side || '').toUpperCase();
      const sideCls = side === 'LONG' ? 'text-emerald-500' : 'text-rose-400';

      row.append(
        $div('font-medium', t.symbol),
        $div(sideCls, side),
        $div('', fmtNum(t.entry_price)),
        $div('', `${t.leverage}x`),
        // Sağ tabloyla aynı: nowrap tarih (ellipsis/truncate yok)
        $div('text-xs text-slate-500 whitespace-nowrap', fmtDateUTC(t.timestamp))
      );

      wrap.appendChild(row);
    });

    frag.append(wrap);
    el.appendChild(frag);
    return items;
  } catch {
    const el = document.querySelector('#open-positions');
    if (el) el.textContent = '—';
    return [];
  }
}



// ==== Kapanan pozisyonlar ====
async function loadRecentTrades() {
  try {
    const res = await fetch(`/api/me/recent-trades?limit=${RECENT_TRADES_LIMIT}`, { credentials: 'include' });
    if (!res.ok) throw new Error('api');
    const items = await res.json();
    // Equity modülüne haber ver
    try { document.dispatchEvent(new CustomEvent('sig:recent-trades', { detail: { items } })); } catch {}
    const el = document.querySelector('#recent-trades');
    if (!el) return items;

    if (!items || !items.length) { el.textContent = '—'; return items; }

    const fmtMaybePrice = (v) => (v == null || v === '' ? '—' : nf2.format(Number(v)));

    // Güvenli DOM: header + satırlar
    el.textContent = '';
    const $div = (cls, text) => { const d=document.createElement('div');
    if (cls) d.className=cls;
    if (text!=null) d.textContent=String(text); return d; };
    const frag = document.createDocumentFragment();
    // Header
    const header = $div('text-xs text-slate-500 dark:text-slate-400 mb-1 grid gap-2');
    header.style.gridTemplateColumns = 'repeat(5,minmax(0,1fr))';
    header.append($div('','Sembol'), $div('','Yön'), $div('','Giriş Fiyatı'), $div('','Çıkış Fiyatı'), $div('','Tarih'));
    frag.append(header);
    // Rows
    const wrap = document.createElement('div');
    items.forEach(t => {
      const side = String(t.side || '').toUpperCase();
      const sideCls = side === 'LONG' ? 'text-emerald-500' : 'text-rose-400';
      const tsUTC = fmtDateUTC(pickTradeCloseTs(t));
      const row = $div('grid gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40');
      row.style.gridTemplateColumns = 'repeat(5,minmax(0,1fr))';
      const sym = $div('font-medium', t.symbol); sym.title = tsUTC;
      row.append(
        sym,
        $div(sideCls, side),
        $div('', fmtMaybePrice(t.entry_price)),
        $div('', fmtMaybePrice(t.exit_price)),
        // $div('text-xs text-slate-500', tsUTC),
        $div('text-xs text-slate-500 whitespace-nowrap', tsUTC)
      );
      wrap.appendChild(row);
    });
    frag.append(wrap);
    el.appendChild(frag);
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

      const setTitle = (sel, t) => { const el = document.querySelector(sel); if (el) el.title = t; };
      setTitle('#kpi-pnl',    'PnL (son 7 gün)');
      setTitle('#kpi-win',    'Kazanma Oranı (son 30 gün)');
      setTitle('#kpi-open',   'Şu anki açık pozisyon adedi');
      setTitle('#kpi-dd',     'Maksimum Düşüş (son 30 gün, peak→trough)');
      setTitle('#kpi-sharpe', 'Sharpe Oranı (son 30 gün, günlük getiriler)');
      setTitle('#kpi-last',   'Son sinyal zamanı (UTC)');
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
    // Öncelik: URL ?symbol= → açık poz./son işlem (bootstrapActiveSymbol) → canlı marker → bilinen liste → fallback
    const qp    = new URLSearchParams(location.search);
    const fromUrl = qp.get('symbol');
    const known   = await loadSymbols();
    const bootSym = await bootstrapActiveSymbol();     // /api/me/open-trades → /api/me/recent-trades → picker
    const latest  = await getLatestMarkerSymbol();     // canlı marker varsa
    let initial = (fromUrl && fromUrl.toUpperCase())
               || bootSym
               || latest
               || (known[0] || '');                   // sabit yok; bilinen listeden ya da boş
    activeSymbol = initial ? initial.toUpperCase() : '';
    updateSymbolLabel(activeSymbol || '—');
    // Hızlı Bakiye ilk çekimi için (activeSymbol hazır olduğunda) haber ver
    document.dispatchEvent(new Event('sig:active-ready'));
    if (usedFallbackSymbol) showDefaultNotice(activeSymbol);

    // İlk yüklemede de son işaretçiye senkron ol
    await autoSwitchSymbolIfNeeded();
    await loadKlines({ symbol: activeSymbol });
    await loadMarkers({ symbols: [activeSymbol] });

    loadOpenTrades();      // tüm semboller
    loadRecentTrades();    // tüm semboller
    loadOverview();

    setInterval(async () => {
      if (!activeSymbol) {               // sembol yoksa API çağırma
        await bootstrapActiveSymbol();   // arada bir yeniden deneyelim (hafif)
        return;
      }
      await autoSwitchSymbolIfNeeded();  // varsa canlı open başka sembole kayar
      await loadKlines({ symbol: activeSymbol, tf: klTf, limit: klLimit });
      await loadMarkers();
    }, REFRESH_MS);

    setInterval(() => loadOpenTrades(),  OPEN_TRADES_MS);
    setInterval(() => loadRecentTrades(), RECENT_TRADES_MS);
  })();

  // ===== HIZLI BAKİYE ÖZETİ =====
  (function wireQuickBalance(){
    // Kart yalnız Asil'de HTML'a basılıyor; bu yüzden sadece DOM varlığına bakmak yeterli.
    const elWallet = document.getElementById('qb-wallet');
    const elNet    = document.getElementById('qb-net');
    const elUp     = document.getElementById('qb-upnl');
    const elOpen = document.getElementById('qb-open');
    const elLast = document.getElementById('qb-last');
    const btnRef = document.getElementById('qb-refresh');
    const a11y   = document.getElementById('qb-a11y');
    const statusEl = document.getElementById('qb-status');
    if (!elNet || !elOpen || !elLast) return;

    let _qbHideTimer = null;
    function showStatus(text, tone){
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

    async function loadQuickBalance(opts) {
    const silent = !!(opts && opts.silent);
    // Aktif sembol henüz belirlenmediyse ilk yüklemeyi beklet
    if (!activeSymbol) return;
      try {
        // durum: yenileniyor
        if (!silent) showStatus('Yenileniyor…','info');
        // Başlangıç değerleri: boş kalmasın (yalnız manuelde göster)
        if (!silent) {
          elNet.textContent = '0'; elOpen.textContent = '0'; elLast.textContent = '—';
          if (elUp) elUp.textContent = '—';
        }
        // 1) Kapanan işlemler -> toplam net PnL ve son işlem
        let net = 0, lastText = '—';
        let lastView = null; // {sym, side, sign, lpnl, ts, pnlCls}
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
              const pnlCls = lpnl > 0 ? 'text-emerald-500'
                             : (lpnl < 0 ? 'text-rose-400' : 'text-slate-400');
              // dışarıda kullanmak için parçaları sakla
              lastView = { sym, side, sign, lpnl, ts, pnlCls };
              // fallback metin (veri yoksa kullanılacak)
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
        // Canlı PnL (uPnL): SADECE açık pozisyon varsa çağır
        if (elUp) {
          if (openCnt > 0) {
            let up = 0;
            try {
              const qs2 = new URLSearchParams({ symbol: String(activeSymbol).toUpperCase() });
              const rU  = await fetch('/api/me/unrealized?' + qs2.toString(), {
                credentials: 'include', headers: { 'Accept': 'application/json' }
              });
              if (rU.ok) {
                const ju = await rU.json();
                up = Number(ju?.unrealized ?? 0);
              }
            } catch {}
            elUp.classList.remove('text-emerald-500','text-rose-400');
            if (up > 0) elUp.classList.add('text-emerald-500');
            else if (up < 0) elUp.classList.add('text-rose-400');
            elUp.textContent = (up >= 0 ? '+' : '−') + nf2.format(Math.abs(up));
          } else {
            elUp.classList.remove('text-emerald-500','text-rose-400');
            elUp.textContent = '—';
          }
        }
        if (lastView) {
          elLast.textContent = ''; // temizle
          elLast.append(
            document.createTextNode(`${lastView.sym} ${lastView.side} · `),
            (() => {
              const s = document.createElement('span');
              s.className = lastView.pnlCls;
              s.textContent = `${lastView.sign}${fmt2(lastView.lpnl)}`;
              return s;
            })(),
            document.createTextNode(` · ${lastView.ts}`)
          );
        } else {
          elLast.textContent = lastText; // '—' veya fallback metin
        }

        // Net PnL Renk: + yeşil / - kırmızı
        elNet.classList.remove('text-emerald-500','text-rose-400');
        if (net > 0) elNet.classList.add('text-emerald-500');
        else if (net < 0) elNet.classList.add('text-rose-400');

        // Cüzdan: backend’den sembole göre (quote çıkarımı server’da)
        if (elWallet) {
          let shown = null;
          try {
            const qs = new URLSearchParams({ symbol: String(activeSymbol).toUpperCase() });
            const r  = await fetch('/api/me/balance?' + qs.toString(), {
              credentials: 'include', headers: { 'Accept': 'application/json' }
            });
            if (r.ok) {
              const j = await r.json();
              shown = Number(j?.available ?? j?.balance);
            }
          } catch {}
          // Fallback: API başarısızsa eski simülasyon mantığını kullan
          if (!Number.isFinite(shown)) {
            const START_CAP = (typeof window.START_CAPITAL === 'number') ? window.START_CAPITAL : 1000;
            shown = START_CAP + (Number(net) || 0);
            // simüle modda renk: başlangıcın üstü/altı
            elWallet.classList.remove('text-emerald-500','text-rose-400');
            if (shown > START_CAP) elWallet.classList.add('text-emerald-500');
            else if (shown < START_CAP) elWallet.classList.add('text-rose-400');
          } else {
            // gerçek bakiye → nötr renk
            elWallet.classList.remove('text-emerald-500','text-rose-400');
          }
          elWallet.textContent = fmt2(shown || 0);
        }
        // a11y: güncellendi bilgisi
        if (a11y) a11y.textContent = 'Hızlı bakiye özeti güncellendi.';
        // durum: yenilendi (kısa süre göster)
        if (!silent) showStatus('Yenilendi','ok');
      } catch {
        // sessiz
        if (!silent) showStatus('Hata','err');
      }
    }

    btnRef?.addEventListener('click', (e) => {
      e.preventDefault();
      if (a11y) a11y.textContent = 'Yenileniyor…';
      loadQuickBalance({ silent: false });  // manuel yenileme
    });
    // İlk yükleme: activeSymbol hazır değilse bekle
    if (activeSymbol) loadQuickBalance({ silent: true });
    else document.addEventListener('sig:active-ready', () => loadQuickBalance({ silent: true }), { once: true });
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

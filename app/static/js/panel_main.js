// app/static/js/panel_main.js
/*
  panel_main.js — Trading panel UI
  - Data feed & chart (Lightweight Charts)
  - Markers, MA overlays, MA Confluence (Chart.js)
  - Open/Recent trades, Quick Balance
  - Account mode chip (Hedge/One-way)
  Güvenlik: innerHTML YOK, sadece DOM API.
*/
(() => {
    const r = document.documentElement;
    window.TRADES_ALLOWED ??= (r.getAttribute('data-trades-allowed') === 'true');
    window.EQUITY_ALLOWED ??= (r.getAttribute('data-equity-allowed') === 'true');
})();

(() => {
    // ==== build flags & timings ====
    const DEBUG = false;
    const REFRESH_MS = Number(localStorage.getItem('REFRESH_MS') || 5000);
    const OPEN_TRADES_MS = 5000;
    const RECENT_TRADES_MS = 10000;
    const RECENT_TRADES_LIMIT = 50;
    const OPEN_TRADES_LIMIT = 50;
    const DEFAULT_SYMBOL = 'BTCUSDT';
    let usedFallbackSymbol = false;
    // Misafir: kullanıcı
    const GUEST = !window.TRADES_ALLOWED;
    // Son bilinen hesap modu (UI’da geçici boş dönüşlerde kaybolmayı önlemek için)
    let LAST_POSITION_MODE = null; // 'hedge' | 'one_way' | null

    // ==== Veri tazelik göstergesi ("Veri durumu") ====
    // Son başarılı kline çağrısı zamanı ve son hata zamanı (ms)
    let lastApiOkAt = 0;
    let lastApiErrAt = 0;
    const FRESH_AGE_MS = REFRESH_MS * 2; // eşikler REFRESH_MS’e göre
    const LAGGY_AGE_MS = REFRESH_MS * 6; // ~30 sn
    const STALE_AGE_MS = REFRESH_MS * 24; // ~2 dk
    // Feed chip state cache (animasyonu bozmamak ve gereksiz reflow’ları önlemek için)
    let FEED_STATE = null; // 'waiting' | 'ok' | 'warn' | 'stale' | 'err'

    // === Entry price çizgileri (LONG/SHORT) ===
    const ENTRY_LINE_STYLE = 'dashed'; // stil: 'dashed' veya 'solid'
    const ENTRY_OPTS = (side, price) => {
        const labelColor = side === 'short' ? '#ef4444' : '#10b981';
        return {
            price,
            color: labelColor, // çizgiyi gizlemiyoruz
            lineStyle: ENTRY_LINE_STYLE === 'dashed' ?
                LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
            lineWidth: 1,
            axisLabelVisible: true,
            axisLabelColor: labelColor,
            title: side === 'short' ? '↓' : '↑',
        };
    };

    let entryLines = {
        long: null,
        short: null
    }; // {side: PriceLineHandle|null}

    function setEntryLine(side, price) {
        if (!window.TRADES_ALLOWED || !candle) return;
        const s = (side || '').toLowerCase();
        if (s !== 'long' && s !== 'short') return;
        // eskisini kaldır
        try {
            entryLines[s] && candle.removePriceLine(entryLines[s]);
        } catch {}
        entryLines[s] = null;
        // yeni çiz
        if (Number.isFinite(price)) {
            entryLines[s] = candle.createPriceLine(ENTRY_OPTS(s, Number(price)));
        }
    }

    function updateEntryLines(map) { // { long?: number, short?: number }
        const wantLong = Number.isFinite(map?.long) ? Number(map.long) : null;
        const wantShort = Number.isFinite(map?.short) ? Number(map.short) : null;

        // Aynı/çok yakınsa küçük bir epsilon ile ayır
        if (wantLong != null && wantShort != null) {
            const base = Number.isFinite(wantLong) ? wantLong : wantShort;
            const decs = (() => {
                const s = String(base);
                const i = s.indexOf('.');
                return i === -1 ? 0 : Math.min(6, s.length - i - 1);
            })();
            const step = Math.pow(10, -decs) || 0.01;
            if (Math.abs(wantLong - wantShort) < step / 2) {
                // LONG'u yarım adım yukarı kaydır
                map.long = wantLong + step * 0.5;
            }
        }

        // >>> ÇİZİM İÇİN GÜNCELLENEN DEĞERLERİ KULLAN <<<
        const drawLong = Number.isFinite(map?.long) ? Number(map.long) : wantLong;
        const drawShort = Number.isFinite(map?.short) ? Number(map.short) : wantShort;

        // Long
        if (drawLong != null) setEntryLine('long', drawLong);
        else {
            try {
                entryLines.long && candle.removePriceLine(entryLines.long);
            } catch {}
            entryLines.long = null;
        }

        // Short
        if (drawShort != null) setEntryLine('short', drawShort);
        else {
            try {
                entryLines.short && candle.removePriceLine(entryLines.short);
            } catch {}
            entryLines.short = null;
        }
    }

    function clearEntryLines() {
        try {
            entryLines.long && candle.removePriceLine(entryLines.long);
        } catch {}
        try {
            entryLines.short && candle.removePriceLine(entryLines.short);
        } catch {}
        entryLines = {
            long: null,
            short: null
        };
    }
    // geriye dönük: tek çizgi temizleme çağrıları boşa düşmesin
    function clearEntryLine() {
        clearEntryLines();
    }

    // Tek noktadan render: durum değişmedikçe DOM'a dokunmaz (animasyon kesilmez)
    function renderFeedChip(state) {
        const el = document.getElementById('feed-status');
        if (!el) return;
        if (FEED_STATE === state) return; // aynı durum → no-op
        FEED_STATE = state;
        // Sınıf
        let cls = 'chip bg-slate-100 dark:bg-slate-800/60';
        if (state === 'ok')
            cls = 'chip bg-emerald-50 dark:bg-emerald-900/20 border-emerald-300/50 text-emerald-700 dark:text-emerald-300';
        else if (state === 'warn')
            cls = 'chip bg-amber-50 dark:bg-amber-900/20 border-amber-300/50 text-amber-700 dark:text-amber-300';
        else if (state === 'err')
            cls = 'chip bg-rose-50 dark:bg-rose-500/20 border-rose-200 text-rose-700 dark:text-rose-200';
        el.className = cls;
        // İçerik
        if (state === 'waiting') {
            // Loader node’u varsa koru, yoksa ekle
            let loader = el.querySelector('.loader');
            if (!loader) {
                // mevcut içeriği güvenle temizle
                while (el.firstChild) el.removeChild(el.firstChild);
                loader = document.createElement('div');
                loader.className = 'loader';
                el.appendChild(loader);
            }
            el.setAttribute('aria-label', 'Veri akışı: Bekleniyor');
            el.title = 'Veri akışı: Bekleniyor';
        } else {
            const label =
                state === 'ok' ? 'Stabil' :
                state === 'warn' ? 'Gecikmeli' :
                state === 'stale' ? 'Eski' : 'Kopuk';
            el.textContent = `Veri akışı: ${label}`;
            el.removeAttribute('aria-label');
            el.removeAttribute('title');
        }
    }

    // Eski çağrı imzasıyla uyumluluk (başka yerlerden text+tone gelebilir)
    function setFeedChip(text, tone) {
        const t = String(text || '').toLowerCase();
        let state;
        if (t === 'waiting' || t === 'bekleniyor' || t === '__loader__') state = 'waiting';
        else if (t === 'stabil' || tone === 'ok') state = 'ok';
        else if (t === 'gecikmeli' || tone === 'warn') state = 'warn';
        else if (t === 'eski') state = 'stale';
        else if (t === 'kopuk' || tone === 'err') state = 'err';
        else state = 'stale';
        renderFeedChip(state);
    }

    function updateFeedStatus() {
        const now = Date.now();

        if (!lastApiOkAt && !lastApiErrAt) {
            renderFeedChip('waiting');
            return;
        }
        // Başarılı son çağrıdan bu yana geçen süreye göre ton seç
        const age = now - lastApiOkAt;

        if (lastApiOkAt && age <= FRESH_AGE_MS) renderFeedChip('ok');
        else if (lastApiOkAt && age <= LAGGY_AGE_MS) renderFeedChip('warn');
        else if (lastApiOkAt && age <= STALE_AGE_MS) renderFeedChip('stale');
        else renderFeedChip('err');
    }

    // ==== helpers ====
    const $ = (sel) => document.querySelector(sel);
    const isDark = () => document.documentElement.classList.contains('dark');
    const setText = (sel, v) => {
        const el = $(sel);
        if (el) el.textContent = v;
    };
    const fmtPct = (v) => (v == null ? '—' : (Math.round(v * 10) / 10) + '%');
    let fmtNum = (v) => (v == null ? '—' : String(v));
    let fmtPnl = (v) => {
        if (v == null) return '—';
        const x = Number(v);
        return (x >= 0 ? '+' : '-') + Math.abs(x).toFixed(2);
    };

    function ensureModeChip() {
        const host = document.getElementById('data-disclaimer');
        if (!host) return null;
        let chip = document.getElementById('mode-chip');
        if (!chip) {
            chip = document.createElement('span');
            chip.id = 'mode-chip';
            chip.className = 'hidden inline-flex items-center gap-1 ml-2 px-1.5 py-0.5 rounded-md border border-slate-300/60 dark:border-slate-600/60 text-[10px] font-medium';
            host.appendChild(chip);
        }
        return chip;
    }

    function updateModeChip(mode) {
        // Pozisyon modu misafire görünmesin
        if (typeof GUEST !== 'undefined' && GUEST) return;
        const chip = ensureModeChip();
        if (!chip) return;
        const m = String(mode || LAST_POSITION_MODE || '').toLowerCase();
        // API arada null dönerse: mevcut görünümü KORU (gizleme!)
        if (m !== 'hedge' && m !== 'one_way') return;
        chip.classList.remove('hidden');
        // Host metninde "Pozisyon modu" zaten var mı?
        const host = document.getElementById('data-disclaimer');
        const hostTxt = (host?.textContent || '').toLowerCase();
        const needLabel = !hostTxt.includes('pozisyon modu');
        // İçeriği sıfırla ve gerektiği kadar etiket ekle
        while (chip.firstChild) chip.removeChild(chip.firstChild);
        if (needLabel) chip.append(document.createTextNode('Pozisyon modu: '));
        const strong = document.createElement('strong');
        strong.textContent = (m === 'hedge' ? 'Hedge' : 'One-way');
        chip.appendChild(strong);
        chip.setAttribute('aria-label', `Pozisyon modu: ${strong.textContent}`);
        chip.title = 'Pozisyon modu hesap seviyesinde geçerlidir ve güncel sinyale göre değişkenlik gösterebilir.';
    }

    // --- tarih yardımcıları ---
    function parseTs(v) {
        if (v == null || v === '') return null;
        if (typeof v === 'number') return v < 1e12 ? v * 1000 : v; // saniye→ms
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
    function pickTradeCloseTs(t) {
        const keys = [
            'timestamp', // DB kapaniş saati (öncelik)
            'closed_at', 'exit_at', 'exit_time', 'closedAt',
            'executed_at', 'time' // alternatif alanlar
        ];
        for (const k of keys) {
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
            const anchor = document.getElementById('feed-status') || document.getElementById('chart');
            (anchor?.parentElement || document.body).insertBefore(el, anchor || null);
        }
        return el;
    }

    function showDefaultNotice(sym) {
        const el = ensureDefaultNoticeEl();
        // Açık pozisyon varsa asla gösterme
        if (Array.isArray(OPEN_TRADES_CACHE) && OPEN_TRADES_CACHE.length > 0) {
            hideDefaultNotice();
            return;
        }
        el.textContent = `Sinyal bekleniyor...`;
        el.classList.remove('hidden');
    }

    function hideDefaultNotice() {
        const el = document.getElementById('default-note');
        if (el) el.classList.add('hidden');
    }

    // === MA overlay katmanları ===
    const MA = {};

    const PALETTE = {
        // Dark: daha doygun ama göz yormayan orta-açık tonlar
        dark: ['#93c5fd', '#c084fc', '#fbbf24', '#34d399', '#fb7185'], // blue-300, violet-300, amber-400, emerald-400, rose-400
        // Light: yüksek kontrast için 600 civarı canlı tonlar
        light: ['#2563eb', '#9333ea', '#f59e0b', '#059669', '#db2777'], // blue-600, purple-600, amber-500, emerald-600, rose-600
    };
    // not: key→renk cache'i MA_COLOR_IDX ile tutuluyor

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
                lastValueVisible: false, // değer etiketi yok
                priceLineVisible: false, // ← MA’larda track price kapalı
                crosshairMarkerVisible: true,
            });
        } else {
            MA[key].applyOptions({
                color,
                priceLineVisible: false
            });
        }
        return MA[key];
    }

    function recolorMAs(dark) {
        const keys = Object.keys(MA);
        keys.forEach((k, i) => {
            const c = pickColor(k, i, dark); // cache’i günceller
            MA[k]?.applyOptions({
                color: c
            });
        });
    }

    // === Polar (MA Konfluensi) ===
    let maChart = null; // singleton
    const POLAR_BG = {
        // MA 99, MA 25, MA 7
        light: ['rgba(251,191,36,0.50)', 'rgba(168,85,247,0.50)', 'rgba(59,130,246,0.50)'],
        dark: ['rgba(245,158,11,0.55)', 'rgba(147,51,234,0.55)', 'rgba(59,130,246,0.55)']
    };
    const POLAR_BORDER = (dark) => (dark ? '#0f172a' : '#e5e7eb');

    function ensureMaChart() {
        const el = document.getElementById('maConfluence') || document.getElementById('maConfChart');
        if (!el || !window.Chart) return null;
        // 1) Varsa aynısını kullan
        if (maChart && !maChart._destroyed) return maChart;
        const existing = (window.Chart.getChart ? window.Chart.getChart(el) : null);
        if (existing) {
            maChart = existing;
            return maChart;
        }
        // 2) Boyutu kilitle
        //    Varsa .ma-conf-wrap yüksekliğine sabitle, yoksa 166px kullan
        const wrap = el.closest('.ma-conf-wrap');
        el.style.width = '100%';
        if (!el.style.height) {
            const h = wrap ? wrap.clientHeight : 166;
            el.style.height = h + 'px';
        }
        // 3) Oluştur
        const dark = isDark();
        maChart = new Chart(el.getContext('2d'), {
            type: 'polarArea',
            data: {
                labels: ['7↔25', '25↔99', '7↔99'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: POLAR_BG[dark ? 'dark' : 'light'],
                    borderColor: POLAR_BORDER(dark),
                    borderWidth: 1.5,
                    hoverBackgroundColor: POLAR_BG[dark ? 'dark' : 'light']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                resizeDelay: 120,

                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: (c) => `${c.formattedValue}%`
                        }
                    }
                },
                scales: {
                    r: {
                        min: 0,
                        max: 100,
                        // 0–20–40–60–80–100
                        ticks: {
                            stepSize: 20,
                            color: dark ? '#94a3b8' : '#64748b',
                            backdropColor: 'transparent'
                        },
                        grid: {
                            color: dark ? 'rgba(148,163,184,.18)' : 'rgba(100,116,139,.22)'
                        },
                        angleLines: {
                            color: dark ? 'rgba(148,163,184,.22)' : 'rgba(100,116,139,.22)'
                        },
                        pointLabels: {
                            color: dark ? '#cbd5e1' : '#334155',
                            font: {
                                size: 11,
                                weight: '600'
                            }
                        }
                    }
                }
            }
        });
        return maChart;
    }

    function applyMaChartTheme(dark) {
        if (!maChart) return;
        const r = maChart.options.scales.r;
        r.ticks.color = dark ? '#cbd5e1' : '#334155';
        r.grid.color = dark ? 'rgba(148,163,184,.18)' : 'rgba(100,116,139,.22)';
        r.angleLines.color = dark ? 'rgba(148,163,184,.22)' : 'rgba(100,116,139,.22)';
        const ds = maChart.data?.datasets?.[0];
        if (ds) {
            ds.backgroundColor = POLAR_BG[dark ? 'dark' : 'light'];
            ds.hoverBackgroundColor = ds.backgroundColor;
            ds.borderColor = POLAR_BORDER(dark);
            ds.borderWidth = 1.5;
        }
        maChart.update('none');
    }
    const CONF_THRESH_PCT = 1.5; // diff fiyatın %1.5’i → 100 yakınlık

    function closenessPct(a, b, price, tol = CONF_THRESH_PCT) {
        if (!Number.isFinite(a) || !Number.isFinite(b) || !Number.isFinite(price) || price <= 0) return 0;
        const diffPct = Math.abs(a - b) / price * 100;
        return Math.max(0, Math.min(100, 100 * (1 - diffPct / tol)));
    }

    function updateMaConfluence(series) {
        const ch = ensureMaChart();
        if (!ch) return;
        if (!Array.isArray(series) || series.length < 2) {
            ch.data.datasets[0].data = [0, 0, 0];
            ch.update('none');
            return;
        }
        // Kapanmış son bar
        const idx = Math.max(0, series.length - 2);
        const closes = series.map(b => b.close);
        const sma7 = sma(closes, 7)[idx];
        const sma25 = sma(closes, 25)[idx];
        const ema99 = ema(closes, 99)[idx];
        const px = series[idx].close;
        const d1 = closenessPct(sma7, sma25, px);
        const d2 = closenessPct(sma25, ema99, px);
        const d3 = closenessPct(sma7, ema99, px);
        ch.data.datasets[0].data = [d1, d2, d3].map(v => Math.round(v)); // tam sayıya yuvarla
        // Sabit şeffaf renkler
        const dark = isDark();
        ch.data.datasets[0].backgroundColor = POLAR_BG[dark ? 'dark' : 'light'];
        ch.data.datasets[0].hoverBackgroundColor = ch.data.datasets[0].backgroundColor;
        ch.data.datasets[0].borderColor = POLAR_BORDER(dark);
        ch.data.datasets[0].borderWidth = 1.5;
        ch.update('none');
    }
    // --------------------------------------------------------------

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
                let s = 0;
                for (let j = 0; j < period; j++) s += values[j];
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
        return arrValues.map((v, i) => (v == null ? null : {
            time: times[i],
            value: v
        })).filter(Boolean);
    }

    function updateMAOverlays(klSeries, config = {
        sma: [20],
        ema: []
    }) {
        const closes = klSeries.map(b => b.close);
        const keys = [
            ...(config.sma || []).map(p => `SMA${p}`),
            ...(config.ema || []).map(p => `EMA${p}`),
        ];
        keys.forEach((key, idx) => {
            const p = Number(key.replace(/^\D+/, ''));
            const arr = key.startsWith('SMA') ? sma(closes, p) : ema(closes, p);
            ensureLine(key, idx).setData(buildMAData(klSeries, arr));
        });
    }

    // Varsayılan katmanlar (istediğin gibi değiştir)
    const MA_CONFIG = {
        sma: [7, 25],
        ema: [99]
    };

    // ==== grafik ====
    const chartEl = document.getElementById('chart');
    /** @type {import('lightweight-charts').IChartApi} */
    let chart;
    /** @type {import('lightweight-charts').ISeriesApi<"Candlestick">} */
    let candle;

    function makeChart() {
        if (!chartEl) return; // chart DOM'u yoksa grafik kurulmaz
        // Güvenli temizleme
        while (chartEl.firstChild) chartEl.removeChild(chartEl.firstChild);
        chart = LightweightCharts.createChart(chartEl, {
            autoSize: true,
            timeScale: {
                rightOffset: 3,
                barSpacing: 6,
                borderVisible: false
            },
            crosshair: {
                mode: 1
            },
            grid: {
                vertLines: {
                    visible: true
                },
                horzLines: {
                    visible: true
                }
            },
            layout: {
                background: {
                    type: 'solid',
                    color: '#ffffff'
                },
                textColor: '#334155'
            },
        });
        // Zaman etiketlerinde saat/dk/sn gösterimi
        chart.applyOptions({
            timeScale: {
                timeVisible: true,
                secondsVisible: true
            },
            localization: {
                locale: LOCALE, // dosyada tanımlı (i18n helpers)
                timeFormatter: (ts) => {
                    const d = new Date(ts * 1000);
                    return new Intl.DateTimeFormat(LOCALE, {
                        year: '2-digit',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
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
    }

    function applyChartTheme(dark) {
        chart?.applyOptions({
            layout: {
                background: {
                    type: 'solid',
                    color: dark ? '#0f172a' : '#ffffff'
                },
                textColor: dark ? '#cbd5e1' : '#334155',
            },
            grid: {
                vertLines: {
                    color: dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.16)'
                },
                horzLines: {
                    color: dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.16)'
                },
            },
        });
        candle?.applyOptions({
            upColor: dark ? '#10b981' : '#16a34a',
            downColor: dark ? '#ef4444' : '#dc2626',
            wickUpColor: dark ? '#10b981' : '#16a34a',
            wickDownColor: dark ? '#ef4444' : '#dc2626',
        });
        recolorMAs(dark);
        applyMaChartTheme(dark);
    }

    // (çok sekmeli kullanım için) localStorage 'theme' değişimini yakala
    const onTheme = (e) => {
        const dark = e?.detail?.isDark ?? document.documentElement.classList.contains('dark');
        try {
            applyChartTheme(dark);
        } catch {}
        try {
            window.EQUITY_REDRAW?.();
        } catch {}
        try {
            applyMaChartTheme(dark);
        } catch {}
    };

    window.addEventListener('ui:theme', onTheme);

    // İlk init akışı alttaki IIFE’de yönetiliyor (grafik, bootstrap, interval’ler).

    // ==== global durum ====
    let klTf = '15m';
    let klLimit = 1000;
    let seriesFirstTime = null;
    let seriesLastTime = null; // grafikte en son barın zamanı (ghost sonrası kesin mevcut)
    let activeSymbol = null;
    let symbolList = []; // UI select’i doldurmak için
    // Klines/markers overlap kilidi
    let _tickInFlight = false;

    // Açık/kapanan işlemlerden borsa tespiti ve diğer yardımcılar için güvenli cache
    let OPEN_TRADES_CACHE = [];
    let klTimes = []; // seri bar zamanları (s)
    let klGridTimes = []; // ilk→son bar arası TF adımlı grid

    const TF_SEC = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '4h': 14400,
        '1d': 86400
    };

    async function bootstrapActiveSymbol() {
        // 0) UI select’i hazırla (bir kez)
        try {
            await refreshSymbolPicker();
        } catch {}

        // 1) Açık pozisyonlardan seç
        try {
            const r = await fetch('/api/me/open-trades', {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (r.ok) {
                const items = await r.json();
                if (Array.isArray(items) && items.length) {
                    const sym = String(items[0]?.symbol || '').toUpperCase();
                    if (sym) {
                        activeSymbol = sym;
                        return sym;
                    }
                }
            }
        } catch {}
        // 2) Son işlemden seç
        try {
            const r2 = await fetch('/api/me/recent-trades?limit=1', {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (r2.ok) {
                const arr = await r2.json();
                const t = Array.isArray(arr) ? arr[0] : (arr && arr[0]);
                const sym = t?.symbol ? String(t.symbol).toUpperCase() : '';
                if (sym) {
                    activeSymbol = sym;
                    return sym;
                }
            }
        } catch {}
        // 3) UI seçicisinden (yoksa geçici)
        const el = document.querySelector('[data-symbol-picker]');
        activeSymbol = (el?.value ? String(el.value).toUpperCase() : '');

        if (!activeSymbol) {
            activeSymbol = DEFAULT_SYMBOL;
            usedFallbackSymbol = true;
            updateSymbolLabel?.(activeSymbol);
            showDefaultNotice?.(activeSymbol);
            // tooltip: çip üzerine sembol bilgisini koy
            const note = document.getElementById('default-note');
            if (note) note.title = `Sinyal bekleniyor. Öntanımlı sembol gösteriliyor: ${activeSymbol}`;
        }
        return activeSymbol;
    }

    // --- sembol picker yardımcıları ---
    async function populateSymbolPicker(active) {
        const el = document.querySelector('[data-symbol-picker]');
        if (!el) return;
        try {
            // Sunucudan mevcut semboller (açık + kapanmış işlemlerden)  → options
            const r = await fetch('/api/me/symbols', {
                credentials: 'include'
            });
            const j = r.ok ? await r.json() : {
                symbols: []
            };
            const set = new Set(Array.isArray(j.symbols) ? j.symbols.map(String) : []);
            if (active) set.add(String(active).toUpperCase());
            // Güvenli doldurma (innerHTML yok)
            el.replaceChildren();
            const frag = document.createDocumentFragment();
            [...set].sort().forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                frag.appendChild(opt);
            });
            el.appendChild(frag);
            if (active) el.value = String(active).toUpperCase();
        } catch (_) {
            // sessiz geç – en azından aktif sembolü göster
            el.replaceChildren();
            if (active) {
                const opt = document.createElement('option');
                opt.value = active;
                opt.textContent = active;
                el.appendChild(opt);
                el.value = active;
            }
        }
    }

    async function reloadAllForSymbol(sym) {
        // Grafik + marker + entry line vb. mevcut fonksiyonlarını çağır.
        // (Dosyanın geri kalanındaki kendi yükleme fonksiyonlarını kullanın)
        setActiveSymbol(sym);
        // canlı sembole geçerken bekleme çipini kapat
        try {
            hideDefaultNotice();
            usedFallbackSymbol = false;
        } catch {}
        try {
            await loadKlines?.(activeSymbol, klTf, klLimit);
        } catch {}
        try {
            await loadMarkers?.(activeSymbol, klTf);
        } catch {}
        // ← L/S görünürlüğünü **borsa moduna** göre ayarla (one_way → gizli, hedge → görünür).
        try {
            const mode = await fetchPositionMode(activeSymbol);
            toggleUpnlSplitRows(mode === 'hedge');
            updateModeChip(mode);
        } catch {}
    }


    // ——— Sembol seçici ———
    async function refreshSymbolPicker() {
        const el = document.querySelector('[data-symbol-picker]');
        if (!el) return;

        // Başlangıç: her zaman DEFAULT sembol (BTCUSDT)
        let symbols = [DEFAULT_SYMBOL];
        // Üstüne SADECE açık pozisyon sembollerini ekle
        try {
            const r = await fetch('/api/me/open-trades', {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                },
                cache: 'no-store'
            });
            if (r.ok) {
                const arr = await r.json();
                arr?.forEach(t => t?.symbol && symbols.push(String(t.symbol).toUpperCase()));
            }
        } catch {}
        // benzersiz + sırala
        symbolList = [...new Set(symbols.filter(Boolean))].sort();

        // UI’yi doldur
        const cur = (activeSymbol || '').toUpperCase();
        el.replaceChildren();
        const frag = document.createDocumentFragment();
        symbolList.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            if (s === cur) opt.selected = true;
            frag.appendChild(opt);
        });
        el.appendChild(frag);

        // Tek seçenek de olsa picker görünür kalsın (BTCUSDT göster)
        el.classList.remove('hidden');
        // change dinleyicisi (bir kez)
        if (!el._wired) {
            el.addEventListener('change', async () => {
                const next = String(el.value || '').toUpperCase();
                if (!next || next === activeSymbol) return;
                activeSymbol = next;
                updateSymbolLabel(activeSymbol);
                hideDefaultNotice();
                // grafiği temizle ve tekrar yükle
                try {
                    clearEntryLines();
                } catch {}
                try {
                    candle?.setData?.([]);
                } catch {}
                seriesFirstTime = null;
                seriesLastTime = null;
                await reloadAllForSymbol(next); // aktif sembole göre tüm paneli yenile
            });
            el._wired = true;
        }
    }

    // --- one_way vs hedge: L/S görünürlüğünü yöneten yardımcılar ---
    async function fetchPositionMode(symbol) {
        // /api/me/unrealized?symbol=SYMBOL → { mode: 'one_way'|'hedge', ... }
        try {
            const qs = new URLSearchParams({
                symbol: String(symbol || '').toUpperCase()
            });
            const r = await fetch('/api/me/unrealized?' + qs.toString(), {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Cache-Control': 'no-store'
                },
                cache: 'no-store'
            });
            if (r.ok) {
                const j = await r.json();
                const mode = String(j?.mode || j?.position_mode || '').toLowerCase();
                if (mode === 'hedge' || mode === 'one_way') {
                    LAST_POSITION_MODE = mode;
                    return mode;
                }
            }
            // API boş/uyumsuz dönerse son bilinen değeri koru
            return LAST_POSITION_MODE;
        } catch {
            return LAST_POSITION_MODE;
        }
    }

    function toggleUpnlSplitRows(showSplit) {
        // Sağ panelde L/S satırları (varsa) sadece hedge ve çift bacakta açık olsun
        const rowL = document.getElementById('qb-upnl-long-row');
        const rowS = document.getElementById('qb-upnl-short-row');
        if (rowL) rowL.classList.toggle('hidden', !showSplit);
        if (rowS) rowS.classList.toggle('hidden', !showSplit);
    }

    // (tek) Aktif sembolü değiştir — yüklemeyi reloadAllForSymbol yapar
    function setActiveSymbol(sym) {
        activeSymbol = String(sym).toUpperCase();
        const el = document.querySelector('[data-symbol-picker]');
        if (el && el.value !== activeSymbol) el.value = activeSymbol;
        updateSymbolLabel?.(activeSymbol);
    }

    // Select'i doldur ve event bağla
    async function buildSymbolPicker() {
        const el = document.querySelector('[data-symbol-picker]');
        if (!el) return;

        // 1) /api/me/symbols → tüm bilinen semboller
        let list = [];
        try {
            const r = await fetch('/api/me/symbols', {
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (r.ok) {
                const j = await r.json();
                list = Array.isArray(j.symbols) ? j.symbols.map(x => String(x).toUpperCase()) : [];
            }
        } catch {}

        // 2) Açık pozisyon varsa onları da ekle (çevik UX)
        try {
            const r2 = await fetch('/api/me/open-trades', {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (r2.ok) {
                const arr = await r2.json();
                arr.forEach(t => list.push(String(t.symbol || '').toUpperCase()));
            }
        } catch {}

        // benzersiz + sırala
        list = [...new Set(list.filter(Boolean))].sort();
        // Güvenli doldurma
        el.replaceChildren();
        const frag = document.createDocumentFragment();
        list.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s;
            opt.textContent = s;
            frag.appendChild(opt);
        });
        el.appendChild(frag);

        if (activeSymbol && list.includes(activeSymbol)) el.value = activeSymbol;
        // change listener tekilleştirilmiş olarak refreshSymbolPicker() içinde bağlanıyor.
        // Konsoldan kullanım:
        window.setActiveSymbol = (s) => reloadAllForSymbol(String(s || '').toUpperCase());
    }

    // Verilen ts (s/ms) → grafiğin bar grid'ine snap (<= ts olan en yakın bar başlangıcı)
    function snapToSeries(ts) {
        const tfSec = TF_SEC[klTf] || 60;
        const v = Number(ts);
        const sec = v < 1e12 ? v : Math.floor(v / 1000);
        const times = (klGridTimes && klGridTimes.length) ? klGridTimes : klTimes;
        if (times && times.length) {
            let lo = 0,
                hi = times.length; // upperBound
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                (times[mid] <= sec) ? (lo = mid + 1) : (hi = mid);
            }
            const idx = Math.max(0, lo - 1);
            return times[idx];
        }
        return Math.floor(sec / tfSec) * tfSec;
    }

    // === Markers ===

    // snap & nudge helpers
    function snapToBar(sec, tfSec) {
        return Math.floor(sec / tfSec) * tfSec;
    }

    // Aynı mum + aynı yön/kind için “xN” grupla
    function groupSameBar(baseList) {
        const map = new Map();
        for (const m of baseList) {
            // metinden önceki baz kısmı (OPEN LONG / CLOSE)
            const baseText = String(m.text || '').replace(/\sx\d+$/, '');
            const key = [m.time, m.position, m.shape, m.color, baseText].join('|');
            if (!map.has(key)) map.set(key, {
                ...m,
                text: baseText,
                __count: 0
            });
            map.get(key).__count++;
        }
        return Array.from(map.values()).map(g => ({
            ...g,
            text: g.__count > 1 ? `${g.text} x${g.__count}` : g.text
        }));
    }
    // === EOF Markers ===

    const LOCALE = (navigator.languages && navigator.languages[0]) || navigator.language || 'en-US';
    // Fiyatlar için anahtar:
    //   'en-US'  → borsa gibi göster
    //   'local'  → tarayıcı yereliyle göster
    let PRICE_LOCALE_MODE = localStorage.getItem('priceLocaleMode') || 'en-US'; // 'en-US' | 'local'
    const getPriceLocale = () => (PRICE_LOCALE_MODE === 'local' ? LOCALE : 'en-US');
    // Sayılar (qty, PnL, KPI, fmtNum) da aynı moda tabi olsun:
    const getNumLocale = () => getPriceLocale();
    // Basit API: konsoldan çağır — anında etkisini gör
    window.setPriceLocaleMode = (mode) => {
        PRICE_LOCALE_MODE = (mode === 'local' ? 'local' : 'en-US');
        localStorage.setItem('priceLocaleMode', PRICE_LOCALE_MODE);
        try {
            loadOpenTrades();
            loadRecentTrades();
            loadOverview();
            // QuickBalance otomatik event ile de tetikleniyor; garanti olsun
            document.dispatchEvent(new Event('sig:price-locale-mode-changed'));
        } catch {}
    };

    // ==== i18n helpers ====
    // Dinamik number formatters (mode değişince otomatik etkilenir)
    const numFmt0 = () => new Intl.NumberFormat(getNumLocale());
    const numFmt2 = () => new Intl.NumberFormat(getNumLocale(), {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
    // NOT: Yukarıda let olarak tanımlananlara burada atama yapıyoruz
    fmtNum = (v) => (v == null ? '—' : numFmt0().format(Number(v)));
    fmtPnl = (v) => {
        if (v == null) return '—';
        const n = Number(v);
        const sign = n >= 0 ? '+' : '−';
        return sign + numFmt2().format(Math.abs(n));
    };

    // --- Miktar için dinamik formatter ---
    // 1'in altındaki miktarlarda EN AZ 3 hane göster (Binance görünümü: 0.120 BTC)
    function fmtQty(v) {
        if (v == null || v === '') return '—';
        const n = Number(v);
        if (!Number.isFinite(n)) return '—';
        if (n === 0) return '0';
        const abs = Math.abs(n);
        const max = abs < 1 ? 6 : 3; // küçük miktarlarda daha fazla hassasiyet
        const min = abs < 1 ? 3 : 0; // <1 ise en az 3 hane PAD et
        return new Intl.NumberFormat(getNumLocale(), {
            minimumFractionDigits: min,
            maximumFractionDigits: max
        }).format(n);
    }

    // --- Fiyat için dinamik formatter (LOCALE bazlı) ---
    // Büyük fiyatlarda daha az, mikro fiyatlarda daha çok hane göster.
    function fmtPrice(v) {
        if (v == null || v === '') return '—';
        const n = Number(v);
        if (!Number.isFinite(n)) return '—';
        const abs = Math.abs(n);
        let max;
        if (abs >= 1000) max = 2;
        else if (abs >= 100) max = 3;
        else if (abs >= 1) max = 4;
        else if (abs >= 0.1) max = 5;
        else if (abs >= 0.01) max = 6;
        else max = 8;

        return new Intl.NumberFormat(getPriceLocale(), {
            minimumFractionDigits: 0,
            maximumFractionDigits: max
        }).format(n);
    }

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
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }).format(d);
        return `${utc} UTC`;
    };

    // Kısa, yerel tarih (saniyesiz; "GG.AA SS:DD")
    const fmtDateLocalShort = (rawTs) => {
        if (!rawTs) return '—';
        const ms = (typeof rawTs === 'number' && rawTs < 1e12) ? rawTs * 1000 : rawTs;
        const d = new Date(ms);
        return d.toLocaleString(LOCALE, {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    // ==== market verisi ====
    async function loadKlines({
        symbol = getCurrentSymbol(),
        tf = klTf,
        limit = klLimit
    } = {}) {
        try {
            // Boş sembolde API'yi hiç çağırma → 422 spam’ı durdur
            if (!symbol) {
                lastApiOkAt = 0;
                lastApiErrAt = 0;
                updateFeedStatus();
                return [];
            }
            if (!candle) return []; // grafik kurulmadıysa sessizce çık
            const r = await fetch(`/api/market/klines?symbol=${symbol}&tf=${tf}&limit=${limit}`, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (!r.ok) throw new Error('no api');
            const data = await r.json();
            const rows = Array.isArray(data) ? data : data.items || [];
            const series = rows.map(row => {
                if (Array.isArray(row)) {
                    const ts = Math.floor((row[0] ?? row.t) / 1000);
                    return {
                        time: ts,
                        open: +row[1],
                        high: +row[2],
                        low: +row[3],
                        close: +row[4]
                    };
                } else {
                    const ts = Math.floor((row.t ?? row.ts) / 1000);
                    return {
                        time: ts,
                        open: +row.o,
                        high: +row.h,
                        low: +row.l,
                        close: +row.c
                    };
                }
            });

            if (series.length) {
                klTimes = series.map(s => s.time); // seriden gelen bar zamanları

                // Grafik verisini bas
                candle.setData(series);
                // MA overlay: kapanmış barlar üzerinden hesapla (son bar hariç → daha stabil)
                if (series.length > 1) {
                    // MA overlay: kapanmış barlar
                    updateMAOverlays(series.slice(0, -1), MA_CONFIG);
                } else {
                    try {
                        Object.values(MA).forEach(s => s.setData([]));
                    } catch {}
                }
                // Sağ karttaki MA konfluensi (yalnızca kart ve Chart.js varsa)
                if (document.getElementById('maConfluence') && window.Chart) {
                    try {
                        updateMaConfluence(series);
                    } catch {}
                }

                // Zaman/grid hesapları
                seriesFirstTime = series[0].time;

                const barSec = TF_SEC[tf] || 900;
                seriesLastTime = series[series.length - 1].time;
                // (varsa ghost/son bar güncellemesi burada yapılır)
                // seriesLastTime kesinleştikten sonra grid’i üret:
                klGridTimes = [];
                for (let t = seriesFirstTime; t <= seriesLastTime; t += barSec) klGridTimes.push(t);
                const last = series[series.length - 1];
                let lastTime = last?.time || null;
                const nowBar = Math.floor((Date.now() / 1000) / barSec) * barSec;
                if (last && last.time < nowBar) {
                    const c = last.close;
                    candle.update({
                        time: nowBar,
                        open: c,
                        high: c,
                        low: c,
                        close: c
                    });
                    lastTime = nowBar;
                }
                seriesLastTime = lastTime;
                updateJumpBtnVisibility();
            }
            // Başarılı okuma → "Veri durumu" güncelle
            lastApiOkAt = Date.now();
            updateFeedStatus();
            return series;
        } catch (e) {
            // Hata → son hata zamanını kaydet; çip periyodik olarak bayatlayacak
            lastApiErrAt = Date.now();
            updateFeedStatus();
            return [];
        }
    }

    // Jump butonu devre dışıyken referans hatasını önlemek için no-op
    function updateJumpBtnVisibility() {}

    // * Borsa tarafı: her zaman UTC göster (ISO ya da epoch kabul et)
    const fmtDateUTC = (ts) => {
        if (ts == null) return '—';
        const ms = (typeof ts === 'number') ? ts : parseTs(ts); // ISO → ms
        const d = new Date(ms);
        const yyyy = String(d.getUTCFullYear());
        const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
        const dd = String(d.getUTCDate()).padStart(2, '0');
        const hh = String(d.getUTCHours()).padStart(2, '0');
        const mi = String(d.getUTCMinutes()).padStart(2, '0');
        const ss = String(d.getUTCSeconds()).padStart(2, '0');
        return `${dd}.${mm}.${yyyy} ${hh}:${mi}:${ss}`; // UTC`;
    };

    // ==== son sinyal hangi sembolde? ====
    async function getLatestMarkerSymbol() {
        try {
            const q = new URLSearchParams({
                tf: klTf
            });
            const r = await fetch('/api/me/markers?' + q.toString(), {
                credentials: 'include'
            });
            if (!r.ok) return null;
            const items = await r.json();

            if (!Array.isArray(items) || !items.length) return null;
            // YALNIZCA HÂLÂ AÇIK pozisyonların OPEN marker'ını dikkate al (id'de ':' YOK).
            // Canlı OPEN yoksa, sembolü DEĞİŞTİRME (null dön).
            const liveOpens = items.filter(m => {
                const kind = String(m.kind || '').toLowerCase();
                const status = String(m.status || '').toLowerCase();
                const isLive = (m.is_live === true || m.is_live === 1 || m.is_live === '1' || status === 'open');
                return kind === 'open' && isLive;
            });
            if (!liveOpens.length) return null;
            const chosen = liveOpens.reduce(
                (a, b) => ((+(a.time_bar ?? a.time) || 0) > (+(b.time_bar ?? b.time) || 0) ? a : b)
            );
            return (String(chosen.symbol || '').toUpperCase().trim()) || null;

        } catch {
            return null;
        }
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
        } finally {
            _autoSwitchLock = false;
        }
    }

    async function pickLiveOpenSide(symbol, fallbackRows) {
        // 1) Markers içinde canlı OPEN var mı?
        try {
            const live = (fallbackRows || []).find(m =>
                (String(m.symbol || '').toUpperCase() === symbol) &&
                String(m.kind || '').toLowerCase() === 'open' &&
                (m.is_live === true || String(m.status || '').toLowerCase() === 'open')
            );
            if (live) return String(live.side || '').toLowerCase();
        } catch (e) {}
        // 2) Yoksa open-trades'e sor
        try {
            const qs = new URLSearchParams({
                symbol
            });
            const r = await fetch('/api/me/open-trades?' + qs.toString(), {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json'
                },
                cache: 'no-store'
            });
            if (r.ok) {
                const j = await r.json();
                const arr = Array.isArray(j) ? j : (Array.isArray(j.items) ? j.items : []);
                const row = arr.find(t => String(t.symbol || '').toUpperCase() === symbol);
                if (row) {
                    // side yoksa miktar işaretinden çıkar
                    const s = String(row.side || '').toLowerCase();
                    if (s === 'long' || s === 'short') return s;
                    const amt = Number(row.positionAmt ?? row.position_size ?? 0);
                    if (Number.isFinite(amt) && amt !== 0) return amt > 0 ? 'long' : 'short';
                }
            }
        } catch (e) {}
        return null;
    }

    // ==== markers ====
    // Tüm geçmiş open/close işaretlerini çiz (tek contract: { symbol, tf })
    async function loadMarkers({
        symbol,
        tf
    } = {}) {
        symbol = (symbol || getCurrentSymbol()).toUpperCase();
        tf = tf || klTf;
        try {
            if (!candle || !symbol) return [];
            const url = `/api/me/markers?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}`;
            const res = await fetch(url, {
                credentials: 'include',
                cache: 'no-store'
            });
            if (!res.ok) throw new Error('markers api fail');
            const rows = await res.json();
            // Bu sembolde canlı OPEN var ise çipi gizle (open-trades gecikirse de sorun olmasın)
            try {
                const hasLiveOpen = Array.isArray(rows) && rows.some(m =>
                    String(m.symbol || '').toUpperCase() === symbol &&
                    String(m.kind || '').toLowerCase() === 'open' &&
                    (m.is_live === true || String(m.status || '').toLowerCase() === 'open')
                );
                if (hasLiveOpen) {
                    usedFallbackSymbol = false;
                    hideDefaultNotice();
                }
            } catch {}

            // --- GUEST KISITI ---
            if (GUEST) {
                return []; // misafir: marker çizme
            }

            const tfSec = TF_SEC[klTf] || 60; // 1m=60, 15m=900...
            const used = {}; // aynı bar+pozisyon çakışmasını ötele

            const markers = rows
                .filter(m => (m.symbol || '').toUpperCase() === symbol)
                .map(m => {
                    const kind = String(m.kind || '').toLowerCase();
                    const side = String(m.side || '').toLowerCase();
                    let pos = m.position || (side === 'short' ? 'aboveBar' : 'belowBar');
                    let shape, color, size;

                    if (kind === 'open') {
                        shape = side === 'short' ? 'arrowDown' : 'arrowUp';
                        color = side === 'short' ? '#ef4444' : '#10b981';
                    } else {
                        // CLOSE: ters yön küçük ok
                        if (side === 'long') {
                            // Long
                            shape = 'circle';
                            color = '#047857';
                            pos = 'aboveBar';
                            size = 1;
                        } else if (side === 'short') {
                            // Short
                            shape = 'circle';
                            color = '#b91c1c';
                            pos = 'belowBar';
                            size = 1;
                        } else {
                            shape = 'circle';
                            color = '#f59e0b';
                            size = 1; // bilinmiyorsa turuncu daire
                        }
                    }
                    // zaman: backend time_bar gönderiyorsa onu kullan; yoksa time
                    let t = Math.floor(Number(m.time_bar ?? m.time) || 0); // seconds
                    t = Math.floor(t / tfSec) * tfSec;
                    const key = `${t}:${pos}`;
                    used[key] = (used[key] || 0) + 1;
                    if (used[key] > 1) t += (used[key] - 1); // +1s, +2s...

                    return {
                        time: t,
                        position: pos,
                        shape,
                        color,
                        text: '', // OPEN/CLOSE yazılarını kaldır
                        size // close marker'larda küçük ok
                    };
                });
            candle.setMarkers(markers);
            return markers;
        } catch (e) {
            if (DEBUG) console.warn('loadMarkers failed', e);
            try {
                candle && candle.setMarkers([]);
            } catch {}
            return [];
        }
    }
    if (DEBUG) window.loadMarkers = loadMarkers;

    // ==== Açık pozisyonlar ====
    async function loadOpenTrades() {
        try {
            // cache: 'no-store' → tarayıcı önbelleğini baypas et, eksiltmeler anında gelsin
            const res = await fetch(`/api/me/open-trades?limit=${RECENT_TRADES_LIMIT}`, {
                credentials: 'include',
                cache: 'no-store',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!res.ok) throw new Error('api');
            const items = await res.json();
            OPEN_TRADES_CACHE = Array.isArray(items) ? items : [];
            // Sembol seçiciyi canlı duruma göre güncelle
            try {
                await refreshSymbolPicker();
            } catch {}

            // İlk açılışta fallback sembolden dolayı gösterilen
            // “Sinyal bekleniyor…” çipini, artık canlı open varsa gizle.
            if (Array.isArray(items) && items.length > 0) {
                usedFallbackSymbol = false;
                hideDefaultNotice();
            }

            // Equity modülüne haber ver
            try {
                document.dispatchEvent(new CustomEvent('sig:open-trades', {
                    detail: {
                        items
                    }
                }));
            } catch {}
            // Panel DOM’u olmasa bile çizgileri doğru yönet

            const el = document.querySelector('#open-positions');
            if (!Array.isArray(items) || items.length === 0) {
                // ⟵ Hiç açık pozisyon kalmadı → öntanımlı sembole dön
                try {
                    const needFallback = (activeSymbol && activeSymbol !== DEFAULT_SYMBOL) || !usedFallbackSymbol;
                    if (needFallback) {
                        activeSymbol = DEFAULT_SYMBOL;
                        usedFallbackSymbol = true;
                        updateSymbolLabel?.(activeSymbol);
                        showDefaultNotice?.(activeSymbol);
                        // picker'ı senkle
                        const sel = document.querySelector('[data-symbol-picker]');
                        if (sel) sel.value = DEFAULT_SYMBOL;
                        // grafiği/işaretçileri default sembolle yükle
                        try {
                            await loadKlines({
                                symbol: activeSymbol,
                                tf: klTf,
                                limit: klLimit
                            });
                        } catch {}
                        try {
                            await loadMarkers({
                                symbol: activeSymbol,
                                tf: klTf
                            });
                        } catch {}
                        // mod çipi ve L/S görünürlüğü
                        try {
                            const m = await fetchPositionMode(activeSymbol);
                            toggleUpnlSplitRows(m === 'hedge');
                            updateModeChip(m);
                        } catch {}
                    }
                } catch {}
                if (el) el.textContent = '—';
                clearEntryLines(); // entry çizgilerini temizle
                return [];
            }

            if (!el) return items;

            // Güvenli DOM: header + satırlar
            el.textContent = '';
            const $div = (cls, text) => {
                const d = document.createElement('div');
                if (cls) d.className = cls;
                if (text != null) d.textContent = String(text);
                return d;
            };
            const frag = document.createDocumentFragment();

            // Header — Açık Pozisyonlar tablosu
            const header = $div('text-xs text-slate-500 dark:text-slate-400 mb-1 grid gap-2');
            // Sembol | Yön | Miktar | Giriş | Kaldıraç | Tarih
            header.style.gridTemplateColumns = 'repeat(6,minmax(0,1fr))';
            header.append(
                $div('', 'Sembol'),
                $div('', 'Yön'),
                $div('', 'Miktar'),
                $div('', 'Giriş Fiyatı'),
                $div('', 'Kaldıraç'),
                $div('', 'Tarih')
            );
            frag.append(header);

            // Rows — Açık Pozisyonlar tablosu
            const wrap = document.createElement('div');
            items.forEach(t => {
                const row = $div('grid gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40');
                row.style.gridTemplateColumns = 'repeat(6,minmax(0,1fr))';

                const side = String(t.side || '').toUpperCase();
                const sideCls = side === 'LONG' ? 'text-xs text-emerald-500' : 'text-xs text-rose-400';

                row.append(
                    $div('text-xs', t.symbol),
                    $div(sideCls, side),
                    // Miktar: küçük değerlerde 6 hane, büyüklerde 3
                    // $div('text-xs', fmtQty(t.position_size ?? t.size)),

                    // Miktar: varsa backend’in metni (0.120 vb.), yoksa eski formatter
                    $div('text-xs', t.position_size_text ?? fmtQty(t.position_size ?? t.size)),
                    $div('text-xs', fmtPrice(t.entry_price)),
                    $div('text-xs', `${t.leverage}x`),
                    // Sağ tabloyla aynı: nowrap tarih (ellipsis/truncate yok)
                    $div('text-xs text-slate-500 whitespace-nowrap', fmtDateUTC(t.timestamp))
                );
                wrap.appendChild(row);
            });

            frag.append(wrap);
            el.appendChild(frag);
            // DOM basıldı → canlı open kesinleşti: çipi kapat
            try {
                hideDefaultNotice();
                usedFallbackSymbol = false;
            } catch {}

            // --- Entry price çizgileri (hedge: iki bacak) ---
            // Misafirlerde entry çizgisi asla görünmesin
            if (GUEST) {
                clearEntryLines();
                return items;
            }
            try {
                const act = String(activeSymbol || '').toUpperCase();
                const rows = Array.isArray(items) ?
                    items.filter(t => String(t?.symbol || '').toUpperCase() === act) : [];
                // En yeni kaydı bul (timestamp/alternatif alanlar; epoch ya da ISO destekli)
                const tsOf = (t) => parseTs(t?.timestamp) ?? parseTs(t?.opened_at) ?? 0;
                // Bir kayıttan "entry" seçme yardımcıları
                const pickFrom = (t) => {
                    const cand = [
                        t?.avg_entry_price, t?.avg_price, t?.entry_avg, t?.entry_price
                    ];
                    const v = cand.find(v => v != null && v !== '');
                    return Number(v);
                };
                // Hedge: her bacak için en yeni açık kaydı al
                const perSide = {
                    long: null,
                    short: null
                };
                if (rows.length) {
                    const longRows = rows.filter(r => String(r?.side || '').toLowerCase() === 'long').sort((a, b) => tsOf(a) - tsOf(b));
                    const shortRows = rows.filter(r => String(r?.side || '').toLowerCase() === 'short').sort((a, b) => tsOf(a) - tsOf(b));
                    if (longRows.length) {
                        let v = pickFrom(longRows[longRows.length - 1]);
                        if (!Number.isFinite(v))
                            for (const r of [...longRows].reverse()) {
                                v = pickFrom(r);
                                if (Number.isFinite(v)) break;
                            }
                        if (Number.isFinite(v)) perSide.long = v;
                    }
                    if (shortRows.length) {
                        let v = pickFrom(shortRows[shortRows.length - 1]);
                        if (!Number.isFinite(v))
                            for (const r of [...shortRows].reverse()) {
                                v = pickFrom(r);
                                if (Number.isFinite(v)) break;
                            }
                        if (Number.isFinite(v)) perSide.short = v;
                    }
                }
                if (perSide.long != null || perSide.short != null) updateEntryLines(perSide);
                else clearEntryLines();
            } catch {}
            return items;
        } catch (e) {
            // --- Open trades state (exchange seçimi için) ---
            // cache’i temizle
            OPEN_TRADES_CACHE = [];
            const el = document.querySelector('#open-positions');
            if (el) el.textContent = '—';
            clearEntryLines();
            // Hata olsa da Quick Balance güncelleyebilsin
            try {
                document.dispatchEvent(new CustomEvent('sig:open-trades', {
                    detail: {
                        items: []
                    }
                }));
            } catch {}
            return [];
        }
    }

    // ==== Kapanan pozisyonlar ====
    async function loadRecentTrades() {
        try {
            // Kapamalar için de cache’i kapatalım
            const res = await fetch(`/api/me/recent-trades?limit=${RECENT_TRADES_LIMIT}`, {
                credentials: 'include',
                cache: 'no-store',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!res.ok) throw new Error('api');
            const items = await res.json();
            // Equity modülüne haber ver
            try {
                document.dispatchEvent(new CustomEvent('sig:recent-trades', {
                    detail: {
                        items
                    }
                }));
            } catch (e) {}

            const el = document.querySelector('#recent-trades');
            if (!el) return items;

            if (!Array.isArray(items) || items.length === 0) {
                el.textContent = '—';
                return [];
            }

            const fmtMaybePrice = (v) => (v == null || v === '' ? '—' : fmtPrice(v));
            const fmtMaybeQty = (v) => (v == null || v === '' ? '—' : fmtQty(v));
            // Güvenli DOM: header + satırlar
            el.textContent = '';
            const $div = (cls, text) => {
                const d = document.createElement('div');
                if (cls) d.className = cls;
                if (text != null) d.textContent = String(text);
                return d;
            };
            const frag = document.createDocumentFragment();

            // Header - Kapanmış pozisyonlar tablosu
            const header = $div('text-xs text-slate-500 dark:text-slate-400 mb-1 grid gap-2');
            header.style.gridTemplateColumns = 'repeat(6,minmax(0,1fr))';
            header.append(
                $div('', 'Sembol'),
                $div('', 'Yön'),
                $div('', 'Miktar'),
                $div('', 'Giriş Fiyatı'),
                $div('', 'Çıkış Fiyatı'),
                $div('', 'Tarih')
            );
            frag.append(header);

            // Rows - Kapanmış pozisyonlar tablosu
            const wrap = document.createElement('div');
            items.forEach(t => {
                const side = String(t.side || '').toUpperCase();
                const sideCls = side === 'LONG' ? 'text-xs text-emerald-500' : 'text-xs text-rose-400';
                const tsUTC = fmtDateUTC(pickTradeCloseTs(t));
                const row = $div('grid gap-2 py-1 border-b border-slate-200/40 dark:border-slate-700/40');

                row.style.gridTemplateColumns = 'repeat(6,minmax(0,1fr))';
                const sym = $div('text-xs', t.symbol); // sym.title = tsUTC;
                row.append(
                    sym,
                    $div(sideCls, side),
                    // Kapanmışlar tablosunda da miktarı dinamik göster
                    $div('text-xs', fmtMaybeQty(t.position_size)),
                    $div('text-xs', fmtMaybePrice(t.entry_price)),
                    $div('text-xs', fmtMaybePrice(t.exit_price)),
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
            const r = await fetch('/api/me/overview', {
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (!r.ok) return;
            const d = await r.json();
            setText('#kpi-pnl', fmtPnl(d.pnl_7d));
            setText('#kpi-win', fmtPct(d.winrate_30d));
            setText('#kpi-open', fmtNum(d.open_trade_count));
            setText('#kpi-dd', fmtPct(d.max_dd_30d));
            setText('#kpi-sharpe', d.sharpe_30d ?? '—');
            setText('#kpi-last', d.last_signal_at ? fmtDateLocalPlusUTC(d.last_signal_at) : '—');

            const setTitle = (sel, t) => {
                const el = document.querySelector(sel);
                if (el) el.title = t;
            };
            setTitle('#kpi-pnl', 'PnL (son 7 gün)');
            setTitle('#kpi-win', 'Kazanma Oranı (son 30 gün)');
            setTitle('#kpi-open', 'Şu anki açık pozisyon adedi');
            setTitle('#kpi-dd', 'Maksimum Düşüş (son 30 gün, peak→trough)');
            setTitle('#kpi-sharpe', 'Sharpe Oranı (son 30 gün, günlük getiriler)');
            setTitle('#kpi-last', 'Son sinyal zamanı (UTC)');
        } catch {}
    }

    // ==== sembol yönetimi ====
    function formatPair(sym) {
        return String(sym ?? '');
    }

    function updateSymbolLabel(sym) {
        const el = document.querySelector('#symbol-label');
        if (el) el.textContent = formatPair(sym);
    }

    // Aktif sembolü oku (URL → data-symbol → label text)
    function getCurrentSymbol() {
        const qs = new URLSearchParams(location.search).get('symbol');
        const el = document.querySelector('#symbol-label');
        const ds = el?.dataset?.symbol;
        const tx = (el?.textContent || '').trim();
        return (qs || ds || tx || '').toUpperCase();
    }

    async function loadSymbols() {
        // doğru endpoint: /api/me/symbols  (parametresiz)
        try {
            const r = await fetch('/api/me/symbols', {
                credentials: 'include'
            });
            if (!r.ok) return [];
            const j = await r.json();
            return Array.isArray(j.symbols) ? j.symbols : [];
        } catch {
            return [];
        }
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
        await loadKlines({
            symbol: activeSymbol,
            tf: klTf,
            limit: klLimit
        });
        await loadMarkers({
            symbol: activeSymbol,
            tf: klTf
        });
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
    //  highlightActiveTf(klTf);
    //  makeChart();
    highlightActiveTf(klTf);
    makeChart(); // grafik burada bir kez kuruluyor
    (async () => {
        // Öncelik: URL ?symbol= → açık poz./son işlem (bootstrapActiveSymbol) → canlı marker → bilinen liste → fallback
        const qp = new URLSearchParams(location.search);
        const fromUrl = qp.get('symbol');
        const known = await loadSymbols();
        //    const bootSym = await bootstrapActiveSymbol();     // /api/me/open-trades → /api/me/recent-trades → picker
        const bootSym = await bootstrapActiveSymbol(); // picker'ı da burada doldurur
        const latest = await getLatestMarkerSymbol(); // canlı marker varsa
        let initial = (fromUrl && fromUrl.toUpperCase()) ||
            bootSym ||
            latest ||
            (known[0] || ''); // sabit yok; bilinen listeden ya da boş
        activeSymbol = initial ? initial.toUpperCase() : '';
        updateSymbolLabel(activeSymbol || '—');
        // Hızlı Bakiye ilk çekimi için (activeSymbol hazır olduğunda) haber ver
        document.dispatchEvent(new Event('sig:active-ready'));
        if (usedFallbackSymbol) showDefaultNotice(activeSymbol);

        // İlk yüklemede son işaretçiye senkron + temel verileri çek
        await autoSwitchSymbolIfNeeded();
        await loadKlines({
            symbol: activeSymbol
        });
        await loadMarkers({
            symbol: activeSymbol,
            tf: klTf
        });
        loadOpenTrades();
        loadRecentTrades();
        loadOverview();

        setInterval(async () => {
            if (_tickInFlight) return; // önceki tick bitmeden yenisine girme
            _tickInFlight = true;
            try {
                if (!activeSymbol) {
                    await bootstrapActiveSymbol();
                } else {
                    await autoSwitchSymbolIfNeeded();
                    // küçük jitter (±150ms) → eşzamanlı sekmeler backend’e aynı anda vurmasın
                    const j = Math.floor((Math.random() * 300) - 150);
                    //await new Promise(r => setTimeout(r, Math.max(0, j)));
                    if (j > 0) await new Promise(r => setTimeout(r, j));
                    await loadKlines({
                        symbol: activeSymbol,
                        tf: klTf,
                        limit: klLimit
                    });
                    await loadMarkers({
                        symbol: activeSymbol,
                        tf: klTf
                    });
                }
            } finally {
                _tickInFlight = false;
            }
        }, REFRESH_MS);

        // Veri çipini her saniye yeniden değerlendir (API çağrısı olmasa da)
        setInterval(updateFeedStatus, 1000);
        // İlk durum
        updateFeedStatus();

        setInterval(() => loadOpenTrades(), OPEN_TRADES_MS);
        setInterval(() => loadRecentTrades(), RECENT_TRADES_MS);
    })();

    // ===== HIZLI BAKİYE ÖZETİ =====
    (function wireQuickBalance() {
        let nf2QB = new Intl.NumberFormat(getNumLocale(), {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
        const fmt2 = (v) => nf2QB.format(v || 0);

        // Mode değişince Quick Balance formatter’ını tazele
        document.addEventListener('sig:price-locale-mode-changed', () => {
            nf2QB = new Intl.NumberFormat(getNumLocale(), {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            });
        });

        // Güvenli sayı çevirici (net toplarken ve son kapananda kullanılıyor)
        const safeNum = (v) => {
            const n = Number(v);
            return Number.isFinite(n) ? n : 0;
        };

        // Aktif sembolün borsasını açık pozisyonlardan bul (modüler)
        function getActiveExchange(sym) {
            try {
                const row = OPEN_TRADES_CACHE.find(t => String(t?.symbol || '').toUpperCase() === String(sym || '').toUpperCase());
                return row?.exchange || null;
            } catch {
                return null;
            }
        }
        // uPnL payload'ından (list ya da tekil) verilen sembol için tüm bacakları topla
        function extractUpnl(payload, symbol) {
            const SYM = String(symbol || '').toUpperCase();
            // Tekil sayısal alanlar
            if (typeof payload === 'number') return payload;
            if (payload && Number.isFinite(+payload.unrealized)) return +payload.unrealized;
            if (payload && Number.isFinite(+payload.upnl)) return +payload.upnl;
            const arr = Array.isArray(payload) ? payload :
                (payload?.items || payload?.positions || []);
            if (!Array.isArray(arr)) return 0;
            let sum = 0;
            for (const p of arr) {
                const psym = String(p?.symbol || p?.s || '').toUpperCase();
                if (SYM && psym && psym !== SYM) continue;
                // doğrudan uPnL alanları
                let u = p?.unrealized ?? p?.unRealizedProfit ?? p?.unrealizedPnl ?? p?.upnl ?? p?.pnl;
                if (u != null && u !== '') {
                    sum += +u;
                    continue;
                }
                // türet: entry/mark/qty
                const qty = +((p?.positionAmt ?? p?.qty ?? p?.size) || 0);
                const entry = +((p?.entryPrice ?? p?.avgPrice ?? p?.entry) || 0);
                const mark = +((p?.markPrice ?? p?.price ?? 0));
                if (qty && entry && mark) {
                    const abs = Math.abs(qty);
                    sum += (qty > 0) ? (mark - entry) * abs // LONG
                        :
                        (entry - mark) * abs; // SHORT
                }
            }
            return sum;
        }

        // Hedge: LONG/SHORT kırılımını çıkar (liste varsa doğrudan, aggregate ise açık bacağın yönüne paylaştır)
        function extractUpnlBySide(payload, symbol, openRowsForActive = []) {
            const SYM = String(symbol || '').toUpperCase();
            const out = {
                long: 0,
                short: 0,
                hasLong: false,
                hasShort: false
            };
            // (0) Yeni backend şekli: { unrealized, legs: { long, short }, mode }
            if (payload && payload.legs && typeof payload.legs === 'object') {
                const L = Number(payload.legs.long ?? 0);
                const S = Number(payload.legs.short ?? 0);
                out.long = Number.isFinite(L) ? L : 0;
                out.short = Number.isFinite(S) ? S : 0;
                // Satırı gizlememek için: değer 0 olsa bile ilgili bacakta açık pozisyon varsa görünür kalsın
                const hasLongOpen = (openRowsForActive || []).some(r => String(r?.side || '').toLowerCase() === 'long');
                const hasShortOpen = (openRowsForActive || []).some(r => String(r?.side || '').toLowerCase() === 'short');
                // one_way/BOTH güvenlik ağı: legs 0 ise toplamı açık bacağın yönüne yaz
                if (!out.long && !out.short && Number.isFinite(+payload.unrealized)) {
                    if (hasLongOpen) {
                        out.long = +payload.unrealized;
                        out.hasLong = true;
                    }
                    if (hasShortOpen) {
                        out.short = +payload.unrealized;
                        out.hasShort = true;
                    }
                }
                out.hasLong = hasLongOpen || out.long !== 0;
                out.hasShort = hasShortOpen || out.short !== 0;
                return out;
            }

            // 1) Liste (positions/items/array) ise tek tek tara
            const arr = Array.isArray(payload) ? payload :
                (payload?.items || payload?.positions || []);
            if (Array.isArray(arr)) {
                for (const p of arr) {
                    const psym = String(p?.symbol || p?.s || '').toUpperCase();
                    if (SYM && psym && psym !== SYM) continue;
                    let u = p?.unrealized ?? p?.unRealizedProfit ?? p?.unrealizedPnl ?? p?.upnl ?? p?.pnl;
                    if (u == null || u === '') {
                        const qty = +((p?.positionAmt ?? p?.qty ?? p?.size) || 0);
                        const entry = +((p?.entryPrice ?? p?.avgPrice ?? p?.entry) || 0);
                        const mark = +((p?.markPrice ?? p?.price ?? 0));
                        if (qty && entry && mark) {
                            const abs = Math.abs(qty);
                            u = (qty > 0) ? (mark - entry) * abs : (entry - mark) * abs;
                        } else {
                            u = 0;
                        }
                    }
                    let side = String(p?.side || '').toLowerCase();
                    if (!side) {
                        const qty = +((p?.positionAmt ?? p?.qty ?? p?.size) || 0);
                        side = qty < 0 ? 'short' : (qty > 0 ? 'long' : '');
                    }
                    if (side === 'short') {
                        out.short += +u;
                        out.hasShort = true;
                    } else {
                        out.long += +u;
                        out.hasLong = true;
                    }
                }
                return out;
            }
            // 2) Aggregate sayı ise: aktif açık kayıtlardan bacak yönünü bul ve ona yaz
            const agg = (typeof payload === 'number') ?
                +payload :
                (Number.isFinite(+payload?.unrealized) ? +payload.unrealized :
                    (Number.isFinite(+payload?.upnl) ? +payload.upnl : 0));
            if (!Number.isFinite(agg) || agg === 0) return out;
            const cand = (openRowsForActive || []).find(Boolean);
            const side = String(cand?.side || '').toLowerCase();
            if (side === 'short') {
                out.short = agg;
                out.hasShort = true;
            } else {
                out.long = agg;
                out.hasLong = true;
            }
            return out;
        }

        // Kart yalnız Asil üye'de HTML'a basılıyor; bu yüzden sadece DOM varlığına bakmak yeterli.
        const elWallet = document.getElementById('qb-wallet');
        const elNet = document.getElementById('qb-net');

        // L/S — toplam yok (hedge: ayrı satırlar)
        const elUpL = document.getElementById('qb-upnl-long');
        const elUpS = document.getElementById('qb-upnl-short');
        const rowUpL = document.getElementById('qb-upnl-long-row');
        const rowUpS = document.getElementById('qb-upnl-short-row');
        const elOpen = document.getElementById('qb-open');
        const elLast = document.getElementById('qb-last');

        if (!elNet || !elOpen || !elLast) return;
        // Öncelikli alan: realized_pnl; diğer isimler olursa temkinli fallback
        const pickPnl = (t) => (
            t?.realized_pnl ??
            t?.realized_pnl_usd ??
            t?.pnl_usdt ??
            t?.pnl ??
            0
        );

        async function loadQuickBalance(opts) {
            const silent = true; // manuel yenile kaldırıldı → hep sessiz
            // Aktif sembol henüz belirlenmediyse ilk yüklemeyi beklet
            if (!activeSymbol) return;
            // SYM'i fonksiyon seviyesinde tanımla: aşağıda ve catch dışında da kullanılıyor
            const SYM = String(activeSymbol).toUpperCase();
            try {
                /* manuel durum mesajları kaldırıldı */

                // 1) Net PnL (önce /netpnl, olmazsa /recent-trades toplamı)
                let net = 0,
                    lastText = '—';
                let lastView = null; // {sym, side, sign, lpnl, ts, pnlCls}
                // a) /api/me/netpnl – backend “ilk emrin tarihinden” aralığı kendi belirler
                try {
                    const qsNet = new URLSearchParams();
                    const exForNet = getActiveExchange(activeSymbol);
                    if (exForNet) qsNet.set('exchange', exForNet);
                    if (activeSymbol) qsNet.set('symbol', String(activeSymbol).toUpperCase());
                    const rNet = await fetch('/api/me/netpnl?' + qsNet.toString(), {
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json'
                        }
                    });
                    if (rNet.ok) {
                        const jn = await rNet.json();
                        // destek: { net: <num> } veya { net_pnl: <num> }
                        const v = (jn && (jn.net ?? jn.net_pnl));
                        if (typeof v === 'number') net = v;
                    }
                } catch {}
                // b) Eğer /netpnl yoksa/0 geldiyse fallback: /recent-trades toplamı (+ son işlem bilgisi)
                try {
                    // Son işlemi göstermek için limit=1; toplam için limit geniş tut (1000)
                    const qsSum = new URLSearchParams({
                        limit: '1000'
                    });
                    if (activeSymbol) qsSum.set('symbol', String(activeSymbol).toUpperCase());
                    const rSum = await fetch('/api/me/recent-trades?' + qsSum.toString(), {
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json'
                        }
                    });
                    if (rSum.ok) {
                        const arr = await rSum.json();
                        if (Array.isArray(arr) && arr.length) {
                            // /netpnl değeri 0 ise DB toplamına düş
                            if (!net) {
                                let sum = 0;
                                for (const t of arr) sum += safeNum(pickPnl(t));
                                net = sum;
                            }
                            // “Son Kapanan” için yalnız ilk kayıt yeterli
                            const last = arr[0];
                            if (last) {
                                const side = (last?.side || '').toString().toUpperCase();
                                const sym = last?.symbol || '';
                                const lpnl = safeNum(pickPnl(last));
                                const sign = lpnl >= 0 ? '+' : '';
                                const ts = fmtDateLocalShort(last?.timestamp);
                                const pnlCls = lpnl > 0 ? 'text-emerald-500' :
                                    (lpnl < 0 ? 'text-rose-400' : 'text-slate-400');
                                lastView = {
                                    sym,
                                    side,
                                    sign,
                                    lpnl,
                                    ts,
                                    pnlCls
                                };
                                lastText = `${sym} ${side} · ${sign}${fmt2(lpnl)} · ${ts}`;
                            }
                        }
                    }
                } catch {}

                // 2) Açık pozisyonlar — ÖNCE cache, boşsa fetch'e düş
                let openRowsAll = Array.isArray(OPEN_TRADES_CACHE) ? OPEN_TRADES_CACHE : [];
                let openCnt = openRowsAll.length;
                if (openCnt === 0) {
                    try {
                        const r2 = await fetch(`/api/me/open-trades?limit=${RECENT_TRADES_LIMIT}`, {
                            credentials: 'include',
                            cache: 'no-store',
                            headers: {
                                'Accept': 'application/json'
                            }
                        });
                        if (r2.ok) {
                            const arr2 = await r2.json();
                            if (Array.isArray(arr2)) {
                                openRowsAll = arr2;
                                openCnt = arr2.length;
                            }
                        }
                    } catch {}
                }

                elNet.textContent = (Number(net) === 0 ? '0' : (net > 0 ? '+' : '−') + fmt2(Math.abs(Number(net))));
                elOpen.textContent = String(openCnt);

                if (openCnt > 0) {
                    // Önce aynı çağrıdan gelen liste → sonra cache → en son tek yedek fetch
                    let openRowsForActive = Array.isArray(openRowsAll) ?
                        openRowsAll.filter(t =>
                            String(t?.symbol || '').toUpperCase() === String(activeSymbol).toUpperCase()
                        ) : [];
                    if (!openRowsForActive.length && Array.isArray(OPEN_TRADES_CACHE) && OPEN_TRADES_CACHE.length) {
                        openRowsForActive = OPEN_TRADES_CACHE.filter(t =>
                            String(t?.symbol || '').toUpperCase() === String(activeSymbol).toUpperCase()
                        );
                    }
                    // L/S kırılımı için başlangıç objesi (toplam yok; sıfır)
                    let bd = {
                        long: 0,
                        short: 0,
                        hasLong: false,
                        hasShort: false
                    };
                    let lastPayload = null; // gerektiğinde toplamı çıkarmak için
                    try {
                        const ex = getActiveExchange(activeSymbol);
                        // (a) Düz çağrı (legs dönerse burada yakalarız)
                        let ju = null;
                        const qs0 = new URLSearchParams({
                            symbol: SYM
                        });
                        if (ex) qs0.set('exchange', ex);
                        let rU = await fetch('/api/me/unrealized?' + qs0.toString(), {
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json'
                            }
                        });
                        if (rU.ok) {
                            ju = await rU.json();
                            bd = extractUpnlBySide(ju, SYM, openRowsForActive);
                            lastPayload = ju;
                        }
                        // (b) Hâlâ L/S oluşmadıysa all=1'e düş
                        if (!bd.hasLong && !bd.hasShort) {
                            const qs2 = new URLSearchParams({
                                symbol: SYM,
                                all: '1'
                            });
                            if (ex) qs2.set('exchange', ex);
                            rU = await fetch('/api/me/unrealized?' + qs2.toString(), {
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json'
                                }
                            });
                            if (rU.ok) {
                                ju = await rU.json();
                                bd = extractUpnlBySide(ju, SYM, openRowsForActive);
                                lastPayload = ju;
                            }
                        }
                        // fallback: aggregate
                        if (!bd.hasLong && !bd.hasShort) {
                            const qsA = new URLSearchParams({
                                symbol: SYM
                            });
                            if (ex) qsA.set('exchange', ex);
                            const rA = await fetch('/api/me/unrealized?' + qsA.toString(), {
                                credentials: 'include',
                                headers: {
                                    'Accept': 'application/json'
                                }
                            });
                            if (rA.ok) {
                                const jA = await rA.json();
                                bd = extractUpnlBySide(jA, SYM, openRowsForActive);
                                lastPayload = jA;
                            }
                        }

                        // Hâlâ bacak tespit edilemediyse (ör. one_way + agg),
                        // açık pozisyon satırından yönü çıkar ve toplamı o bacağa yaz.
                        if (!bd.hasLong && !bd.hasShort && openRowsForActive.length) {
                            const first = openRowsForActive[0];
                            const qty = Number(first.positionAmt ?? first.position_size ?? first.size ?? 0);
                            const sideFromOpen = String(first.side || (qty < 0 ? 'short' : 'long')).toLowerCase();
                            const total = extractUpnl(lastPayload || 0, SYM);
                            if (sideFromOpen === 'short') {
                                bd.short = total;
                                bd.hasShort = true;
                            } else {
                                bd.long = total;
                                bd.hasLong = true;
                            }
                        }

                    } catch (e) {}

                    // Pozisyon modunu çek (hedge / one_way) ve L/S satırı görünürlüğünü ayarla
                    let __mode = null;
                    try {
                        __mode = await fetchPositionMode(SYM);
                    } catch {}
                    // L/S satırları yalnızca hedge modda ve iki bacak da gerçekten varsa görünsün
                    const __showSplit = (__mode === 'hedge') && !!(bd.hasLong && bd.hasShort);
                    toggleUpnlSplitRows(__showSplit);
                    try {
                        updateModeChip(__mode);
                    } catch {}

                    // ——— uPnL label & tooltip metni (one_way → “Gerçekleşmemiş PnL”, hedge → “Gerçekleşmemiş PnL (L)”)
                    try {
                        const lbl = document.getElementById('qb-upnl-long-label');
                        const tip = document.getElementById('tt-upnl-l');
                        if (lbl) {
                            lbl.textContent = __showSplit ? 'Gerçekleşmemiş PnL (L)' : 'Gerçekleşmemiş PnL';
                        }
                        if (tip) {
                            tip.textContent = __showSplit ?
                                'Aktif sembolde long bacağın gerçekleşmemiş PnL değeri.' :
                                'Aktif sembolde gerçekleşmemiş PnL (toplam).';
                        }
                    } catch {}

                    // Sadece L/S satırları (toplam yok) — tek bir yerden güncelle
                    if (rowUpL && elUpL && rowUpS && elUpS) {
                        if (__showSplit) {
                            // HEDGE: bacakları ayrı ayrı yaz
                            if (bd.hasLong) {
                                const vL = Number(bd.long || 0);
                                elUpL.classList.remove('text-emerald-500', 'text-rose-400');
                                if (vL > 0) elUpL.classList.add('text-emerald-500');
                                else if (vL < 0) elUpL.classList.add('text-rose-400');
                                elUpL.textContent = (vL > 0 ? '+' : (vL < 0 ? '−' : '')) + nf2QB.format(Math.abs(vL));
                                rowUpL.classList.remove('hidden');
                            } else {
                                rowUpL.classList.add('hidden');
                            }
                            if (bd.hasShort) {
                                const vS = Number(bd.short || 0);
                                elUpS.classList.remove('text-emerald-500', 'text-rose-400');
                                if (vS > 0) elUpS.classList.add('text-emerald-500');
                                else if (vS < 0) elUpS.classList.add('text-rose-400');
                                elUpS.textContent = (vS > 0 ? '+' : (vS < 0 ? '−' : '')) + nf2QB.format(Math.abs(vS));
                                rowUpS.classList.remove('hidden');
                            } else {
                                rowUpS.classList.add('hidden');
                            }
                        } else {
                            // ONE-WAY: tek satırda TOPLAM unrealized (L satırı yeniden kullanılır)
                            const totalUpnl = Number(bd.long || 0) + Number(bd.short || 0);
                            elUpL.classList.remove('text-emerald-500', 'text-rose-400');
                            if (totalUpnl > 0) elUpL.classList.add('text-emerald-500');
                            else if (totalUpnl < 0) elUpL.classList.add('text-rose-400');
                            elUpL.textContent = (totalUpnl > 0 ? '+' : (totalUpnl < 0 ? '−' : '')) + nf2QB.format(Math.abs(totalUpnl));
                            rowUpL.classList.remove('hidden');
                            rowUpS.classList.add('hidden');
                        }
                    }

                } else {
                    if (elUpL) elUpL.textContent = '—';
                    if (elUpS) elUpS.textContent = '—';
                    if (rowUpL) rowUpL.classList.add('hidden');
                    if (rowUpS) rowUpS.classList.add('hidden');
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
                elNet.classList.remove('text-emerald-500', 'text-rose-400');
                if (net > 0) elNet.classList.add('text-emerald-500');
                else if (net < 0) elNet.classList.add('text-rose-400');

                // Cüzdan: backend’den sembole & exchange’e göre
                if (elWallet) {
                    let shown = null;
                    let isSim = false; // fallback mı?
                    try {
                        const ex = getActiveExchange(activeSymbol);
                        const qs = new URLSearchParams({
                            symbol: String(activeSymbol).toUpperCase()
                        });
                        if (ex) qs.set('exchange', ex);
                        qs.set('_', Date.now().toString()); // cache-buster
                        const r = await fetch('/api/me/balance?' + qs.toString(), {
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json',
                                'Cache-Control': 'no-store'
                            },
                            cache: 'no-store'
                        });
                        if (r.ok) {
                            const j = await r.json();
                            shown = Number(j?.available ?? j?.balance);
                        }
                    } catch {}
                    // Fallback: API ok değilse simülasyona düş → status=err göster
                    if (!Number.isFinite(shown)) {
                        if (!silent) showStatus('Bağlantı yok (simülasyon)', 'err');
                        const START_CAP = (typeof window.START_CAPITAL === 'number') ? window.START_CAPITAL : 1000;
                        shown = START_CAP + (Number(net) || 0);
                        isSim = true;
                    } else {
                        // gerçek bakiye → nötr renk
                        //            elWallet.classList.remove('text-emerald-500','text-rose-400');
                        // gerçek bakiye
                    }
                    // Renk ve metin: gerçek → nötr, simülasyon → gri + "≈"
                    elWallet.classList.remove('text-emerald-500', 'text-rose-400', 'text-slate-400');
                    if (isSim) elWallet.classList.add('text-slate-400');
                    elWallet.textContent = (isSim ? '≈ ' : '') + fmt2(shown || 0);
                    elWallet.title = isSim ?
                        'Canlı güncelleme başarısız' //'Simülasyon (balance API başarısız): START_CAPITAL + Net PnL'
                        :
                        'Aktif cüzdan bakiyesi';
                }
            } catch {}
        }
        // Açık pozisyon push sinyali geldiğinde sessiz güncelle
        document.addEventListener('sig:open-trades', () => loadQuickBalance({
            silent: true
        }));
        // İlk yükleme: activeSymbol hazır değilse bekle
        if (activeSymbol) loadQuickBalance({
            silent: true
        });
        else document.addEventListener('sig:active-ready', () => loadQuickBalance({
            silent: true
        }), {
            once: true
        });

        // Veri akışı kopukken de canlı tutmak için periyodik yedek tetikleyici
        setInterval(() => loadQuickBalance({
            silent: true
        }), Math.max(OPEN_TRADES_MS, 7000));
    })();

    // ==== Referans Kodu Modalı (frontend) ====
    (function wireReferralModal() {
        const btnOpen = document.getElementById('open-referral');
        const modal = document.getElementById('ref-modal');
        const form = document.getElementById('ref-form');
        const input = document.getElementById('ref-code');
        const btnCancel = document.getElementById('ref-cancel');
        const msg = document.getElementById('ref-msg');
        if (!btnOpen || !modal || !form || !input) return;

        // ok=true: başarı, ok=false: hata, ok=null: nötr bilgi
        function setMsg(t, ok = null) {
            if (!msg) return;
            // erişilebilirlik
            if (!msg.hasAttribute('role')) {
                msg.setAttribute('role', 'status');
                msg.setAttribute('aria-live', 'polite');
            }
            if (!t) { // boş mesaj: tamamen gizle
                msg.textContent = '';
                msg.className = 'hidden';
                return;
            }
            msg.textContent = t;
            const base = 'text-sm mt-2 px-2 py-1 rounded border font-medium tracking-wide ';
            // light: koyu metin + açık arka plan, dark: açık metin + yarı saydam arka plan
            let tone = 'text-sky-700 bg-sky-50 border-sky-200 dark:text-sky-200 dark:bg-sky-500/15 dark:border-sky-300/40'; // nötr
            if (ok === true) tone = 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-200 dark:bg-emerald-500/15 dark:border-emerald-300/40';
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
                return s.length > 160 ? s.slice(0, 157) + '…' : s;
            } catch {
                return `Hata ${status}`;
            }
        };

        btnOpen.addEventListener('click', () => {
            setMsg(''); // açılışta mesaj gizli
            input.value = '';
            if (modal.showModal) modal.showModal();
            else modal.style.display = 'block';
            setTimeout(() => input.focus(), 30);
        });
        btnCancel?.addEventListener('click', () => {
            setMsg(''); // kapatırken de gizle
            if (modal.close) modal.close();
            else modal.style.display = 'none';
        });
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const code = (input.value || '').trim().toUpperCase();
            if (!code) {
                setMsg('Kod boş olamaz', false);
                return;
            }
            // İstemci tarafı biçim kontrolü (backend de aynı regex ile doğruluyor)
            if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) {
                setMsg('Kod formatı geçersiz. Örn: AB12-CDEF-3456', false);
                return;
            }
            try {
                setMsg('Doğrulanıyor…', null); // nötr ton
                const r = await fetch('/referral/verify', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        code
                    })
                });
                if (!r.ok) {
                    let d = null;
                    try {
                        d = await r.json();
                    } catch {}
                    throw new Error(extractErrText(d, r.status));
                }
                setMsg('Başarılı. Yenileniyor…', true);
                setTimeout(() => location.reload(), 600);
            } catch (err) {
                setMsg(err?.message || 'Doğrulama başarısız', false);
            }
        });
    })();
})();

(function () {
  // DOM yüklendikten sonra çalış
  document.addEventListener("DOMContentLoaded", () => {
    const S = window.__SIGMOM__ || {};

    // --- Referral modal (UI) ---
    const refBtn = document.getElementById('open-referral');
    const modal = document.getElementById('ref-modal');
    const form  = document.getElementById('ref-form');
    const msg   = document.getElementById('ref-msg');

    if (refBtn && modal) {
      refBtn.addEventListener('click', () => modal.showModal());
    }

    if (form) {
      form.addEventListener('submit', async (e) => {
        // İptal butonu tıklandıysa
        if (e.submitter && e.submitter.value === 'close') {
          e.preventDefault();
          modal.close();
          if (msg) msg.textContent = '';
          form.reset();
          return; // burada dur
        }

        // Doğrula butonu → normal AJAX işlemi
        e.preventDefault();
        const code = (document.getElementById('ref-code').value || '').trim();
        if (!code) { msg.textContent = 'Kod boş olamaz.'; return; }
        msg.textContent = 'Doğrulanıyor...';
        try {
          const r = await fetch('/referral/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
          });
          if (r.ok) {
            msg.style.color = '#2bb673';
            msg.textContent = 'Başarılı! Sayfa yenileniyor...';
            setTimeout(() => location.reload(), 800);
          } else {
            const data = await r.json().catch(()=>({detail:'Geçersiz kod'}));
            msg.style.color = '#ffd793';
            msg.textContent = data.detail || 'Kod geçersiz veya tahsisli e-posta ile uyuşmuyor.';
          }
        } catch {
          msg.textContent = 'Ağ hatası. Lütfen tekrar deneyin.';
        }
      });
    }

    // --- Chart (read-only) ---
    const el = document.getElementById('chart');
    if (!el) return;

    // Kütüphane yüklendi mi?
    if (!window.LightweightCharts || typeof window.LightweightCharts.createChart !== 'function') {
      console.error('LightweightCharts yüklenemedi.');
      return;
    }

    const chart = LightweightCharts.createChart(el, {
      layout: { background: { color: '#111624' }, textColor: '#cbd5e1' },
      grid: { vertLines: { color: '#1c2335' }, horzLines: { color: '#1c2335' } },
      rightPriceScale: { borderColor: '#1c2335' },
      timeScale: { borderColor: '#1c2335' },
      crosshair: { mode: 1 },
      localization: { priceFormatter: v => v.toFixed(2) },
    });

    // === Responsive chart boyutlandırma (mobil dostu) ===
    function resizeChart() {
      const { clientWidth, clientHeight } = el;
      chart.resize(clientWidth, Math.max(260, clientHeight));
    }

    const ro = new ResizeObserver(() => resizeChart());
    ro.observe(el);

    window.addEventListener('orientationchange', () => {
      setTimeout(resizeChart, 200);
    });
    window.addEventListener('resize', () => {
      clearTimeout(window.__lwc_r_t);
      window.__lwc_r_t = setTimeout(resizeChart, 120);
    });

    resizeChart();

    // Bazı build'lerde addCandlestickSeries yerine addSeries(type) kullanılıyor
    const candleSeries = (typeof chart.addCandlestickSeries === 'function')
      ? chart.addCandlestickSeries()
      : chart.addSeries ? chart.addSeries({ type: 'Candlestick' }) : null;

    if (!candleSeries) {
      console.error('Candlestick serisi eklenemedi. API uyuşmazlığı.');
      return;
    }

    // Dummy data
    const now = Math.floor(Date.now()/1000);
    const seed = [];
    let p = 65000;
    for (let i=120; i>0; i--) {
      const t = now - i*60;
      const o = p + (Math.random()-0.5)*200;
      const c = o + (Math.random()-0.5)*200;
      const h = Math.max(o,c) + Math.random()*120;
      const l = Math.min(o,c) - Math.random()*120;
      seed.push({ time: t, open:o, high:h, low:l, close:c });
      p = c;
    }
    candleSeries.setData(seed);

    // Canlı veri göstergesi (şimdilik kapalı)
    const feedStatus = document.getElementById('feed-status');
    function setFeedStatus(s){ if(feedStatus){ feedStatus.textContent = 'Bağlantı: '+s; } }
    setFeedStatus('kapalı');

    // if (S.feedUrl) { ... }
  });
})();

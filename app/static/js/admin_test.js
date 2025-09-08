const WEBHOOK_URL = '/webhook';

/** DOM helpers (keep at top to avoid hoisting issues) */
const el = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);

/** Status */
async function refreshStatus(){
  try{
    const r = await fetch('/admin/test/status');
    const j = await r.json();
    const b = el('modeBadge');

    if(j.success){
      const ok = j.config_mode === j.exchange_mode;
      b.textContent = `Exchange Mode: ${j.exchange_mode} (cfg: ${j.config_mode})`;
      b.className = 'pill ' + (ok ? 'ok' : 'warn');
    }else{
      b.textContent = 'mode: unknown';
      b.className = 'pill err';
    }

    // Exchange bilgisini otomatik olarak set et (daha temiz versiyon)
    if (j.exchange) {
      el('exchangeDisplay').textContent = j.exchange;
      el('exchange').value = j.exchange;

      if (j.success) {
        el('exchangeStatus').textContent = '✓';
        el('exchangeStatus').className = 'pill ok';
      } else {
        el('exchangeStatus').textContent = '✗';
        el('exchangeStatus').className = 'pill err';
      }
      el('exchangeStatus').style.display = 'inline-block';
    } else {
      el('exchangeStatus').style.display = 'none';
    }

  }catch(_){
    const b = el('modeBadge');
    b.textContent = 'mode: error';
    b.className = 'pill err';
    el('exchangeStatus').style.display = 'none'; // Hata durumunda da tik'i gizle
  }
}
refreshStatus();

/** Time helpers */
function nowIsoUtc() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}
function fmtIsoUtc(d) {
  return new Date(d.getTime()).toISOString().replace(/\.\d{3}Z$/, 'Z');
}
function fmtIsoLocal(d) {
  const pad = n => String(n).padStart(2, '0');
  const y = d.getFullYear(), m = pad(d.getMonth() + 1), day = pad(d.getDate());
  const hh = pad(d.getHours()), mm = pad(d.getMinutes()), ss = pad(d.getSeconds());
  const off = -d.getTimezoneOffset(); // minutes; east is positive
  const sign = off >= 0 ? '+' : '-';
  const abs = Math.abs(off), oh = pad(Math.floor(abs / 60)), om = pad(abs % 60);
  return `${y}-${m}-${day}T${hh}:${mm}:${ss}${sign}${oh}:${om}`;
}
function nowIsoLocal() { return fmtIsoLocal(new Date()); }
function getTzMode() {
  const r = document.querySelector('input[name="tzmode"]:checked');
  return r ? r.value : 'local';
}
function nowIsoByMode() { return getTzMode() === 'utc' ? nowIsoUtc() : nowIsoLocal(); }

/** UI helpers */
function flash(elm) {
  if (!elm) return;
  elm.style.outline = '2px solid #10b981';
  setTimeout(() => (elm.style.outline = ''), 600);
}
function clampLev(v) {
  if (v == null || v === '') return null;
  let n = parseInt(v, 10);
  if (isNaN(n)) return null;
  if (n < 1) n = 1;
  if (n > 125) n = 125;
  return n;
}

/** Build payload from form controls */
function buildPayload() {
  const mode = qs('input[name="mode"]:checked').value;
  const side = qs('input[name="side"]:checked').value;

  const symbol = el('symbol').value.trim().toUpperCase();
  const position_size = parseFloat(el('position_size').value);
  const order_type = el('order_type').value.trim();
  const exchange = el('exchange').value;
  const timestamp = el('timestamp').value.trim();
  const fund_manager_id = el('fund_manager_id').value.trim();

  const leverage = clampLev(el('leverage').value);
  const entry_price = el('entry_price').value ? parseFloat(el('entry_price').value) : null;
  const exit_price  = el('exit_price').value  ? parseFloat(el('exit_price').value)  : null;

  const payload = {
    mode, side, symbol,
    position_size,
    order_type,
    exchange,
    timestamp,
    fund_manager_id
  };

  const posModeEl = document.getElementById('position_mode');
  if (posModeEl) {
    const val = posModeEl.value?.trim().toLowerCase();
    if (val === 'hedge' || val === 'one_way') {
      payload.position_mode = val;
    }
  }

  // timestamp varsa ekle (kullanıcı seçimi)
  if (timestamp) payload.timestamp = timestamp;

  // leverage sadece mode=open iken gönder
  if (mode === 'open' && leverage !== null) payload.leverage = leverage;
  if (entry_price !== null) payload.entry_price = entry_price;
  if (exit_price  !== null) payload.exit_price  = exit_price;

  return payload;
}

// mode değişince leverage alanını yönet (close => disable & temizle)
function syncLeverageState() {
  const isOpen = qs('input[name="mode"]:checked').value === 'open';
  const lev = el('leverage');
  lev.disabled = !isOpen;
}

/** Raw edit support */
function getPayloadFromRawOrInputs() {
  if (el('rawMode')?.checked) {
    const txt = el('rawPayload').value.trim() || '{}';
    try {
      return JSON.parse(txt);
    } catch (e) {
      throw new Error("Raw JSON parse error: " + e.message);
    }
  }
  return buildPayload();
}

/** Preview */
function refreshPreview() {
  const out = el('payloadOut');
  if (!out) return;
  try {
    const payload = getPayloadFromRawOrInputs();
    el('rawStatus').textContent = '';
    out.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    el('rawStatus').textContent = err.message || 'Raw JSON error';
  }
}

function setStatus(text, cls='') {
  const s = el('status');
  s.textContent = text;
  s.className = 'pill ' + cls;
}

function setRespBadge(ok) {
  const b = el('respBadge');
  b.textContent = ok ? 'success' : 'error';
  b.className = 'pill ' + (ok ? 'ok' : 'err');

  // 5 saniye sonra otomatik reset
  setTimeout(() => {
    b.textContent = '–';
    b.className = 'pill';
  }, 2000);
}

/** Send */
async function sendSignal() {
  let payload;
  try {
    payload = getPayloadFromRawOrInputs();
  } catch (e) {
    el('rawStatus').textContent = e.message || 'Raw JSON error';
    return;
  }

  if (el('sendUtc')?.checked && payload.timestamp) {
    const d = new Date(payload.timestamp);
    if (!isNaN(d)) {
      payload.timestamp = d.toISOString().replace(/\.\d{3}Z$/, 'Z');
    }
  }

  el('payloadOut').textContent = JSON.stringify(payload, null, 2);
  setStatus('sending…');
  el('btnSend').disabled = true;

  try {
    const res = await fetch(WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({ raw: 'no json' }));
    el('respOut').textContent = JSON.stringify(data, null, 2);
    setRespBadge(res.ok && (data.success !== false));
    setStatus('idle');
  } catch (e) {
    el('respOut').textContent = JSON.stringify({ error: String(e) }, null, 2);
    setRespBadge(false);
    setStatus('idle');
  } finally {
    el('btnSend').disabled = false;
  }
}

function applyTzModeToCurrentValue() {
  const ts = el('timestamp');
  const raw = ts.value.trim();
  let d = raw ? new Date(raw) : new Date();
  if (isNaN(d)) d = new Date(); // fallback
  ts.value = (getTzMode() === 'utc') ? fmtIsoUtc(d) : fmtIsoLocal(d);
  flash(ts);
  refreshPreview();
}

document.querySelectorAll('input[name="tzmode"]').forEach(r => {
  r.addEventListener('change', applyTzModeToCurrentValue);
});

document.querySelectorAll('input[name="mode"]').forEach(r => {
  r.addEventListener('change', () => {
    syncLeverageState();
    refreshPreview();
  });
});

document.querySelectorAll('input[name="side"]').forEach(r => {
  r.addEventListener('change', () => {
    refreshPreview();
  });
});

el('leverage').addEventListener('input', refreshPreview);
el('position_size').addEventListener('input', refreshPreview);
el('symbol').addEventListener('input', refreshPreview);
// timestamp canlı dinlensin → yazdıkça önizleme güncellensin
el('timestamp').addEventListener('input', refreshPreview);
el('entry_price').addEventListener('input', refreshPreview);
el('exit_price').addEventListener('input', refreshPreview);
el('order_type').addEventListener('change', refreshPreview);
el('position_mode').addEventListener('change', refreshPreview);

el('btnNow').addEventListener('click', (e) => {
  e.preventDefault();
  const ts = el('timestamp');
  ts.value = nowIsoByMode();
  flash(ts);
  refreshPreview();
});

el('btnSend').addEventListener('click', (e) => {
  e.preventDefault();
  if (!el('symbol').value.trim()) { alert('Symbol gerekli'); return; }
  if (!el('position_size').value.trim()) { alert('Position size gerekli'); return; }
  if (!el('fund_manager_id').value.trim()) { alert('Fund manager id gerekli'); return; }
  sendSignal();
});

el('btnReset').addEventListener('click', (e) => {
  e.preventDefault();
  el('symbol').value = 'BTCUSDT';
  el('position_size').value = '0.03';
  el('leverage').value = '';
  el('entry_price').value = '';
  el('exit_price').value = '';
  el('timestamp').value = nowIsoByMode();
  el('payloadOut').textContent = '{}';
  el('respOut').textContent = '{}';
  setRespBadge(true); setRespBadge(false);
  setStatus('idle');
  if (el('rawMode').checked) {
    el('rawPayload').value = JSON.stringify(buildPayload(), null, 2);
  }
  refreshPreview();
});

// Raw mode toggles
el('rawMode').addEventListener('change', () => {
  const ta = el('rawPayload');
  if (el('rawMode').checked) {
    try {
      const obj = buildPayload(); // from form
      ta.value = JSON.stringify(obj, null, 2);
      el('rawStatus').textContent = '';
    } catch (e) {
      ta.value = '{}';
      el('rawStatus').textContent = e.message || 'Raw init error';
    }
    ta.style.display = 'block';
  } else {
    ta.style.display = 'none';
  }
  refreshPreview();
});
el('rawPayload').addEventListener('input', () => {
  try {
    JSON.parse(el('rawPayload').value || '{}');
    el('rawStatus').textContent = '';
  } catch (e) {
    el('rawStatus').textContent = e.message;
  }
  refreshPreview();
});
el('btnFormat').addEventListener('click', () => {
  if (!el('rawMode').checked) return;
  try {
    const obj = JSON.parse(el('rawPayload').value || '{}');
    el('rawPayload').value = JSON.stringify(obj, null, 2);
    el('rawStatus').textContent = '';
  } catch (e) {
    el('rawStatus').textContent = e.message;
  }
});

syncLeverageState(); // ilk yüklemede doğru duruma getir
refreshPreview();

let statusInterval;

function startStatusPolling() {
  refreshStatus();
  statusInterval = setInterval(refreshStatus, 2000);
}

function stopStatusPolling() {
  if (statusInterval) {
    clearInterval(statusInterval);
  }
}

// Sayfa yüklendiğinde direkt başlat
document.addEventListener('DOMContentLoaded', function() {
  startStatusPolling();
});

// Visibility change için dinleyici
document.addEventListener('visibilitychange', function() {
  if (document.visibilityState === 'visible') {
    startStatusPolling();
  } else {
    stopStatusPolling();
  }
});

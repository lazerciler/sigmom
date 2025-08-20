// app/static/js/admin_test.js
    async function refreshStatus(){
    try{
      const r = await fetch('/admin/test/status');
      const j = await r.json();
      const b = document.getElementById('modeBadge');
      if(j.success){
        const ok = j.config_mode === j.exchange_mode;
        b.textContent = `mode: ${j.exchange_mode} (cfg: ${j.config_mode})`;
        b.className = 'pill ' + (ok ? 'ok' : 'warn');
      }else{
        b.textContent = 'mode: unknown';
        b.className = 'pill err';
      }
    }catch(_){
      const b = document.getElementById('modeBadge');
      b.textContent = 'mode: error';
      b.className = 'pill err';
    }
  }
  refreshStatus();

    const WEBHOOK_URL = '/webhook';

    const el = id => document.getElementById(id);
    const qs = sel => document.querySelector(sel);

    function nowIso() {
      return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
    }

    function clampLev(v) {
      if (v == null || v === '') return null;
      let n = parseInt(v, 10);
      if (isNaN(n)) return null;
      if (n < 1) n = 1;
      if (n > 125) n = 125;
      return n;
    }

    function buildPayload() {
      const mode = qs('input[name="mode"]:checked').value;
      const side = qs('input[name="side"]:checked').value;

      const symbol = el('symbol').value.trim().toUpperCase();
      const position_size = parseFloat(el('position_size').value);
      const order_type = el('order_type').value.trim();
      const exchange = el('exchange').value;
      const timestamp = el('timestamp').value.trim() || nowIso();
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
      if (leverage !== null) payload.leverage = leverage;
      if (entry_price !== null) payload.entry_price = entry_price;
      if (exit_price  !== null) payload.exit_price  = exit_price;

      return payload;
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
    }

    async function sendSignal() {
      const payload = buildPayload();
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

    // hooks
    el('btnNow').addEventListener('click', (e) => {
      e.preventDefault();
      el('timestamp').value = nowIso();
    });

    el('btnSend').addEventListener('click', (e) => {
      e.preventDefault();
      // client validation
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
      el('timestamp').value = nowIso();
      el('payloadOut').textContent = '{}';
      el('respOut').textContent = '{}';
      setRespBadge(true); setRespBadge(false); // reset
      setStatus('idle');
    });

    // init
    el('timestamp').value = nowIso();

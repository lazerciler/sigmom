// app/static/js/panel_boot.js
(() => {
  const root   = document.documentElement;
  const toBool = v => v === true || v === 'true' || v === 1 || v === '1';
  const read   = (camel, attr) => {
    const d = root.dataset ? root.dataset[camel] : undefined;
    return d != null ? toBool(d) : toBool(root.getAttribute(attr));
  };
  window.TRADES_ALLOWED = read('tradesAllowed', 'data-trades-allowed');
  window.EQUITY_ALLOWED = read('equityAllowed', 'data-equity-allowed');
  window.KPI_ALLOWED    = window.EQUITY_ALLOWED;
})();

// app/static/js/panel_head.js
// Sayfa boyanmadan önce tema
(() => {
  const t = localStorage.getItem('theme');
  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  if (t === 'dark' || (!t && prefersDark)) document.documentElement.classList.add('dark');
})();

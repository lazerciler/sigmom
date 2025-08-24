// app/static/js/admin_referrals_head.js
(function () {
  // 1) İlk boyamadan önce dark sınıfını bas (FOUT önler)
  var t = localStorage.getItem('theme');
  var prefersDark = false;
  try { prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches; } catch(_) {}

  var tw = (window.tailwind = window.tailwind || {});
  tw.config = { darkMode: 'class' };

  // 3) Tanılayıcı log
  // console.log('[head] config=', tw.config, 'html.hasDark=', document.documentElement.classList.contains('dark'));
})();

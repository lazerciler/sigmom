// app/static/js/theme_toggle.js
(function () {
  var btn = document.getElementById('themeToggle') ||
            document.querySelector('[data-theme-toggle]');
  if (!btn) return;
  if (!btn.hasAttribute('type')) btn.setAttribute('type', 'button');

  var root = document.documentElement;

  btn.setAttribute('aria-pressed', root.classList.contains('dark') ? 'true' : 'false');

  btn.addEventListener('click', function () {
    var isDark = root.classList.toggle('dark');
    btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');

    var val = isDark ? 'dark' : 'light';
    var maxAge = 60*60*24*365;
    var exp = new Date(Date.now() + maxAge*1000).toUTCString();
    var secure = (location.protocol === 'https:') ? '; Secure' : '';

    document.cookie = 'theme=' + val +
                      '; Path=/' +
                      '; Max-Age=' + maxAge +
                      '; Expires=' + exp +
                      '; SameSite=Lax' + secure;

    try { localStorage.setItem('theme', val); } catch (_) {}

//    const isPanel = document.documentElement.hasAttribute('data-equity-allowed');
//    if (isPanel) setTimeout(() => location.reload(), 0);
    const isPanel = document.documentElement.hasAttribute('data-equity-allowed');
    if (isPanel) {
      window.dispatchEvent(new CustomEvent('ui:theme', { detail: { isDark } }));
      setTimeout(() => location.reload(), 0);
    }
  });

  window.addEventListener('storage', function (e) {
    if (e.key !== 'theme') return;
    var dark = e.newValue === 'dark';
    root.classList.toggle('dark', dark);
    btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    window.dispatchEvent(new CustomEvent('ui:theme', { detail: { isDark: dark } }));
  });
})();

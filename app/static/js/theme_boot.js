// app/static/js/theme_boot.js
(function() {
    // 1) Cookie → 2) localStorage → 3) prefers-color-scheme
    function readCookie(name) {
        var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]*)'));
        return m ? decodeURIComponent(m[1]) : null;
    }
    var pref = readCookie('theme');
    if (!pref) {
        try {
            pref = localStorage.getItem('theme');
        } catch (_) {}
    }
    if (!pref && window.matchMedia) {
        pref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.classList.toggle('dark', pref === 'dark');
})();

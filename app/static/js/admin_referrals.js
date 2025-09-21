// app/static/js/admin_referrals.js
// Generate form — CSV/ZIP seçimleri (CSP: inline yasak, bu yüzden buradan bağlanır)
(function() {
    const form = document.getElementById('gen-form');
    if (!form) return;
    const mode = form.querySelector('input[name="mode"]');
    const zipBtn = document.getElementById('zip-download');
    const csvBtn = document.getElementById('csv-download');
    if (zipBtn && mode) zipBtn.addEventListener('click', () => {
        mode.value = 'zip';
    });
    if (csvBtn && mode) csvBtn.addEventListener('click', () => {
        mode.value = 'download';
    });
})();

// Assign formu — hata mesajı gösterimi (HTMX responseError hook'unu çağırıyor)
window.handleAssignError = function(e) {
    const msgEl = document.getElementById('assign-msg');
    let text = '';
    try {
        const json = JSON.parse(e.detail.xhr.responseText || '{}');
        text = json.detail || '';
    } catch (_) {}
    if (!text) text = e.detail.xhr.responseText || 'İşlem başarısız.';
    msgEl.textContent = text;
    msgEl.className = 'md:col-span-4 text-sm mt-1 text-rose-600';
};

// Assign formu — butonu alanlar dolana kadar kilitle + düz kodu normalize et
(function() {
    const form = document.getElementById('assign-form');
    if (!form) return;
    const idField = form.querySelector('[name="referral_id"]');
    const codeField = form.querySelector('input[name="plain_code"]');
    const submitBtn = document.getElementById('assign-submit');
    const msgEl = document.getElementById('assign-msg');

    function validate() {
        const ok = !!(idField.value && codeField.value && codeField.value.trim().length >= 8);
        submitBtn.disabled = !ok;
        if (msgEl) msgEl.textContent = '';
    }

    idField.addEventListener('change', validate);
    codeField.addEventListener('input', () => {
        codeField.value = codeField.value.toUpperCase().replace(/\s+/g, '');
        validate();
    });

    validate(); // ilk yükleme
})();

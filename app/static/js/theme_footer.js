// app/static/js/theme_footer.js

// Footer yılını ayarla (elemana sahip sayfalarda)
(() => {
    const el = document.getElementById('ft-year-b');
    if (el) el.textContent = new Date().getFullYear();
})();

(() => {
    const GUTTER = 12; // ekran kenarı güvenlik boşluğu (px)
    const GAP = 8; // ikon ile tooltip arası (px)

    function openTip(icon) {
        const tip = icon.querySelector('.tooltiptext');
        if (!tip) return;

        // ölçüm için önce görünür kıl (ama opak olmasın)
        tip.style.opacity = '0';
        icon.dataset.open = '1';

        requestAnimationFrame(() => {
            const irect = icon.getBoundingClientRect();

            // CSS var’larını temizleyip doğal boyutu ölç
            tip.style.removeProperty('--tt-left');
            tip.style.removeProperty('--tt-top');
            tip.style.removeProperty('--tt-arrow-x');
            tip.style.removeProperty('--tt-arrow-y');

            const tw = tip.offsetWidth;
            const th = tip.offsetHeight;

            const iconCx = irect.left + irect.width / 2;
            let left = iconCx - tw / 2;
            let top = irect.top - th - GAP;

            // Üstten taşarsa, aşağıya koy
            let below = false;
            if (top < GUTTER) {
                top = irect.bottom + GAP;
                below = true;
            }

            // Soldan/sağdan taşmayı engelle (clamp)
            const minL = GUTTER;
            const maxL = window.innerWidth - GUTTER - tw;
            left = Math.min(Math.max(left, minL), maxL);

            // Ok (arrow) koordinatları (viewport)
            const arrowX = Math.min(Math.max(iconCx, left + 8), left + tw - 8);
            const arrowY = below ? top : (top + th); // aşağıdaysa tip üstüne, yukarıdaysa tip altına

            // CSS değişkenlerini set et
            tip.style.setProperty('--tt-left', left + 'px');
            tip.style.setProperty('--tt-top', top + 'px');
            tip.style.setProperty('--tt-arrow-x', arrowX + 'px');
            tip.style.setProperty('--tt-arrow-y', arrowY + 'px');

            // Aşağıda mı? (ok yönünü CSS’te değiştirmek için işaretle)
            if (below) {
                tip.setAttribute('data-pos', 'below');
            } else {
                tip.removeAttribute('data-pos');
            }

            tip.style.opacity = '1';
        });
    }

    function closeTip(icon) {
        const tip = icon.querySelector('.tooltiptext');
        if (!tip) return;
        icon.removeAttribute('data-open');
        tip.removeAttribute('data-pos');
        tip.style.removeProperty('--tt-left');
        tip.style.removeProperty('--tt-top');
        tip.style.removeProperty('--tt-arrow-x');
        tip.style.removeProperty('--tt-arrow-y');
        tip.style.opacity = '';
    }

    function bind() {
        document.querySelectorAll('.tooltip > .circle-icon').forEach(icon => {
            // Mouse
            icon.addEventListener('mouseenter', () => openTip(icon));
            icon.addEventListener('mouseleave', () => closeTip(icon));
            // Klavye
            icon.addEventListener('focus', () => openTip(icon));
            icon.addEventListener('blur', () => closeTip(icon));
            // Dokunmatik: toggle
            icon.addEventListener('touchstart', (ev) => {
                if (ev.cancelable) ev.preventDefault();
                if (icon.dataset.open === '1') closeTip(icon);
                else openTip(icon);
            }, {
                passive: false
            });
        });

        // Dışarı tıklanınca kapat
        document.addEventListener('pointerdown', (e) => {
            const open = document.querySelector('.tooltip > .circle-icon[data-open="1"]');
            if (open && !open.contains(e.target)) closeTip(open);
        });

        // Resize/scroll'da yeniden hizala
        const reflow = () => {
            const open = document.querySelector('.tooltip > .circle-icon[data-open="1"]');
            if (open) openTip(open);
        };
        window.addEventListener('resize', reflow);
        window.addEventListener('scroll', reflow, {
            passive: true
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }
})();

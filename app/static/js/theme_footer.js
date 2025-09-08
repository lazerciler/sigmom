// app/static/js/theme_footer.js

// Yıl bilgisini dinamik olarak güncelle
document.getElementById('ft-year-b').textContent = new Date().getFullYear();

(() => {
  const GUTTER = 12;      // ekran kenarı güvenlik boşluğu
  const GAP    = 8;       // ikon ile tooltip arası

  function openTip(icon){
    const tip = icon.querySelector('.tooltiptext');
    if (!tip) return;

    // Önce görünür yapıp ölçmek için kısa süreli göster (ama ekrandan taşırma yok)
    tip.style.opacity = '0';
    icon.dataset.open = '1';

    // Bir sonraki frame'de ölç
    requestAnimationFrame(() => {
      const irect = icon.getBoundingClientRect();
      const tw = tip.offsetWidth;
      const th = tip.offsetHeight;

      // Hedef pozisyon: İKON MERKEZİ ÜZERİ
      const iconCx = irect.left + irect.width/2;
      let left = iconCx - tw/2;
      let top  = irect.top - th - GAP;

      // Üstten taşarsa aşağıya al
      if (top < GUTTER) top = irect.bottom + GAP;

      // Soldan/sağdan taşmayı clamp et
      const minL = GUTTER;
      const maxL = window.innerWidth - GUTTER - tw;
      left = Math.min(Math.max(left, minL), maxL);

      // Ok ucunun konumu (viewport koordinatı)
      const arrowX = Math.min(Math.max(iconCx, left + 8), left + tw - 8);
      const arrowY = top + th;  // kutunun alt kenarı

      // CSS değişkenlerini gönder
      tip.style.setProperty('--tt-left',  left + 'px');
      tip.style.setProperty('--tt-top',   top  + 'px');
      tip.style.setProperty('--tt-arrow-x', arrowX + 'px');
      tip.style.setProperty('--tt-arrow-y', arrowY + 'px');

      // görünür yap
      tip.style.opacity = '1';
    });
  }

  function closeTip(icon){
    const tip = icon.querySelector('.tooltiptext');
    if (!tip) return;
    icon.removeAttribute('data-open');
    tip.style.removeProperty('--tt-left');
    tip.style.removeProperty('--tt-top');
    tip.style.removeProperty('--tt-arrow-x');
    tip.style.removeProperty('--tt-arrow-y');
    tip.style.opacity = '';
  }

  function bind(){
    const icons = document.querySelectorAll('.tooltip > .circle-icon');
    icons.forEach(icon => {
      // Mouse
      icon.addEventListener('mouseenter', () => openTip(icon));
      icon.addEventListener('mouseleave', () => closeTip(icon));
      // Klavye
      icon.addEventListener('focus',    () => openTip(icon));
      icon.addEventListener('blur',     () => closeTip(icon));
      // Dokunmatik (toggle)
      icon.addEventListener('touchstart', (ev) => {
        ev.preventDefault();
        if (icon.dataset.open === '1') closeTip(icon); else openTip(icon);
      }, {passive:false});
    });

    // Dışarı tıklayınca kapat
    document.addEventListener('pointerdown', (e) => {
      const open = document.querySelector('.tooltip > .circle-icon[data-open="1"]');
      if (open && !open.contains(e.target)) closeTip(open);
    });

    // Resize/scroll sırasında açık olanı yeniden hizala
    const reflow = () => {
      const open = document.querySelector('.tooltip > .circle-icon[data-open="1"]');
      if (open) openTip(open);
    };
    window.addEventListener('resize', reflow);
    window.addEventListener('scroll', reflow, {passive:true});
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', bind);
  else
    bind();
})();

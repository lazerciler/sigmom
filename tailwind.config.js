/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/templates/**/*.{html,htm,jinja}',   // Jinja/HTML şablonların
    './app/static/js/**/*.{js,ts}',            // panel.js, panel_equity.js vs.
    './**/*.py',                               // Jinja sınıf literal'ları Python içinde olabilir
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  safelist: [
    // JS ile runtime eklediğin tonlar/renkler (panel.js’de kullanılıyor)
    { pattern: /(text|bg|border)-(slate|emerald|amber|indigo|sky|rose)-(50|100|200|300|400|500|600|700|800|900)/ },
    { pattern: /(dark:)?(text|bg|border)-(slate|emerald|amber|indigo|sky|rose)-(50|100|200|300|400|500|600|700|800|900)/ },
    // Chip/durum/utility varyasyonları
    { pattern: /(opacity|w|h|px|py|mx|my)-\d+/ },
  ],
}

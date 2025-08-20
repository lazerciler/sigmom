// tailwind.config.js
/** @type {import('tailwindcss').Config} */

// tailwind.config.js
module.exports = {
  content: [
    "./templates/**/*.html",
    "./app/static/js/**/*.js",      // JS içinde ürettiğimiz markup
    "./app/**/*.py"                 // (Jinja/Starlette kullanıyorsan faydalı)
  ],
  theme: { extend: {} },
  plugins: [],
  safelist: [
    'grid-cols-5',
    // ileride gerekirse:
    'grid-cols-6'
    // veya pattern kullan:
    // { pattern: /grid-cols-(5|6)/ }
  ]
};


//module.exports = {
//  darkMode: 'class',                       // ← kritik
//  content: [
//    './app/templates/**/*.html',
//    './app/static/js/**/*.js',
//  ],
//  theme: { extend: {} },
//  plugins: [],
//};

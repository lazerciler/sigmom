// tailwind.config.js
module.exports = {
  darkMode: 'class',
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js"
  ],
  theme: {
    extend: {
      maxWidth: {
        '8xl': '90rem',
        '9xl': '96rem'
      }
    }
  },
  plugins: [],
}
//// tailwind.config.js
//module.exports = {
//  darkMode: 'class',
//  content: [
//    "./app/templates/**/*.html",
//    "./app/static/js/**/*.js"
//  ],
//  theme:
//    { extend: {} },
//  },
//  plugins: [],
//  safelist: [
//    'grid-cols-5',
//    // ileride gerekirse:
//    'grid-cols-6'
//    // veya pattern kullan:
//    // { pattern: /grid-cols-(5|6)/ }
//  ]
//}

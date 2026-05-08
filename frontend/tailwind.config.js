/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"Share Tech Mono"', 'monospace'],
      },
      colors: {
        cyber: {
          bg:     '#05050f',
          panel:  '#0d0d1f',
          border: '#1a1a3a',
          cyan:   '#00e5ff',
          purple: '#b400ff',
          green:  '#00ff7f',
          yellow: '#ffd600',
          red:    '#ff1744',
        },
      },
      gridTemplateColumns: {
        '24': 'repeat(24, minmax(0, 1fr))',
      },
    },
  },
  plugins: [],
}

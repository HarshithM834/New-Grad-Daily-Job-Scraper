/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f8f9fb', ink: '#151e2b', muted: '#667181',
        line: '#dce1e7', brand: '#176d68', soft: '#ecf6f4',
      },
      borderRadius: { xl: '12px', lg: '9px' },
      fontFamily: { sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Arial', 'sans-serif'], mono: ['ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'] },
    },
  },
  plugins: [],
}
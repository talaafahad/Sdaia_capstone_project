/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          page: '#10122B',
          card: '#171B3D',
        },
        purple: {
          base: '#8174C9',
          active: '#9D7CFF',
          light: '#BEA9FF',
          tint: '#DFD4FF',
        },
        green: {
          base: '#5BCD84',
          light: '#93DEAE',
          tint: '#C9EED6',
        },
        text: {
          primary: '#F1F1F1',
          muted: '#B0B0B0',
          faint: '#616161',
        },
        status: {
          amber: '#D9A441',
          red: '#C0564B',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

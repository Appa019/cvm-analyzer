/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0A0A0A',
        muted: '#5E5E5E',
        rule: '#E5E5E5',
        // CVM Analyzer navy, taken from the app's own sidebar
        accent: '#0F3172',
      },
      fontFamily: {
        sans: ['Archivo', 'system-ui', 'sans-serif'],
      },
      maxWidth: { page: '1100px' },
    },
  },
  plugins: [],
}

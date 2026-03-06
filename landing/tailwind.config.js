/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  '#E6F5ED',
          100: '#CCE9DA',
          200: '#99D3B5',
          300: '#66BD90',
          400: '#33A76B',
          500: '#008A49',
          600: '#00703C',
          700: '#005A30',
          800: '#004424',
          900: '#002E18',
        },
        accent: {
          50:  '#E8F0FF',
          100: '#D1E1FF',
          200: '#A3C3FF',
          300: '#75A5FF',
          400: '#4787FF',
          500: '#116DFF',
          600: '#0E57CC',
          700: '#0A4199',
          800: '#072C66',
          900: '#031633',
        },
        surface: '#F0FAF5',
        border: '#D4E8DC',
      },
      fontFamily: {
        display: ['Wix Madefor Display', 'sans-serif'],
        sans: ['Wix Madefor Text', 'sans-serif'],
      },
      borderRadius: {
        card: '20px',
      },
      boxShadow: {
        glow:   '0 0 24px rgba(0, 112, 60, 0.18)',
        card:   '0 4px 24px rgba(0, 112, 60, 0.10), 0 1px 4px rgba(0, 112, 60, 0.07)',
        'card-hover': '0 8px 32px rgba(0, 112, 60, 0.16), 0 2px 8px rgba(0, 112, 60, 0.10)',
        sm:     '0 1px 3px rgba(0, 112, 60, 0.07), 0 1px 2px rgba(0, 112, 60, 0.04)',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in':    'fadeIn 0.5s ease-out forwards',
        'slide-up':   'slideUp 0.5s ease-out forwards',
        'float':      'float 6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-8px)' },
        },
      },
    },
  },
  plugins: [],
}

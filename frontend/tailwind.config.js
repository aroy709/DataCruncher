/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#f0f7ff',
          100: '#e0effe',
          200: '#b9dffd',
          500: '#3b9edd',
          600: '#2563eb',
          700: '#1d4ed8',
        },
      },
      animation: {
        'progress-stripe': 'progress-stripe 1s linear infinite',
        'fade-in': 'fade-in 0.4s ease-out',
      },
      keyframes: {
        'progress-stripe': {
          '0%': { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '40px 0' },
        },
        'fade-in': {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}

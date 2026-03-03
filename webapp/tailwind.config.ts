import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        cream: '#F7F6F3',
        ink: '#0C0C0C',
        muted: '#6B6B6B',
        border: '#E5E5E0',
        tan: '#E8D9C0',
      },
      fontFamily: {
        serif: ['Instrument Serif', 'Georgia', 'serif'],
        sans: ['Geist', 'Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        hero: ['4.5rem', { lineHeight: '1.05', letterSpacing: '-0.02em' }],
        display: ['3rem', { lineHeight: '1.1', letterSpacing: '-0.02em' }],
      },
    },
  },
  plugins: [],
}
export default config

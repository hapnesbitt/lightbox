/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // LightBox dark palette (matches Flask app's CSS variables)
        base:      '#0a0a10',
        card:      '#131318',
        'card-hover': '#181820',
        input:     '#1c1c25',
        thumb:     '#1a1a22',
        border:    '#21212e',
        'border-soft': '#1c1c28',
        txt:       '#dddde8',
        muted:     '#7070a0',
        faint:     '#3a3a55',
        accent:    '#7c7cf8',
        'accent-hover': '#a0a0fc',
        success:   '#34d399',
        danger:    '#f87171',
        warning:   '#fbbf24',
        info:      '#60a5fa',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['SFMono-Regular', 'JetBrains Mono', 'Consolas', 'monospace'],
      },
      borderRadius: {
        sm: '5px',
        DEFAULT: '8px',
        lg: '12px',
      },
      boxShadow: {
        sm: '0 2px 8px rgba(0,0,0,0.35)',
        md: '0 4px 20px rgba(0,0,0,0.55)',
        lg: '0 8px 32px rgba(0,0,0,0.70)',
      },
    },
  },
  plugins: [],
};

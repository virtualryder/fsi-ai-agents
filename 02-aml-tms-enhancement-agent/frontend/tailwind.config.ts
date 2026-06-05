import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // GitHub dark palette used throughout the app
        canvas: {
          DEFAULT: '#0d1117',
          overlay: '#161b22',
          subtle: '#21262d',
        },
        border: {
          DEFAULT: '#30363d',
          muted: '#21262d',
        },
        fg: {
          DEFAULT: '#f0f6fc',
          muted: '#8b949e',
          subtle: '#6e7681',
        },
        accent: {
          blue: '#58a6ff',
          green: '#3fb950',
          yellow: '#e3b341',
          red: '#f85149',
          purple: '#bc8cff',
        },
      },
      fontFamily: {
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config

import type { Config } from 'tailwindcss';

/**
 * Nablix Authoring Portal — Numera brand palette.
 * Mirrors Numera-ui/tailwind.config.ts so both apps share one design language.
 * Every colour has a fixed meaning; never use colour for decoration alone.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'focus-navy': '#1B2A4A', // Deep focus base — sidebar, dark panels
        'learning-blue': '#4169E1', // Learning emphasis — active node, links
        'slate-blue': '#4A6984', // Secondary structure — muted labels
        'ai-cyan': '#00B4D8', // AI guidance / connection
        'dark-cyan': '#008B8B', // Calm connection
        'highlight-amber': '#FF9F1C', // Key action — primary CTA
        'action-orange': '#F77F00', // Strong CTA — major action only
        'success-sage': '#8A9A86', // Completion / success
        ink: '#2B2D42', // Text primary
        'reading-surface': '#F4F6F9', // Panel canvas
        'off-white': '#FAFAFA', // Page background
        'muted-gray': '#E0E2E5', // Borders / inactive
        // Semantic validation colours (coverage grid + status)
        warn: '#FF9F1C',
        danger: '#E5484D',
        // Premium hybrid accent
        lime: '#CBF24A',
        'lime-deep': '#B4D62E',
        spotlight: '#0E1A33',
        page: '#EEF1F6',
      },
      fontFamily: {
        sans: ['var(--font-body)', '"Helvetica Neue"', 'system-ui', 'sans-serif'],
        display: ['var(--font-body)', '"Helvetica Neue"', 'sans-serif'],
        mono: ['var(--font-mono)', '"SF Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['11px', { lineHeight: '1.35' }],
        xl: ['22px', { lineHeight: '1.3' }],
        '2xl': ['28px', { lineHeight: '1.2' }],
        '3xl': ['36px', { lineHeight: '1.15' }],
      },
      borderRadius: {
        btn: '11px',
        card: '20px',
        pill: '999px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(11,16,32,0.04), 0 8px 24px rgba(11,16,32,0.06)',
      },
    },
  },
  plugins: [],
};

export default config;

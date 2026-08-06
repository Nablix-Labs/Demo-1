import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      // Numera brand palette — every colour has a fixed meaning.
      // Never use colour for decoration alone. (Brand Guidelines v1.0)
      colors: {
        'focus-navy':      '#1B2A4A', // Deep focus base — headers, dark panels
        'learning-blue':   '#4169E1', // Learning emphasis — active lesson, progress
        'slate-blue':      '#4A6984', // Secondary structure — side panels, cards
        'ai-cyan':         '#00B4D8', // AI guidance / connection — prompts, arrows
        'dark-cyan':       '#008B8B', // Calm connection — secondary concept flow
        'highlight-amber': '#FF9F1C', // Key formula / aha moment — primary CTA
        'action-orange':   '#F77F00', // Strong CTA — major action only
        'success-sage':    '#8A9A86', // Completion / success states
        'ink':             '#2B2D42', // Text primary — body text, labels
        'reading-surface': '#F4F6F9', // Main learning canvas — explanation cards
        'off-white':       '#FAFAFA', // High-whitespace surface — page background
        'muted-gray':      '#E0E2E5', // Borders / inactive — dividers, disabled

        // Book component (components/ui/book.tsx). Named for the design system
        // it came from so the component reads unmodified against its source.
        // `gray-200` is deliberately NOT redefined here: the original used its
        // own scale, and overriding Tailwind's would silently restyle every
        // other screen that uses bg-gray-200.
        'background-200':  '#FAFAFA',
        'gray-alpha-400':  'rgba(0,0,0,0.08)',
      },
      boxShadow: {
        book: '0 1px 1px 0 rgba(0,0,0,.02), 0 4px 8px -4px rgba(0,0,0,.1), 0 16px 24px -8px rgba(0,0,0,.03)',
        'book-border': 'inset 0 1px 2px 0 rgba(255,255,255,.3)',
      },
      backgroundImage: {
        // The lower half of a cover: paper catching light from above.
        'book-gradient': 'linear-gradient(180deg, #FFFFFF 0%, #F4F4F5 100%)',
      },
      fontFamily: {
        // Clean, readable sans-serif. Cognitive clarity over decorative fonts.
        sans: ['"Helvetica Neue"', 'Helvetica', 'Arial', 'sans-serif'],
      },
      // Brand type scale. lg/base/sm/xs already match Tailwind defaults
      // (18/16/14/12px), so only the heading + math steps are defined here.
      fontSize: {
        xl:          ['22px', { lineHeight: '1.3' }],  // Card heading
        '2xl':       ['28px', { lineHeight: '1.2' }],  // Main concept heading
        '3xl':       ['36px', { lineHeight: '1.15' }], // Hero concept title
        'math-base': ['24px', { lineHeight: '1.4' }],  // Inline math — min readable
        'math-lg':   ['40px', { lineHeight: '1.2' }],  // Large math
      },
      borderRadius: {
        btn:  '14px', // Button radius (brand: 12–16px)
        card: '16px', // Card radius
      },
    },
  },
  plugins: [],
};

export default config;

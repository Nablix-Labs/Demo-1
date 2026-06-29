import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Nablix design system tokens
        navy:    '#1B2A4A',
        cyan:    '#00B4D8',
        amber:   '#FF9F1C',
        sage:    '#8A9A86',
        slate:   '#4A6984',
        lblue:   '#4169E1',
        offwhite:'#FAFAFA',
        surface: '#F4F6F9',
        ink:     '#2B2D42',
        // Wireframe grays
        'wire-1': '#f4f4f4',
        'wire-2': '#eaeaea',
        'wire-3': '#dadada',
        'wire-text': '#7a7a7a',
        'wire-line': '#c8c8c8',
        'wire-strong': '#9a9a9a',
      },
      fontFamily: {
        sans: ['"Helvetica Neue"', 'Helvetica', 'Arial', 'sans-serif'],
        math: ['"Cambria Math"', 'Georgia', 'serif'],
        hand: ['"Comic Sans MS"', '"Bradley Hand"', '"Segoe Print"', 'cursive'],
      },
    },
  },
  plugins: [],
};

export default config;

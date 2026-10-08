import type { Config } from 'tailwindcss';

/**
 * The ResQMe design system (ResQMe/ios/ResQMe/UI/Theme.swift), on the web:
 * warm cream canvas, chunky rounded type, coral / teal / mustard blocks,
 * pastel stat tiles, large-radius cards and dark pill buttons.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#F8F5E4',
        'cream-deep': '#EFEBD3',
        card: '#FFFDF2',
        coral: '#EC6A84',
        'coral-soft': '#F7C9D2',
        teal: '#3D8C79',
        'teal-deep': '#2E6F60',
        'teal-soft': '#CFE3D6',
        mustard: '#F4B63F',
        'mustard-soft': '#FBE3A9',
        mint: '#DFE9C6',
        ink: '#1F1D1A',
        'ink-soft': '#6E6A60',
        line: '#E4DFC7',
        info: '#5B7FD6',
        'info-soft': '#D9E2F7',
        // Chart marks: deeper steps of teal / mustard / coral that pass the
        // palette validator (CVD ΔE ≥ 13.6). Always shown with a text label.
        correct: '#1F9A78',
        partial: '#E3A41E',
        incorrect: '#E65A78',
      },
      fontFamily: {
        sans: ['Nunito', 'ui-rounded', '"SF Pro Rounded"', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        card: '28px',
        tile: '22px',
      },
    },
  },
  plugins: [],
};

export default config;

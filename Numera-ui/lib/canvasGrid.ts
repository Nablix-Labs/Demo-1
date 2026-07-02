import type { CSSProperties } from 'react';
import type { CanvasGrid } from '@/store/useNumeraStore';

const LINE = '#E0E2E5'; // muted-gray

/** Background CSS for the drawing surface, per chosen paper style. */
export function gridBackground(grid: CanvasGrid): CSSProperties {
  switch (grid) {
    case 'plain':
      return {};
    case 'dots':
      return {
        backgroundImage: `radial-gradient(${LINE} 1.5px, transparent 1.6px)`,
        backgroundSize: '22px 22px',
      };
    case 'grid-sm':
      return {
        backgroundImage: `linear-gradient(${LINE} 1px, transparent 1px), linear-gradient(90deg, ${LINE} 1px, transparent 1px)`,
        backgroundSize: '16px 16px',
      };
    case 'grid-lg':
      return {
        backgroundImage: `linear-gradient(${LINE} 1px, transparent 1px), linear-gradient(90deg, ${LINE} 1px, transparent 1px)`,
        backgroundSize: '48px 48px',
      };
    case 'lines':
      return {
        backgroundImage: `linear-gradient(${LINE} 1px, transparent 1px)`,
        backgroundSize: '100% 32px',
      };
    case 'grid':
    default:
      return {
        backgroundImage: `linear-gradient(${LINE} 1px, transparent 1px), linear-gradient(90deg, ${LINE} 1px, transparent 1px)`,
        backgroundSize: '28px 28px',
      };
  }
}

export const GRID_OPTIONS: { id: CanvasGrid; label: string }[] = [
  { id: 'plain', label: 'Plain' },
  { id: 'lines', label: 'Lines' },
  { id: 'dots', label: 'Dots' },
  { id: 'grid-sm', label: 'Small grid' },
  { id: 'grid', label: 'Grid' },
  { id: 'grid-lg', label: 'Large grid' },
];

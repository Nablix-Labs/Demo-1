import { describe, it, expect } from 'vitest';
import { clampSupportWidth, SUPPORT_WIDTH_MIN, SUPPORT_WIDTH_DEFAULT } from '@/store/useNumeraStore';

describe('clampSupportWidth', () => {
  it('keeps a width inside the bounds', () => {
    expect(clampSupportWidth(360, 1440)).toBe(360);
  });
  it('never goes below the width a sticky note still reads at', () => {
    expect(clampSupportWidth(40, 1440)).toBe(SUPPORT_WIDTH_MIN);
  });
  it('caps at 40% of the window so the canvas keeps the middle', () => {
    expect(clampSupportWidth(5000, 1440)).toBe(576);
    expect(clampSupportWidth(5000, 400)).toBe(SUPPORT_WIDTH_MIN);
  });
  it('falls back to the default on garbage', () => {
    expect(clampSupportWidth(Number.NaN, 1440)).toBe(SUPPORT_WIDTH_DEFAULT);
  });
});

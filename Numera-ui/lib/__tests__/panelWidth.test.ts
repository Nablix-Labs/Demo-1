/**
 * Tutor panel width bounds.
 *
 * The width is dragged by the student and persisted, which is exactly the shape
 * of bug where a value set on one machine makes the app unusable on another. So
 * the clamp is checked here rather than trusted to the drag handler.
 */

import { describe, it, expect } from 'vitest';
import { clampPanelWidth, panelWidthMax, PANEL_WIDTH_MIN, PANEL_WIDTH_DEFAULT } from '@/store/useNumeraStore';

describe('clampPanelWidth', () => {
  it('keeps a sensible width as given', () => {
    expect(clampPanelWidth(320, 1440)).toBe(320);
  });

  it('will not shrink past the point where the chat stops being readable', () => {
    // Narrower than this the panel should be collapsed, not squeezed — that is
    // what the collapse control is for.
    expect(clampPanelWidth(40, 1440)).toBe(PANEL_WIDTH_MIN);
  });

  it('will not take more than half the window', () => {
    expect(clampPanelWidth(5000, 1440)).toBe(720);
  });

  it('rescues a width dragged wide on a big monitor and restored on a laptop', () => {
    // The persistence bug this exists for: 700px is fine at 1920 and would
    // leave the canvas a sliver at 1024, with the drag handle offscreen.
    const onBigMonitor = clampPanelWidth(700, 1920);
    expect(onBigMonitor).toBe(700);
    expect(clampPanelWidth(onBigMonitor, 1024)).toBe(512);
  });

  it('never inverts the bounds on a very narrow window', () => {
    // Half of 320 is below the minimum. Passing max < min to a naive clamp
    // returns the wrong end; the panel would come back narrower than readable.
    expect(clampPanelWidth(300, 320)).toBe(PANEL_WIDTH_MIN);
    expect(panelWidthMax(320)).toBe(PANEL_WIDTH_MIN);
  });

  it('falls back to the designed width rather than NaN', () => {
    expect(clampPanelWidth(Number.NaN, 1440)).toBe(PANEL_WIDTH_DEFAULT);
  });

  it('rounds, so panel text never lands on a half pixel', () => {
    expect(Number.isInteger(clampPanelWidth(300.4, 1440))).toBe(true);
  });
});

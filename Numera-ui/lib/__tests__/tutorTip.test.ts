import { describe, it, expect } from 'vitest';
import { tipFor } from '@/lib/tutorTip';
import type { TutorElement } from '@/store/useNumeraStore';

const W = 800;
const H = 600;

const el = (e: Partial<TutorElement> & { kind: TutorElement['kind'] }): TutorElement =>
  ({ id: 'x', ...e }) as TutorElement;

describe('tipFor', () => {
  describe('line and arrow', () => {
    const line = el({ kind: 'line', from: [0, 0], to: [1, 1] });

    it('starts at `from` and ends at `to`', () => {
      expect(tipFor(line, 0, W, H)).toEqual({ x: 0, y: 0 });
      expect(tipFor(line, 1, W, H)).toEqual({ x: W, y: H });
    });

    it('interpolates linearly, matching how TutorLayer draws the stroke', () => {
      expect(tipFor(line, 0.5, W, H)).toEqual({ x: W / 2, y: H / 2 });
    });

    it('treats an arrow the same as a line', () => {
      const arrow = el({ kind: 'arrow', from: [0.2, 0.4], to: [0.6, 0.4] });
      expect(tipFor(arrow, 0.5, W, H)).toEqual({ x: 0.4 * W, y: 0.4 * H });
    });
  });

  describe('rect', () => {
    // 0.5 wide, 0.5 tall from the origin => 400x300px, perimeter 1400
    const rect = el({ kind: 'rect', x: 0, y: 0, w: 0.5, h: 0.5 });

    it('opens and closes at the top-left corner', () => {
      expect(tipFor(rect, 0, W, H)).toEqual({ x: 0, y: 0 });
      expect(tipFor(rect, 1, W, H)).toEqual({ x: 0, y: 0 });
    });

    it('walks the perimeter clockwise', () => {
      // 400/1400 of the way round is the top-right corner
      expect(tipFor(rect, 400 / 1400, W, H)).toEqual({ x: 400, y: 0 });
      // a further 300 reaches the bottom-right
      expect(tipFor(rect, 700 / 1400, W, H)).toEqual({ x: 400, y: 300 });
    });
  });

  describe('ellipse', () => {
    const ellipse = el({ kind: 'ellipse', x: 0.5, y: 0.5, w: 0.5, h: 0.5 });

    it('starts at the rightmost point, as Konva traces it', () => {
      const t = tipFor(ellipse, 0, W, H)!;
      expect(t.x).toBeCloseTo(W / 2 + (0.5 * W) / 2);
      expect(t.y).toBeCloseTo(H / 2);
    });

    it('reaches the opposite side half way round', () => {
      const t = tipFor(ellipse, 0.5, W, H)!;
      expect(t.x).toBeCloseTo(W / 2 - (0.5 * W) / 2);
      expect(t.y).toBeCloseTo(H / 2);
    });
  });

  describe('freehand and highlight', () => {
    const points = [0, 0, 0.5, 0.5, 1, 1];
    const free = el({ kind: 'freehand', points });

    it('sits on the last revealed point', () => {
      expect(tipFor(free, 1, W, H)).toEqual({ x: W, y: H });
    });

    it('never runs ahead of the ink at p=0', () => {
      expect(tipFor(free, 0, W, H)).toEqual({ x: 0, y: 0 });
    });

    it('returns null when there are too few points to draw', () => {
      expect(tipFor(el({ kind: 'freehand', points: [0, 0] }), 1, W, H)).toBeNull();
      expect(tipFor(el({ kind: 'highlight', points: [] }), 1, W, H)).toBeNull();
    });
  });

  describe('text', () => {
    const text = el({ kind: 'text', text: 'y = 3', x: 0.25, y: 0.5, size: 20 });

    it('touches down at the left anchor, which is where the pen starts', () => {
      // jsdom has no canvas 2d context, so the glyph advance measures 0 and the
      // tip collapses to the anchor. The anchor is the part worth pinning here.
      expect(tipFor(text, 0, W, H)).toEqual({ x: 0.25 * W, y: 0.5 * H });
    });

    it('keeps the baseline fixed as the text types out', () => {
      expect(tipFor(text, 1, W, H)!.y).toBe(0.5 * H);
    });

    it('never moves left of the anchor', () => {
      expect(tipFor(text, 1, W, H)!.x).toBeGreaterThanOrEqual(0.25 * W);
    });
  });

  describe('progress clamping', () => {
    const line = el({ kind: 'line', from: [0, 0], to: [1, 1] });

    it('clamps out-of-range progress instead of extrapolating off-canvas', () => {
      expect(tipFor(line, -0.5, W, H)).toEqual({ x: 0, y: 0 });
      expect(tipFor(line, 2, W, H)).toEqual({ x: W, y: H });
    });
  });

  it('returns null for a kind it does not know, so the hand simply hides', () => {
    expect(tipFor(el({ kind: 'nonsense' as TutorElement['kind'] }), 0.5, W, H)).toBeNull();
  });
});

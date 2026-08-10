/**
 * tipFor — where the pen is touching down for a tutor mark at a given reveal
 * progress, in stage pixels.
 *
 * This is the geometry behind TutorHandOverlay: the writing hand is positioned
 * so its nib sits on this point. Kept as a pure function, separate from the
 * component, because it is the part worth testing — one case per mark kind,
 * plus the p=0 and p=1 boundaries.
 *
 * The maths deliberately mirrors what TutorLayer already does to draw each kind,
 * so the pen and the ink cannot disagree about where the mark currently ends.
 */

import type { TutorElement } from '@/store/useNumeraStore';

export type Point = { x: number; y: number };

/**
 * Text advances by the width of the glyphs revealed so far, so the tip needs a
 * real measurement rather than a proportion of the string — "l" and "W" are not
 * the same distance. Measured on a shared offscreen canvas and memoised by
 * font, since this runs every frame.
 */
let measureCtx: CanvasRenderingContext2D | null = null;
const widthCache = new Map<string, number>();

function measureText(text: string, fontSize: number): number {
  if (typeof document === 'undefined') return 0;
  const font = `${fontSize}px Helvetica, Arial, sans-serif`;
  const key = `${font}|${text}`;
  const hit = widthCache.get(key);
  if (hit !== undefined) return hit;

  if (!measureCtx) measureCtx = document.createElement('canvas').getContext('2d');
  if (!measureCtx) return 0;
  measureCtx.font = font;
  const w = measureCtx.measureText(text).width;
  // Bounded so a long session cannot grow this without limit.
  if (widthCache.size > 500) widthCache.clear();
  widthCache.set(key, w);
  return w;
}

/** Point at `t` (0→1) around a rectangle's perimeter, starting top-left. */
function pointOnRect(x: number, y: number, w: number, h: number, t: number): Point {
  const perim = 2 * (w + h);
  let d = t * perim;
  if (d <= w) return { x: x + d, y };
  d -= w;
  if (d <= h) return { x: x + w, y: y + d };
  d -= h;
  if (d <= w) return { x: x + w - d, y: y + h };
  d -= w;
  return { x, y: y + h - d };
}

/**
 * Konva traces an ellipse from its rightmost point, clockwise. Approximating
 * with the parametric angle rather than true arc length is imprecise on a very
 * eccentric ellipse, but the error is a few pixels on a shape being drawn in
 * under a second — not worth an elliptic integral.
 */
function pointOnEllipse(cx: number, cy: number, rx: number, ry: number, t: number): Point {
  const a = t * Math.PI * 2;
  return { x: cx + rx * Math.cos(a), y: cy + ry * Math.sin(a) };
}

export function tipFor(
  el: TutorElement,
  p: number,
  width: number,
  height: number,
): Point | null {
  const clamped = Math.max(0, Math.min(1, p));

  switch (el.kind) {
    case 'text': {
      const content = el.text ?? '';
      const fontSize = el.size ?? 14;
      const shown = content.slice(0, Math.round(content.length * clamped));
      return {
        x: (el.x ?? 0.5) * width + measureText(shown, fontSize),
        y: (el.y ?? 0.5) * height,
      };
    }

    case 'math': {
      // The typeset width is only known once KaTeX has laid out, so the overlay
      // tags its span with the element id and we read the real box. Before that
      // paint lands, the touch-down point is the only honest answer.
      const left = (el.x ?? 0.5) * width;
      const y = (el.y ?? 0.5) * height;
      if (typeof document === 'undefined') return { x: left, y };
      const node = document.querySelector<HTMLElement>(`[data-tutor-math-id="${el.id}"]`);
      const w = node?.getBoundingClientRect().width ?? 0;
      return { x: left + w * clamped, y };
    }

    case 'line':
    case 'arrow': {
      const from = el.from ?? [0, 0];
      const to = el.to ?? [0, 0];
      return {
        x: (from[0] + (to[0] - from[0]) * clamped) * width,
        y: (from[1] + (to[1] - from[1]) * clamped) * height,
      };
    }

    case 'rect':
      return pointOnRect(
        (el.x ?? 0) * width,
        (el.y ?? 0) * height,
        (el.w ?? 0) * width,
        (el.h ?? 0) * height,
        clamped,
      );

    case 'ellipse':
      return pointOnEllipse(
        (el.x ?? 0.5) * width,
        (el.y ?? 0.5) * height,
        ((el.w ?? 0) * width) / 2,
        ((el.h ?? 0) * height) / 2,
        clamped,
      );

    case 'freehand':
    case 'highlight': {
      const pts = el.points ?? [];
      if (pts.length < 4) return null;
      const count = Math.max(1, Math.ceil((pts.length / 2) * clamped));
      const i = (count - 1) * 2;
      return { x: pts[i] * width, y: pts[i + 1] * height };
    }

    default:
      return null;
  }
}

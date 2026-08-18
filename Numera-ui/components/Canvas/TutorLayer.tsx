'use client';

/**
 * TutorLayer — renders AI-tutor marks on their own non-interactive Konva layer
 * above the student's drawing. Elements arrive with NORMALISED 0–1 geometry
 * (see CanvasDrawPayload) and are scaled to the live stage size here, so the
 * backend stays resolution-independent.
 *
 * Each mark is revealed by its `progress` (0→1) from useTutorReveal, so it draws
 * on like handwriting instead of popping in: text types out, strokes draw from
 * start to tip, outlines trace around, freehand paths trace point by point.
 *
 * For written marks (`text`, and `math` in TutorMathOverlay) `x` is the LEFT edge
 * — where the pen touches down — because the producer can't know how wide the
 * rendered glyphs will be, and centring made the left edge unpredictable enough
 * to collide with whatever sits beside it. Pointing marks (`arrow`, `ellipse`,
 * `line`, `rect`) keep their documented anchors: they target a precise spot and
 * must not be nudged.
 *
 * v1 renders maths as real KaTeX via TutorMathOverlay (HTML); everything else is
 * Konva here.
 */

import { useEffect, useState } from 'react';
import { Layer, Text, Line, Arrow, Rect, Ellipse, Group } from 'react-konva';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';
import { useTutorReveal } from '@/store/useTutorReveal';
import { measureTutorTextBounds, clearTutorTextCache, tutorFontFamily } from '@/lib/tutorTip';

const INK = '#1B2A4A'; // focus-navy — readable AI-tutor ink default

/** Ramanujan approximation of an ellipse perimeter (for the draw-on dash). */
function ellipsePerimeter(rx: number, ry: number): number {
  const h = Math.pow((rx - ry) / (rx + ry || 1), 2);
  return Math.PI * (rx + ry) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
}

export default function TutorLayer({ width, height }: { width: number; height: number }) {
  const tutorElements = useNumeraStore((s) => s.tutorElements);
  const progress = useTutorReveal((s) => s.progress);

  // Konva paints to a bitmap, so it will happily render a mark in the fallback
  // face and never repaint when the real one arrives. Wait for the webfont,
  // bin the widths measured against the fallback, and draw once more.
  const [, setFontTick] = useState(0);
  useEffect(() => {
    let alive = true;
    document.fonts?.ready.then(() => {
      if (!alive) return;
      clearTutorTextCache();
      setFontTick((n) => n + 1);
    });
    return () => { alive = false; };
  }, []);

  // Map normalised pairs → pixel pairs
  const px = (pts: number[]) => pts.map((v, i) => (i % 2 === 0 ? v * width : v * height));

  const render = (el: TutorElement) => {
    const color = el.color ?? INK;
    const sw = el.strokeWidth ?? 2;
    const p = progress[el.id] ?? 0; // unknown id = not yet revealed

    switch (el.kind) {
      // `math` is rendered as real KaTeX by TutorMathOverlay (HTML), not here.
      case 'math':
        return null;
      case 'text': {
        const content = el.text ?? '';
        const fontSize = el.size ?? 14;
        const left = (el.x ?? 0.5) * width;
        const top = (el.y ?? 0.5) * height;
        // Wipe the ink in continuously rather than revealing whole characters.
        // Slicing the string made letters pop in one at a time, which reads as
        // typing; clipping by measured width lets each letter appear under the
        // nib as it is written. (See the `x` note in the file header: no
        // offsetX, so the mark occupies [x, x+width].)
        const { advance, overhangLeft, overhangRight } = measureTutorTextBounds(content, fontSize);
        const inked = advance * p;
        if (inked <= 0) return null;
        // Pad by the painted overhang so a slanted glyph is not shaved at either
        // edge. The right pad reveals a couple of pixels ahead of the nib, which
        // the nib itself covers.
        return (
          <Group
            key={el.id}
            clipX={left - overhangLeft}
            clipY={top - fontSize * 1.3}
            clipWidth={inked + overhangLeft + overhangRight}
            clipHeight={fontSize * 2.6}
          >
            <Text
              x={left}
              y={top}
              text={content}
              fontSize={fontSize}
              fontFamily={tutorFontFamily()}
              fill={color}
              offsetY={fontSize / 2}
            />
          </Group>
        );
      }
      case 'line':
      case 'arrow': {
        if (p <= 0) return null;
        const from = el.from ?? [0, 0];
        const to = el.to ?? [0, 0];
        // Draw from `from` toward `to` as p grows.
        const end: [number, number] = [
          from[0] + (to[0] - from[0]) * p,
          from[1] + (to[1] - from[1]) * p,
        ];
        const pts = px([...from, ...end]);
        return el.kind === 'arrow' ? (
          <Arrow key={el.id} points={pts} stroke={color} fill={color} strokeWidth={sw}
            pointerLength={10} pointerWidth={9} lineCap="round" />
        ) : (
          <Line key={el.id} points={pts} stroke={color} strokeWidth={sw} lineCap="round" />
        );
      }
      case 'rect': {
        if (p <= 0) return null;
        const w = (el.w ?? 0) * width;
        const h = (el.h ?? 0) * height;
        const perim = 2 * (w + h);
        return (
          <Rect key={el.id} x={(el.x ?? 0) * width} y={(el.y ?? 0) * height}
            width={w} height={h} stroke={color} strokeWidth={sw} cornerRadius={3}
            dash={[perim, perim]} dashOffset={perim * (1 - p)} />
        );
      }
      case 'ellipse': {
        // x,y = centre; w,h = full diameters
        if (p <= 0) return null;
        const rx = ((el.w ?? 0) * width) / 2;
        const ry = ((el.h ?? 0) * height) / 2;
        const perim = ellipsePerimeter(rx, ry);
        return (
          <Ellipse key={el.id} x={(el.x ?? 0.5) * width} y={(el.y ?? 0.5) * height}
            radiusX={rx} radiusY={ry} stroke={color} strokeWidth={sw}
            dash={[perim, perim]} dashOffset={perim * (1 - p)} />
        );
      }
      case 'freehand': {
        const pts = px(el.points ?? []);
        const shown = pts.slice(0, Math.ceil((pts.length / 2) * p) * 2);
        if (shown.length < 4) return null; // need at least two points
        return (
          <Line key={el.id} points={shown} stroke={color} strokeWidth={sw}
            tension={0.4} lineCap="round" lineJoin="round" />
        );
      }
      case 'highlight': {
        const pts = px(el.points ?? []);
        const shown = pts.slice(0, Math.ceil((pts.length / 2) * p) * 2);
        if (shown.length < 4) return null;
        return (
          <Line key={el.id} points={shown} stroke={el.color ?? '#FF9F1C'}
            strokeWidth={el.strokeWidth ?? 14} opacity={0.35} lineCap="round" lineJoin="round" />
        );
      }
      default:
        return null; // forward-compatible: ignore unknown kinds
    }
  };

  return <Layer listening={false}>{tutorElements.map(render)}</Layer>;
}

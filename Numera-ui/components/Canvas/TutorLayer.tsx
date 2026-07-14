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
 * v1 renders maths as real KaTeX via TutorMathOverlay (HTML); everything else is
 * Konva here.
 */

import { Layer, Text, Line, Arrow, Rect, Ellipse } from 'react-konva';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';
import { useTutorReveal } from '@/store/useTutorReveal';

const INK = '#1B2A4A'; // focus-navy — readable AI-tutor ink default

/** Ramanujan approximation of an ellipse perimeter (for the draw-on dash). */
function ellipsePerimeter(rx: number, ry: number): number {
  const h = Math.pow((rx - ry) / (rx + ry || 1), 2);
  return Math.PI * (rx + ry) * (1 + (3 * h) / (10 + Math.sqrt(4 - 3 * h)));
}

export default function TutorLayer({ width, height }: { width: number; height: number }) {
  const tutorElements = useNumeraStore((s) => s.tutorElements);
  const progress = useTutorReveal((s) => s.progress);

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
        // Type the text out left→right. offsetX stays keyed to the FULL width so
        // the final position matches and it grows rightward from a fixed anchor.
        const shown = content.slice(0, Math.round(content.length * p));
        const estW = content.length * fontSize * 0.55;
        return (
          <Text
            key={el.id}
            x={(el.x ?? 0.5) * width}
            y={(el.y ?? 0.5) * height}
            text={shown}
            fontSize={fontSize}
            fontFamily={'Helvetica, Arial, sans-serif'}
            fill={color}
            offsetX={estW / 2}
            offsetY={fontSize / 2}
          />
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

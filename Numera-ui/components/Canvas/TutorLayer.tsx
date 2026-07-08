'use client';

/**
 * TutorLayer — renders AI-tutor marks on their own non-interactive Konva layer
 * above the student's drawing. Elements arrive with NORMALISED 0–1 geometry
 * (see CanvasDrawPayload) and are scaled to the live stage size here, so the
 * backend stays resolution-independent.
 *
 * v1 renders maths as a Konva Text in a math font. True KaTeX typesetting
 * (HTML overlay or rasterised image) is a later upgrade — flagged in the spec.
 */

import { Layer, Text, Line, Arrow, Rect, Ellipse } from 'react-konva';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';

const INK = '#1B2A4A'; // focus-navy — readable AI-tutor ink default

export default function TutorLayer({ width, height }: { width: number; height: number }) {
  const tutorElements = useNumeraStore((s) => s.tutorElements);

  // Map normalised pairs → pixel pairs
  const px = (pts: number[]) => pts.map((v, i) => (i % 2 === 0 ? v * width : v * height));

  const render = (el: TutorElement) => {
    const color = el.color ?? INK;
    const sw = el.strokeWidth ?? 2;

    switch (el.kind) {
      // `math` is rendered as real KaTeX by TutorMathOverlay (HTML), not here.
      case 'math':
        return null;
      case 'text': {
        const content = el.text ?? '';
        const fontSize = el.size ?? 14;
        // Centre on (x, y): estimate width from glyph count.
        const estW = content.length * fontSize * 0.55;
        return (
          <Text
            key={el.id}
            x={(el.x ?? 0.5) * width}
            y={(el.y ?? 0.5) * height}
            text={content}
            fontSize={fontSize}
            fontFamily={'Helvetica, Arial, sans-serif'}
            fill={color}
            offsetX={estW / 2}
            offsetY={fontSize / 2}
          />
        );
      }
      case 'line':
        return (
          <Line key={el.id} points={px([...(el.from ?? [0, 0]), ...(el.to ?? [0, 0])])}
            stroke={color} strokeWidth={sw} lineCap="round" />
        );
      case 'arrow':
        return (
          <Arrow key={el.id} points={px([...(el.from ?? [0, 0]), ...(el.to ?? [0, 0])])}
            stroke={color} fill={color} strokeWidth={sw} pointerLength={10} pointerWidth={9} />
        );
      case 'rect':
        return (
          <Rect key={el.id} x={(el.x ?? 0) * width} y={(el.y ?? 0) * height}
            width={(el.w ?? 0) * width} height={(el.h ?? 0) * height}
            stroke={color} strokeWidth={sw} cornerRadius={3} />
        );
      case 'ellipse':
        // x,y = centre; w,h = full diameters
        return (
          <Ellipse key={el.id} x={(el.x ?? 0.5) * width} y={(el.y ?? 0.5) * height}
            radiusX={((el.w ?? 0) * width) / 2} radiusY={((el.h ?? 0) * height) / 2}
            stroke={color} strokeWidth={sw} />
        );
      case 'freehand':
        return (
          <Line key={el.id} points={px(el.points ?? [])} stroke={color} strokeWidth={sw}
            tension={0.4} lineCap="round" lineJoin="round" />
        );
      case 'highlight':
        return (
          <Line key={el.id} points={px(el.points ?? [])} stroke={el.color ?? '#FF9F1C'}
            strokeWidth={el.strokeWidth ?? 14} opacity={0.35} lineCap="round" lineJoin="round" />
        );
      default:
        return null; // forward-compatible: ignore unknown kinds
    }
  };

  return <Layer listening={false}>{tutorElements.map(render)}</Layer>;
}

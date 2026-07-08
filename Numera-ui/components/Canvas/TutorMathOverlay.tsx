'use client';

/**
 * TutorMathOverlay — renders tutor `math` elements as real KaTeX.
 *
 * Konva is pixel-canvas, so equations can't be typeset there. Instead we render
 * math tutor marks as an absolutely-positioned HTML layer over the Konva stage,
 * using the same normalised 0–1 coordinates scaled to the live canvas size. This
 * gives crisp, properly-typeset maths for anything the backend sends as
 * `{ kind: 'math', tex: '...' }`. Non-interactive so it never blocks drawing.
 * (KaTeX CSS is imported globally in app/globals.css.)
 */

import { InlineMath } from 'react-katex';
import { useNumeraStore } from '@/store/useNumeraStore';

export default function TutorMathOverlay({ width, height }: { width: number; height: number }) {
  const tutorElements = useNumeraStore((s) => s.tutorElements);
  const mathEls = tutorElements.filter((e) => e.kind === 'math');
  if (mathEls.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
      {mathEls.map((el) => (
        <span
          key={el.id}
          style={{
            position: 'absolute',
            left: (el.x ?? 0.5) * width,
            top: (el.y ?? 0.5) * height,
            transform: 'translate(-50%, -50%)',
            fontSize: el.size ?? 24,
            color: el.color ?? '#1B2A4A',
            whiteSpace: 'nowrap',
          }}
        >
          <InlineMath math={el.tex ?? el.text ?? ''} />
        </span>
      ))}
    </div>
  );
}

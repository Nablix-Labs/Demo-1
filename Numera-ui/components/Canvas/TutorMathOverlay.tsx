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
import { useTutorReveal } from '@/store/useTutorReveal';

export default function TutorMathOverlay({ width, height }: { width: number; height: number }) {
  const tutorElements = useNumeraStore((s) => s.tutorElements);
  const progress = useTutorReveal((s) => s.progress);
  const mathEls = tutorElements.filter((e) => e.kind === 'math');
  if (mathEls.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
      {mathEls.map((el) => {
        // KaTeX can't be typed glyph-by-glyph, so reveal it with a left→right
        // ink wipe: clip the right side away, then uncover it as p → 1.
        const p = progress[el.id] ?? 0;
        return (
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
              clipPath: `inset(-0.15em ${(1 - p) * 100}% -0.15em -0.15em)`,
              WebkitClipPath: `inset(-0.15em ${(1 - p) * 100}% -0.15em -0.15em)`,
            }}
          >
            <InlineMath math={el.tex ?? el.text ?? ''} />
          </span>
        );
      })}
    </div>
  );
}

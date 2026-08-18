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
 *
 * `x` is where the pen touches DOWN — the left edge — not the centre. Whoever
 * produces the coordinates cannot know how wide the typeset maths will end up,
 * so centring it made the left edge unpredictable and any neighbouring mark
 * (an arrow pointing at it, a previous line) a coin flip for overlapping. Anchor
 * left and the mark occupies [x, x+width]: the producer says "start writing
 * here" and knows what it is claiming. `y` stays the vertical centre.
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
        // KaTeX can't be typed glyph-by-glyph, so reveal it with a left→right ink
        // wipe. The edge is a short gradient rather than a hard cut: a straight
        // clip looks like a sheet sliding off finished text, whereas a soft leading
        // edge reads as ink arriving. FEATHER is in % of the element's own width,
        // and the gradient is offset so p=0 hides everything and p=1 shows all of
        // it (including the feather itself).
        const p = progress[el.id] ?? 0;
        const FEATHER = 7;
        const edge = p * (100 + FEATHER);
        const mask = `linear-gradient(90deg, #000 ${edge - FEATHER}%, rgba(0,0,0,0) ${edge}%)`;
        return (
          <span
            key={el.id}
            // The hand overlay measures this box to find the pen tip for maths.
            data-tutor-math-id={el.id}
            style={{
              position: 'absolute',
              left: (el.x ?? 0.5) * width,
              top: (el.y ?? 0.5) * height,
              transform: 'translateY(-50%)',
              fontSize: el.size ?? 24,
              color: el.color ?? '#1B2A4A',
              whiteSpace: 'nowrap',
              maskImage: mask,
              WebkitMaskImage: mask,
              // Tall content (a fraction, a big radical) can paint outside the
              // span's box. The mask area is the box exactly, so stretch it
              // vertically and centre it — otherwise those overhangs get shaved
              // off. Width stays 100%, so the gradient stops above are unaffected.
              maskSize: '100% 300%',
              WebkitMaskSize: '100% 300%',
              maskPosition: '0 center',
              WebkitMaskPosition: '0 center',
              maskRepeat: 'no-repeat',
              WebkitMaskRepeat: 'no-repeat',
            }}
          >
            <InlineMath math={el.tex ?? el.text ?? ''} />
          </span>
        );
      })}
    </div>
  );
}

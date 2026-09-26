'use client';

/**
 * CONNECT arrows between question tokens, from the canvas teaching plan.
 *
 * The tokens are HTML (AnchoredText tags each one `data-qtoken`), so the arrow
 * is drawn by `drawably` between the two live elements and follows them when
 * the question rewraps — the same reason the rest of the token marks are not
 * on the canvas. A connector whose token is not rendered draws nothing, and
 * the linked tokens also share an underline (AnchoredText).
 */

import { useEffect } from 'react';
import { drawablyArrow } from 'drawably';
import 'drawably/style.css';
import { TEACHING_COLORS } from '@/lib/canvasTeachingPlan';
import { useNumeraStore } from '@/store/useNumeraStore';

/** Below this centre-to-centre distance an arrow is too short to read. */
const MIN_ARROW_PX = 60;

function tokenElement(tokenId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-qtoken="${CSS.escape(tokenId)}"]`);
}

export default function TeachingConnectors() {
  const connectors = useNumeraStore((s) => s.teachingConnectors);

  useEffect(() => {
    const sketches = connectors.flatMap((c) => {
      const from = tokenElement(c.fromTokenId);
      const to = tokenElement(c.toTokenId);
      if (!from || !to || from === to) return [];
      // Neighbouring tokens (a stacked column of cases) leave an arrow a few
      // pixels long, which reads as a smudge. The shared underline AnchoredText
      // draws already says they belong together; the arrow is only for distance.
      const a = from.getBoundingClientRect();
      const b = to.getBoundingClientRect();
      if (Math.hypot(a.x - b.x, a.y - b.y) < MIN_ARROW_PX) return [];
      const sketch = drawablyArrow(from, to, { boil: 0, width: 2, stroke: TEACHING_COLORS[c.color] });
      // drawably appends the arrow to <body> at z-index 1, which puts it UNDER
      // the question strip (z-10) it is meant to point across. Lift it.
      const svg = document.body.lastElementChild;
      if (svg instanceof SVGElement && svg.classList.contains('drawably-arrow')) {
        svg.style.zIndex = '30';
        svg.style.pointerEvents = 'none';
      }
      return [sketch];
    });
    return () => sketches.forEach((sketch) => sketch.destroy());
  }, [connectors]);

  return null;
}

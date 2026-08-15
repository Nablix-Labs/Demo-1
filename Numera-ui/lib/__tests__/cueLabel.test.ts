/**
 * What the amber note calls itself.
 *
 * Mirrors the rule in components/VisualCue.tsx. Kept as a pure function so both
 * reports it has to satisfy are pinned as cases, because they contradict each
 * other on the surface and the next person to read one of them will be tempted
 * to flip the default back:
 *
 *   Manjusha, 10 Aug — hints were titled "Visual cue"; they are not cues.
 *   Sanya, 13 Aug    — authored cues were titled "Hint"; they are not hints.
 *
 * Neither can be settled by `cue_type` (null on every real Topic 1 cue) nor by
 * whether the client holds a card (VISUAL_CUE_CARDS is five linear-equation
 * demo entries and matches no authored content).
 */

import { describe, it, expect } from 'vitest';
import { cueLabel } from '@/lib/cueLabel';

describe('cueLabel', () => {
  it('uses the authored card title when the client has one', () => {
    expect(cueLabel({ cardTitle: 'Equation balance', cueId: null })).toBe('Equation balance');
  });

  it('calls a backend-served cue a visual cue (Sanya, 13 Aug)', () => {
    // The real payload: an id, and no cue_type at all.
    expect(cueLabel({ cardTitle: null, cueId: 'VC-T01-ADD-NOT-MULTIPLY' })).toBe('Visual cue');
    expect(cueLabel({ cardTitle: null, cueId: 'VC-T01-OPERATOR-SLOT' })).toBe('Visual cue');
  });

  it('calls the tutor\'s own guidance text a hint (Manjusha, 10 Aug)', () => {
    // No cue_id: nothing was served from the cue catalogue, so this note is the
    // hint rung of the support ladder.
    expect(cueLabel({ cardTitle: null, cueId: null })).toBe('Hint');
  });

  it('prefers the card title over both', () => {
    expect(cueLabel({ cardTitle: 'Inverse operations', cueId: 'VC-T01-X' }))
      .toBe('Inverse operations');
  });
});

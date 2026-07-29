/**
 * The frontend must not invent cue content.
 *
 * resolveCueCard used to return a DEFAULT_CUE card for any cue_type it did not
 * recognise, so a cue the backend never authored — or authored with a new type
 * we hadn't added artwork for — rendered a fixed worked example about an
 * unrelated equation. To a student that is indistinguishable from the tutor
 * showing them the wrong guidance, and Phase 2 handoff §9 forbids it: never
 * derive support content from hardcoded frontend examples.
 */

import { describe, it, expect } from 'vitest';
import { resolveCueCard, VISUAL_CUE_CARDS } from '@/lib/visualCueCards';

describe('resolveCueCard', () => {
  it('returns the card for a cue_type we have artwork for', () => {
    const known = Object.keys(VISUAL_CUE_CARDS)[0];
    expect(resolveCueCard(known)).toBe(VISUAL_CUE_CARDS[known as keyof typeof VISUAL_CUE_CARDS]);
  });

  it('returns null for an unknown cue_type instead of a stand-in card', () => {
    expect(resolveCueCard('SOME_NEW_BACKEND_CUE')).toBeNull();
  });

  it('returns null when the backend sent no cue_type at all', () => {
    expect(resolveCueCard(null)).toBeNull();
    expect(resolveCueCard(undefined)).toBeNull();
    expect(resolveCueCard('')).toBeNull();
  });
});

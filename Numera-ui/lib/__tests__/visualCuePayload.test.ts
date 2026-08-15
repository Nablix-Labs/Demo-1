/**
 * The visual cue as the backend actually sends it.
 *
 * Two reports pull in opposite directions and both are correct:
 *
 *   Manjusha, 10 Aug — hints were being titled "Visual cue".
 *   Sanya, 13 Aug    — "we still cant see a cue ... even for the typed message
 *                       it says as hint even if it was a cue".
 *
 * The old rule labelled by whether the CLIENT had a hardcoded card, and
 * VISUAL_CUE_CARDS only covers five linear-equation demo types. Every authored
 * Topic 1 cue (VC-T01-…) therefore fell through to "Hint" — Sanya's bug — while
 * the tutor's own guidance text, which also has no card, correctly read "Hint".
 *
 * The discriminator is `cue_id`: present means the Student Model served an
 * authored cue, absent means this is the tutor's own words. `cue_type` cannot
 * do this job — it is null on the real cues.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { applyInteractionSupport, type SupportPresentation } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

/** A cue exactly as the Student Model serves it for Topic 1. */
function cueResponse(cue: Record<string, unknown> | null): SupportPresentation {
  return {
    message: 'Look at what changes between the examples.',
    support_message: null,
    show_visual_cue: cue !== null,
    visual_cue: cue as never,
    show_scaffold_panel: undefined,
    scaffold_id: null,
    current_scaffold_step_id: null,
    scaffold_step_number: null,
    scaffold_step_text: null,
    scaffold_step_voice: null,
    total_scaffold_steps: null,
  } as unknown as SupportPresentation;
}

const cue = (over: Record<string, unknown> = {}) => ({
  show: true,
  cue_id: 'VC-T01-ADD-NOT-MULTIPLY',
  cue_type: null,
  description: 'Notice the number added stays the same each time.',
  ...over,
});

describe('visual cue payload', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      visualCueVisible: false,
      visualCueId: null,
      visualCueType: null,
      visualCueDescription: null,
      visualCueAssetUrl: null,
      visualCueActions: null,
    });
  });

  it('stores the whole cue the backend sent', () => {
    applyInteractionSupport(cueResponse(cue({
      asset_url: 'https://nablixmathvideos.blob.core.windows.net/cues/VC-T01.png',
      actions: [{ type: 'HIGHLIGHT', target: 'n' }],
    })));
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueId).toBe('VC-T01-ADD-NOT-MULTIPLY');
    expect(s.visualCueDescription).toBe('Notice the number added stays the same each time.');
    expect(s.visualCueAssetUrl)
      .toBe('https://nablixmathvideos.blob.core.windows.net/cues/VC-T01.png');
    expect(s.visualCueActions).toEqual([{ type: 'HIGHLIGHT', target: 'n' }]);
  });

  it('keeps cue_id even though cue_type is null', () => {
    // The real Topic 1 cues carry no cue_type. Identity has to survive that.
    applyInteractionSupport(cueResponse(cue()));
    expect(useNumeraStore.getState().visualCueId).toBe('VC-T01-ADD-NOT-MULTIPLY');
    expect(useNumeraStore.getState().visualCueType).toBeNull();
  });

  it('treats a blank cue_id as no cue_id', () => {
    applyInteractionSupport(cueResponse(cue({ cue_id: '  ' })));
    expect(useNumeraStore.getState().visualCueId).toBeNull();
  });

  it('holds the cue across a reply that serves no new support', () => {
    // Sanya's point 6, and the reason cues vanished mid-question: a later reply
    // carries show_visual_cue:false because it served nothing NEW, not because
    // the cue is over.
    applyInteractionSupport(cueResponse(cue()));
    applyInteractionSupport(cueResponse(null));
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueId).toBe('VC-T01-ADD-NOT-MULTIPLY');
  });

  it('drops the whole cue when the question changes', () => {
    applyInteractionSupport(cueResponse(cue({ asset_url: 'https://nablixmathvideos.blob.core.windows.net/c.png' })));
    useNumeraStore.getState().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-007',
      questionText: 'Next one.',
    });
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(false);
    expect(s.visualCueId).toBeNull();
    expect(s.visualCueAssetUrl).toBeNull();
    expect(s.visualCueActions).toBeNull();
  });
});

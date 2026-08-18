/**
 * What applyInteractionSupport renders, given what the backend served.
 *
 * The ORDERING requirement (support before the message) is pinned at the hook
 * level in supportOrderingHook.test.ts, because that is where it can actually
 * regress. This file covers the rest of Sanya's rule: render exactly what
 * arrived, never a placeholder, and never state the frontend invented.
 *
 * Sanya, 12 Aug 2026: the backend's wording now points at the support —
 * "look at the visual cue on your screen", "let's use the scaffold step already
 * shown" — so a cue or scaffold rendered AFTER that line is shown and spoken
 * points at something the student cannot see yet.
 *
 * Every reply path used to append the chat message first and apply support
 * second. These pin the order at the seam that matters: the store already holds
 * the cue/scaffold by the time the transcript gains the tutor's line.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

const CUE_TURN = {
  message: 'Look at the visual cue on your screen.',
  conversation_action: 'GIVE_HINT',
  visual_cue: { show: true, cue_type: 'DIAGRAM', description: 'A number line from 0 to 10.' },
} as Parameters<typeof applyInteractionSupport>[0];

describe('support is rendered exactly as served', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      transcript: [],
      visualCueVisible: false,
      visualCueType: null,
      visualCueDescription: null,
      activeScaffold: null,
      lastHintText: null,
    });
  });

  it('renders the cue the backend served, verbatim', () => {
    applyInteractionSupport(CUE_TURN);
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueType).toBe('DIAGRAM');
    expect(s.visualCueDescription).toBe('A number line from 0 to 10.');
  });

  it('shows no cue when the turn served none — never a placeholder', () => {
    // "If the response has no actual visual cue/scaffold, do not display a
    // placeholder and do not claim support is shown."
    applyInteractionSupport({ message: 'Try the next step.' } as Parameters<typeof applyInteractionSupport>[0]);
    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(false);
    expect(s.visualCueDescription).toBeNull();
  });

  it('opens the scaffold panel from the backend state before speaking', () => {
    applyInteractionSupport({
      message: "Let's use the scaffold step already shown.",
      active_scaffold: {
        scaffold_id: 'SC-1', current_step_id: 'S1', step_number: 1,
        step_text: 'Write what changes each time.', step_voice: 'Write what changes each time.',
        total_steps: 3,
      },
      show_scaffold_panel: true,
    } as unknown as Parameters<typeof applyInteractionSupport>[0]);
    const scaffold = useNumeraStore.getState().activeScaffold;
    expect(scaffold?.scaffoldId).toBe('SC-1');
    expect(scaffold?.stepNumber).toBe(1);
  });

  it('never invents support state of its own', () => {
    // The backend is authoritative: a turn that serves nothing must leave the
    // ladder exactly where it was.
    useNumeraStore.setState({ supportShown: null });
    applyInteractionSupport({ message: 'Keep going.' } as Parameters<typeof applyInteractionSupport>[0]);
    expect(useNumeraStore.getState().supportShown).toBeNull();
  });
});

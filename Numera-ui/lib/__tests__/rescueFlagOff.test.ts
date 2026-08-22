/**
 * With the presentation flag off, rescue actions must be ignored entirely.
 *
 * Its own file because the flag is read once at module load, so it cannot be
 * varied inside a suite that has already imported the store with it on.
 *
 * The failure this guards against is the quiet one: the backend half gets
 * enabled first, rescue actions start arriving, and a client that half-rendered
 * them would show a walkthrough with a "Next step" button that nothing on the
 * other side has agreed to answer.
 */

import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/runtimeConfig', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/runtimeConfig')>()),
  canvasRescuePresentationEnabled: false,
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');

describe('canvas rescue presentation disabled', () => {
  it('ignores rescue actions and leaves the board alone', () => {
    useNumeraStore.setState({
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-1',
      rescueSteps: [],
      tutorElements: [],
      pendingRescueActions: [],
    });
    useNumeraStore.getState().applyTutorCanvasActions([{
      action_id: 'TURN-1:1:SHOW_PARALLEL:R1:1',
      type: 'SHOW_PARALLEL',
      target_kind: 'TUTOR_ANCHOR',
      target_object_id: 'TUTOR_ANCHOR:RESCUE:R1:STEP:1',
      confirmed_component_id: null,
      text: 'Start with p, then add 3.',
      source_id: 'PE-1',
      answer_reveal_allowed: false,
      rescue_id: 'R1',
      step_index: 1,
      total_steps: 3,
      presentation_mode: 'PARALLEL',
      return_target_object_id: 'TUTOR_ANCHOR:ORIGINAL:Q-1',
    }]);
    const s = useNumeraStore.getState();
    expect(s.rescueSteps).toEqual([]);
    expect(s.tutorElements).toEqual([]);
    // Not queued either: nothing later in the session turns the flag on.
    expect(s.pendingRescueActions).toEqual([]);
  });
});

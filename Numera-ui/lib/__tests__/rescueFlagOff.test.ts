/**
 * Rescue actions are backend-authoritative. A client must render a valid rescue
 * action whenever it receives one, regardless of its build-time environment.
 */

import { describe, it, expect } from 'vitest';

const { useNumeraStore } = await import('@/store/useNumeraStore');

describe('canvas rescue presentation', () => {
  it('renders a server-authorised rescue action', () => {
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
    expect(s.rescueSteps).toHaveLength(1);
    expect(s.rescueSteps[0]?.text).toBe('Start with p, then add 3.');
    expect(s.tutorElements).toHaveLength(0);
    expect(s.pendingRescueActions).toEqual([]);
  });
});

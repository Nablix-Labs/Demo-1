import { describe, it, expect, beforeEach } from 'vitest';
import { applyInteractionSupport, type SupportPresentation } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

function turn(over: Partial<SupportPresentation> = {}): SupportPresentation {
  return { message: 'Have another look at the operation.', ...over } as SupportPresentation;
}

beforeEach(() => {
  useNumeraStore.setState({
    lastHintText: null,
    supportShown: null,
    activeQuestionId: 'Q-T01-001',
    currentPhase: 'GUIDED_PRACTICE',
  });
});

describe('capturing the hint rung off a turn (§6)', () => {
  it('remembers a GIVE_HINT message as the hint', () => {
    // /hint/request no longer exists, so a GIVE_HINT turn IS the hint.
    applyInteractionSupport(turn({ conversation_action: 'GIVE_HINT' }));
    expect(useNumeraStore.getState().lastHintText).toBe('Have another look at the operation.');
  });

  it('does not treat an ordinary reply as a hint', () => {
    applyInteractionSupport(turn({ conversation_action: 'ACKNOWLEDGE_ANSWER' }));
    expect(useNumeraStore.getState().lastHintText).toBeNull();
  });

  it('does not treat a missing action as a hint', () => {
    applyInteractionSupport(turn());
    expect(useNumeraStore.getState().lastHintText).toBeNull();
  });

  it('ignores a GIVE_HINT turn with no message', () => {
    applyInteractionSupport(turn({ conversation_action: 'GIVE_HINT', message: '' }));
    expect(useNumeraStore.getState().lastHintText).toBeNull();
  });

  it('a later hint replaces the earlier one', () => {
    applyInteractionSupport(turn({ conversation_action: 'GIVE_HINT', message: 'Hint one.' }));
    applyInteractionSupport(turn({ conversation_action: 'GIVE_HINT', message: 'Hint two.' }));
    expect(useNumeraStore.getState().lastHintText).toBe('Hint two.');
  });
});

describe('the ladder resets with the question', () => {
  it('keeps an authorised visual cue through later scaffold turns', () => {
    useNumeraStore.setState({
      visualCueVisible: true,
      visualCueType: null,
      visualCueDescription: 'Notice which part changes and which part stays fixed.',
    });

    applyInteractionSupport(turn({ show_visual_cue: false }));

    const s = useNumeraStore.getState();
    expect(s.visualCueVisible).toBe(true);
    expect(s.visualCueDescription).toBe(
      'Notice which part changes and which part stays fixed.',
    );
  });

  it('drops the hint and the climbed rung when the question changes', () => {
    useNumeraStore.setState({ lastHintText: 'Hint for Q1.', supportShown: 'SCAFFOLD' });

    useNumeraStore.getState().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-002',
      questionText: 'In m + 7, identify the changing quantity.',
    });

    // Carrying these forward would start the next question's "Need help?" at the
    // scaffold, skipping the hint the student should get first.
    const s = useNumeraStore.getState();
    expect(s.lastHintText).toBeNull();
    expect(s.supportShown).toBeNull();
  });

  it('keeps them while the student is still on the same question', () => {
    useNumeraStore.setState({ lastHintText: 'Hint for Q1.', supportShown: 'HINT' });

    useNumeraStore.getState().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-001',
      questionText: '',
    });

    const s = useNumeraStore.getState();
    expect(s.lastHintText).toBe('Hint for Q1.');
    expect(s.supportShown).toBe('HINT');
  });

  it('drops them when the phase changes', () => {
    useNumeraStore.setState({ lastHintText: 'Guided hint.', supportShown: 'VISUAL_CUE' });

    useNumeraStore.getState().applyBackendPhase({
      phase: 'INDEPENDENT_PRACTICE',
      questionId: 'Q-T01-001',
      questionText: '',
    });

    const s = useNumeraStore.getState();
    expect(s.lastHintText).toBeNull();
    expect(s.supportShown).toBeNull();
  });
});

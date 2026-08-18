/**
 * The bottom two rungs of the support ladder.
 *
 * `guided_rescue` has been typed in lib/api.ts and rendered nowhere (gap C7).
 * So a student who worked all the way down the ladder reached the rungs meant
 * to rescue them and saw nothing — the hint bug of 13 August again, at the point
 * where the student is most stuck. The revised handoff asks for them (frontend
 * §2) and for step-by-step presentation.
 *
 * These assert the pacing rules, because the pacing is the pedagogy: a
 * walkthrough shown whole is an answer to read, and tutor-solved is the only
 * answer-reveal rung in the spec.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { rescuePresentation, visibleSteps, fullyRevealed } from '@/lib/guidedRescue';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

const PARALLEL = {
  rescue_type: 'PARALLEL_EXAMPLE' as const,
  micro_skill_id: 'MS-T01-LINEAR',
  parallel_example: {
    parallel_example_id: 'PE-T01-001',
    problem: 'A plant is 3 cm tall and grows 2 cm each week.',
    worked_steps: ['Start at 3.', 'Add 2 for every week.', 'So the rule is 3 + 2w.'],
    final_answer: '3 + 2w',
  },
  tutor_solved: null,
};

const SOLVED = {
  rescue_type: 'TUTOR_SOLVED' as const,
  micro_skill_id: 'MS-T01-LINEAR',
  parallel_example: null,
  tutor_solved: {
    explanation: 'The score goes up by the same amount each turn.',
    answer_steps: ['Find what changes.', 'It goes up by 5.', 'So the rule is n + 5.'],
    final_answer: 'n + 5',
  },
};

describe('unpacking a rescue', () => {
  it('reads a parallel example', () => {
    expect(rescuePresentation(PARALLEL)).toEqual({
      kind: 'PARALLEL_EXAMPLE',
      problem: 'A plant is 3 cm tall and grows 2 cm each week.',
      steps: ['Start at 3.', 'Add 2 for every week.', 'So the rule is 3 + 2w.'],
      finalAnswer: '3 + 2w',
    });
  });

  it('puts the tutor-solved explanation where the problem goes', () => {
    // It frames the solution, so it belongs above the steps — appended after
    // the answer it would be explaining something already given away.
    const view = rescuePresentation(SOLVED)!;
    expect(view.problem).toBe('The score goes up by the same amount each turn.');
    expect(view.steps[0]).toBe('Find what changes.');
  });

  it('shows nothing rather than an empty card', () => {
    // A rung with no content renders as the tutor failing at the moment it
    // promised help. Better to leave the ladder where it was.
    expect(rescuePresentation(null)).toBeNull();
    expect(rescuePresentation({ ...PARALLEL, parallel_example: null })).toBeNull();
    expect(rescuePresentation({
      ...SOLVED,
      tutor_solved: { ...SOLVED.tutor_solved, answer_steps: ['  ', ''] },
    })).toBeNull();
  });
});

describe('pacing', () => {
  const steps = ['one', 'two', 'three'];

  it('opens on the first step alone', () => {
    expect(visibleSteps(steps, 1)).toEqual(['one']);
  });

  it('holds the answer back until every step has been seen', () => {
    expect(fullyRevealed(steps, 2)).toBe(false);
    expect(fullyRevealed(steps, 3)).toBe(true);
  });

  it('never reads past the end when a shorter rescue replaces a longer one', () => {
    expect(visibleSteps(['only one'], 3)).toEqual(['only one']);
    expect(visibleSteps(steps, -1)).toEqual([]);
  });

  it('is not "revealed" when there is nothing to reveal', () => {
    // Otherwise an empty rescue would count as complete and show its answer
    // with no reasoning above it at all.
    expect(fullyRevealed([], 0)).toBe(false);
  });
});

describe('through a real turn', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      guidedRescue: null,
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-T01-004',
    });
  });

  const turn = (over: Record<string, unknown> = {}) => ({
    message: 'Let us look at a similar one.',
    show_visual_cue: false,
    ...over,
  }) as Parameters<typeof applyInteractionSupport>[0];

  it('holds the rescue the backend served', () => {
    applyInteractionSupport(turn({ guided_rescue: PARALLEL }));
    expect(state().guidedRescue).toEqual(PARALLEL);
  });

  it('stays up through the ordinary turns taken while reading it', () => {
    // The student talks to the tutor mid-walkthrough and those replies carry no
    // guided_rescue. Clearing on them would close the card between one step and
    // the next — the scaffold panel's old bug, on the rung that matters most.
    applyInteractionSupport(turn({ guided_rescue: PARALLEL }));
    applyInteractionSupport(turn({ message: 'Good question.' }));
    expect(state().guidedRescue).toEqual(PARALLEL);
  });

  it('is replaced when the tutor escalates to solving it', () => {
    applyInteractionSupport(turn({ guided_rescue: PARALLEL }));
    applyInteractionSupport(turn({ guided_rescue: SOLVED }));
    expect(state().guidedRescue).toEqual(SOLVED);
  });

  it('comes down when the question changes', () => {
    applyInteractionSupport(turn({ guided_rescue: PARALLEL }));
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-005', questionText: 'Next one',
    });
    expect(state().guidedRescue).toBeNull();
  });
});

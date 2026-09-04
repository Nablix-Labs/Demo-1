/**
 * Opening a rescue takes the ladder above it down.
 *
 * A rescue is the BOTTOM rung: reaching it means the hint, the cue and the
 * scaffold have all already failed this student. Chirudeva, 4 Sep: "clear/hide
 * lower-rung scaffold and visual-cue cards for that active question."
 *
 * The clear happens once, when a rescue OPENS. That is the part worth a test —
 * clearing on every step would take away a rung the student picked up between
 * step 1 and step 2, and clearing on a step of a rescue already running is
 * indistinguishable from clearing on the first one until you look.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/lib/rescueEvents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/rescueEvents')>()),
  emitRenderAck: () => true,
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');
type Action = Parameters<ReturnType<typeof useNumeraStore.getState>['applyTutorCanvasActions']>[0][number];

const step = (i: number, rescueId = 'R1', over: Partial<Action> = {}): Action => ({
  action_id: `TURN-1:${i}:TUTOR_SOLVED_STEP:${rescueId}:${i}`,
  type: 'TUTOR_SOLVED_STEP',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: `TUTOR_ANCHOR:RESCUE:${rescueId}:STEP:${i}`,
  confirmed_component_id: null,
  text: `Step ${i}.`,
  source_id: 'TS-1',
  answer_reveal_allowed: false,
  rescue_id: rescueId,
  step_index: i,
  total_steps: 3,
  presentation_mode: 'TUTOR_SOLVED',
  return_target_object_id: null,
  ...over,
});

const apply = (...actions: Action[]) =>
  useNumeraStore.getState().applyTutorCanvasActions(actions);

/** Every rung above the rescue, up at once. */
const rungsUp = () => useNumeraStore.setState({
  visibleHint: 'Try grouping the like terms.',
  writeInstruction: 'Write the next line of working.',
  activeScaffold: {
    scaffoldId: 'SC-1', currentStepId: 'ST-1', stepNumber: 1,
    stepText: 'What is on the left?', stepVoice: null, totalSteps: 3,
  },
  visualCueVisible: true,
  visualCueId: 'CUE-1',
  visualCueType: 'BAR_MODEL',
  visualCueDescription: 'Look at the bar model.',
  visualCueAssetUrl: null,
  visualCueActions: null,
});

const rungs = () => {
  const s = useNumeraStore.getState();
  return {
    hint: s.visibleHint,
    write: s.writeInstruction,
    scaffold: s.activeScaffold,
    cueVisible: s.visualCueVisible,
    cueId: s.visualCueId,
    cueDescription: s.visualCueDescription,
  };
};

beforeEach(() => {
  useNumeraStore.getState().clearRescueSteps();
  useNumeraStore.getState().clearTutorMarks();
  useNumeraStore.setState({
    currentPhase: 'GUIDED_PRACTICE',
    activeQuestionId: 'Q-1',
    rescueSteps: [],
    rescueReturnTarget: null,
    pendingRescueActions: [],
    tutorElements: [],
    items: [],
    questionAnchors: [],
  });
});

describe('opening a rescue', () => {
  it('takes down every rung above it', () => {
    rungsUp();
    apply(step(1));
    expect(rungs()).toEqual({
      hint: null, write: null, scaffold: null,
      cueVisible: false, cueId: null, cueDescription: null,
    });
  });

  it('leaves the rungs alone on the second step of the same rescue', () => {
    // The student picked up a hint between step 1 and step 2 — from "Need
    // help?", or because the turn that carried step 2 also served one. Clearing
    // on every step would take it away again the moment they pressed Next.
    apply(step(1));
    rungsUp();
    apply(step(2));
    expect(rungs().hint).toBe('Try grouping the like terms.');
    expect(rungs().scaffold).not.toBeNull();
  });

  it('clears again when a DIFFERENT rescue supersedes the first', () => {
    apply(step(1));
    rungsUp();
    apply(step(1, 'R2'));
    expect(rungs().hint).toBeNull();
    expect(useNumeraStore.getState().rescueSteps.map((s) => s.rescueId)).toEqual(['R2']);
  });

  it('does not clear anything when the action was not a usable step', () => {
    // No rescue_id: nothing is recorded, no panel opens, so nothing on screen
    // has been superseded. Clearing here would strip the ladder on the strength
    // of an action that rendered nothing.
    rungsUp();
    apply(step(1, 'R1', { rescue_id: null }));
    expect(rungs().hint).toBe('Try grouping the like terms.');
  });

  it('does not clear anything in Phase 3, where no rescue is recorded at all', () => {
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    rungsUp();
    apply(step(1));
    expect(useNumeraStore.getState().rescueSteps).toEqual([]);
    expect(rungs().hint).toBe('Try grouping the like terms.');
  });
});

describe('completion and failure belong to one walkthrough', () => {
  it('clears a completion when the student returns to the question', () => {
    apply(step(1));
    useNumeraStore.getState().noteRescueCompleted();
    useNumeraStore.getState().clearRescueSteps();
    expect(useNumeraStore.getState().rescueCompleted).toBe(false);
  });

  it('does not carry a completion into the rescue that replaces it', () => {
    // A completion belongs to the walkthrough it ended. Carried over, the next
    // rescue would open with "Return to original" already showing in place of
    // "Next step" — one step in, and no way to reach the rest of it.
    apply(step(1));
    useNumeraStore.getState().noteRescueCompleted();
    apply(step(1, 'R2'));
    expect(useNumeraStore.getState().rescueCompleted).toBe(false);
  });

  it('does not carry a failed press into the rescue that replaces it', () => {
    apply(step(1));
    useNumeraStore.getState().noteRescueAdvanceFailed({ rescueId: 'R1', step: 1 });
    apply(step(1, 'R2'));
    expect(useNumeraStore.getState().rescueAdvanceFailure).toBeNull();
  });

  it('keeps a failed press while the SAME rescue is still on screen', () => {
    // The notice is about the step the student is looking at, and they are
    // still looking at it — a step that never arrived cannot have replaced it.
    apply(step(1));
    useNumeraStore.getState().noteRescueAdvanceFailed({ rescueId: 'R1', step: 1 });
    apply(step(2));
    expect(useNumeraStore.getState().rescueAdvanceFailure).toEqual({ rescueId: 'R1', step: 1 });
  });
});

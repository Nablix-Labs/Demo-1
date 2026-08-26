/**
 * The rescue presentation through the store — the wiring, not the parsing.
 *
 * Four things are worth a test here because each of them, when it broke, would
 * look like something else entirely:
 *
 *   - the flag being off must leave the rungs to `guided_rescue`, or enabling
 *     the backend half alone shows a walkthrough nothing can advance;
 *   - an unresolvable rescue action must WAIT, not drop, or the student at the
 *     bottom of the ladder gets nothing and the log says "not on screen";
 *   - the acknowledgement must fire only for a step that actually rendered, or
 *     the backend believes the student saw a step they did not;
 *   - rescue marks must not consume confirmation rows, or the next "m → changes"
 *     lands three rows further down for no reason a reader could see.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('@/lib/runtimeConfig', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/runtimeConfig')>()),
  canvasRescuePresentationEnabled: true,
}));

const sent: unknown[] = [];
vi.mock('@/lib/rescueEvents', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/rescueEvents')>()),
  emitRenderAck: (ack: unknown) => { sent.push(ack); return true; },
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');
const { occupiedSlots } = await import('@/lib/tutorCanvasActions');
type Action = Parameters<ReturnType<typeof useNumeraStore.getState>['applyTutorCanvasActions']>[0][number];

const step = (i: number, over: Partial<Action> = {}): Action => ({
  action_id: `TURN-1:${i}:TUTOR_SOLVED_STEP:R1:${i}`,
  type: 'TUTOR_SOLVED_STEP',
  target_kind: 'TUTOR_ANCHOR',
  target_object_id: `TUTOR_ANCHOR:RESCUE:R1:STEP:${i}`,
  confirmed_component_id: null,
  text: `Step ${i}.`,
  source_id: 'TS-1',
  answer_reveal_allowed: false,
  rescue_id: 'R1',
  step_index: i,
  total_steps: 3,
  presentation_mode: 'TUTOR_SOLVED',
  return_target_object_id: 'TUTOR_ANCHOR:WRITE_RULE:Q-1',
  ...over,
});

const apply = (...actions: Action[]) =>
  useNumeraStore.getState().applyTutorCanvasActions(actions);

beforeEach(() => {
  sent.length = 0;
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

describe('rendering a rescue', () => {
  it('records the step and its return target', () => {
    apply(step(1));
    const s = useNumeraStore.getState();
    expect(s.rescueSteps.map((x) => x.stepIndex)).toEqual([1]);
    expect(s.rescueReturnTarget).toBe('TUTOR_ANCHOR:WRITE_RULE:Q-1');
  });

  it('puts the step on the tutor layer', () => {
    apply(step(1));
    const marks = useNumeraStore.getState().tutorElements;
    expect(marks).toHaveLength(1);
    expect(marks[0].text).toBe('Step 1.');
  });

  it('appends steps in authored order, whatever order they arrive in', () => {
    apply(step(2));
    apply(step(1));
    expect(useNumeraStore.getState().rescueSteps.map((s) => s.stepIndex)).toEqual([1, 2]);
  });

  it('acknowledges the step it rendered, against its anchor', async () => {
    apply(step(1));
    await Promise.resolve();
    expect(sent).toEqual([{
      action_id: 'TURN-1:1:TUTOR_SOLVED_STEP:R1:1',
      status: 'RENDERED',
      target_object_id: 'TUTOR_ANCHOR:RESCUE:R1:STEP:1',
    }]);
  });

  it('does not acknowledge an action it could not use', async () => {
    apply(step(1, { rescue_id: null }));
    await Promise.resolve();
    expect(sent).toEqual([]);
  });

  it('keeps its rows off the confirmation ladder', () => {
    apply(step(1), step(2), step(3));
    // Three rescue rows on the board, and the next confirmation still lands on
    // the first row of its own ladder.
    expect(useNumeraStore.getState().tutorElements).toHaveLength(3);
    expect(occupiedSlots(useNumeraStore.getState().tutorElements)).toBe(0);
  });

  it('leaves student ink alone', () => {
    const ink = [{ id: 'ITEM-1', kind: 'stroke', points: [0.1, 0.1, 0.2, 0.2] }];
    useNumeraStore.setState({ items: ink as never });
    apply(step(1));
    expect(useNumeraStore.getState().items).toEqual(ink);
  });
});

describe('when the target is not there yet', () => {
  it('queues a rescue action rather than dropping it', () => {
    // A FOCUS onto a return target that is not on the board. The ordinary rule
    // drops this; a rescue must not lose it.
    apply({
      ...step(1),
      action_id: 'TURN-1:9:FOCUS',
      type: 'FOCUS',
      target_object_id: 'TUTOR_ANCHOR:ORIGINAL:Q-1',
      rescue_id: null,
      step_index: null,
    });
    expect(useNumeraStore.getState().pendingRescueActions).toHaveLength(1);
  });

  it('retries the queue on the next batch', () => {
    apply({
      ...step(1),
      action_id: 'TURN-1:9:FOCUS',
      type: 'FOCUS',
      target_object_id: 'TUTOR_ANCHOR:ORIGINAL:Q-1',
      rescue_id: null,
      step_index: null,
    });
    apply(step(1));
    const s = useNumeraStore.getState();
    // Still unresolvable, so still queued — and the step alongside it rendered
    // anyway rather than being held up behind it.
    expect(s.pendingRescueActions).toHaveLength(1);
    expect(s.rescueSteps).toHaveLength(1);
  });

  it('bounds the queue', () => {
    for (let i = 0; i < 30; i += 1) {
      apply({
        ...step(1),
        action_id: `TURN-1:${i}:FOCUS`,
        type: 'FOCUS',
        target_object_id: 'TUTOR_ANCHOR:ORIGINAL:Q-1',
        rescue_id: null,
        step_index: null,
      });
    }
    expect(useNumeraStore.getState().pendingRescueActions.length).toBeLessThanOrEqual(12);
  });
});

describe('returning', () => {
  it('takes the steps and their marks away, leaving student ink', () => {
    const ink = [{ id: 'ITEM-1', kind: 'stroke', points: [0.1, 0.1] }];
    useNumeraStore.setState({ items: ink as never });
    apply(step(1), step(2));
    useNumeraStore.getState().clearRescueSteps();
    const s = useNumeraStore.getState();
    expect(s.rescueSteps).toEqual([]);
    expect(s.rescueReturnTarget).toBeNull();
    expect(s.tutorElements).toEqual([]);
    expect(s.items).toEqual(ink);
  });

  it('lets the same rescue be served again afterwards', () => {
    apply(step(1));
    useNumeraStore.getState().clearRescueSteps();
    apply(step(1));
    expect(useNumeraStore.getState().rescueSteps).toHaveLength(1);
  });
});

describe('Phase 3', () => {
  it('shows no rescue during an independent attempt', () => {
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    apply(step(1));
    expect(useNumeraStore.getState().rescueSteps).toEqual([]);
  });
});

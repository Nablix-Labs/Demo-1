/**
 * Every canvas action reaches ordered memory (§8, §9 of the V1-Hybrid spec).
 *
 * The pure log rules are covered in lib/__tests__/canvasMemory.test.ts. What is
 * pinned HERE is the wiring, because a missed emitter is the failure nobody
 * would notice: the board still looks right, the student sees nothing wrong,
 * and only the tutor is quietly reasoning from an incomplete history. So there
 * is a test per mutation path rather than one happy-path walkthrough.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore, type DrawnItem } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();
const events = () => state().canvasEvents;

const stroke = (id: string): DrawnItem => ({
  id, kind: 'stroke', tool: 'pen', points: [80, 40, 240, 120], color: '#000', size: 3,
});

beforeEach(() => {
  useNumeraStore.setState({
    canvasEvents: [],
    items: [],
    undone: [],
    tutorElements: [],
    canvasSize: { width: 800, height: 400 },
    currentTurnId: 'TURN-1',
    activeQuestionId: 'Q-T01-004',
    currentPhase: 'GUIDED_PRACTICE',
  });
  // The applied-actionId set is module-level, so it outlives setState and one
  // test's ACT-1 would silently dedupe the next test's. clearTutorMarks is what
  // resets it.
  useNumeraStore.getState().clearTutorMarks();
});

describe('student actions', () => {
  it('logs a WRITE with the object and its normalised position', () => {
    state().addItem(stroke('S1'));
    expect(events()).toHaveLength(1);
    expect(events()[0]).toMatchObject({
      actor: 'STUDENT',
      action_type: 'WRITE',
      target_object_id: 'S1',
      bbox: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
      active_state: 'ACTIVE',
    });
  });

  it('logs an ERASE and supersedes the write it removed', () => {
    state().addItem(stroke('S1'));
    state().removeItem('S1');
    expect(events().map((e) => [e.action_type, e.active_state])).toEqual([
      ['WRITE', 'SUPERSEDED'],
      ['ERASE', 'ACTIVE'],
    ]);
  });

  it('logs undo as an erase rather than rewinding the log', () => {
    // The student DID write it and then take it back. That sequence is the
    // evidence — a log that rewound would say they never tried it.
    state().addItem(stroke('S1'));
    state().undo();
    expect(state().items).toHaveLength(0);
    expect(events()).toHaveLength(2);
    expect(events()[1].action_type).toBe('ERASE');
  });

  it('logs redo as a fresh write', () => {
    state().addItem(stroke('S1'));
    state().undo();
    state().redo();
    expect(state().items).toHaveLength(1);
    expect(events().map((e) => e.action_type)).toEqual(['WRITE', 'ERASE', 'WRITE']);
  });

  it('keeps the whole trail when the board is cleared', () => {
    // §11: transient marks "may fade/clear visually but remain in ordered
    // memory". An empty canvas is not an empty history.
    state().addItem(stroke('S1'));
    state().addItem(stroke('S2'));
    state().clearCanvas();
    expect(state().items).toHaveLength(0);
    expect(events()).toHaveLength(3);
    expect(events().slice(0, 2).every((e) => e.active_state === 'CLEARED')).toBe(true);
    expect(events()[2].action_type).toBe('CLEAR');
  });

  it('ignores an erase of an object that was never there', () => {
    state().removeItem('GHOST');
    expect(events()).toHaveLength(0);
  });

  it('keeps order_index a true position after supersede rewrites', () => {
    // supersede maps over the array; if it ever produced a different length,
    // the next order_index would collide and the tutor's "first unresolved
    // step" would resolve to the wrong one.
    state().addItem(stroke('S1'));
    state().removeItem('S1');
    state().addItem(stroke('S2'));
    state().clearCanvas();
    expect(events().map((e) => e.order_index)).toEqual([0, 1, 2, 3]);
  });
});

describe('tutor actions', () => {
  it('logs one event per drawn element with the §8 verb', () => {
    state().applyCanvasDraw({
      actionId: 'ACT-1',
      elements: [
        { id: 'T1', kind: 'highlight', x: 0.1, y: 0.2, w: 0.3, h: 0.1 },
        { id: 'T2', kind: 'math', x: 0.4, y: 0.5, tex: 'n + 5' },
      ],
    });
    expect(events().map((e) => e.action_type)).toEqual(['HIGHLIGHT', 'INSERT_MATH']);
    expect(events().every((e) => e.actor === 'TUTOR')).toBe(true);
  });

  it('carries the maths the tutor wrote', () => {
    state().applyCanvasDraw({ elements: [{ id: 'T1', kind: 'math', x: 0.4, y: 0.5, tex: 'n + 5' }] });
    expect(events()[0].math_text).toBe('n + 5');
  });

  it('traces the mark back to the action that ordered it', () => {
    state().applyCanvasDraw({ actionId: 'ACT-1', elements: [{ id: 'T1', kind: 'arrow', from: [0, 0], to: [1, 1] }] });
    expect(events()[0].source_id).toBe('ACT-1');
  });

  it('does not log a re-delivered action twice', () => {
    // A WebSocket reconnect replays the command. Logged twice, it would read
    // as the tutor making the same teaching move again.
    const payload = { actionId: 'ACT-1', elements: [{ id: 'T1', kind: 'highlight' as const, x: 0.1, y: 0.1 }] };
    state().applyCanvasDraw(payload);
    state().applyCanvasDraw(payload);
    expect(events()).toHaveLength(1);
  });

  it('supersedes the marks a replace wipes, keeping them in the log', () => {
    state().applyCanvasDraw({ actionId: 'ACT-1', elements: [{ id: 'T1', kind: 'highlight', x: 0.1, y: 0.1 }] });
    state().applyCanvasDraw({ actionId: 'ACT-2', mode: 'replace', elements: [{ id: 'T2', kind: 'arrow', from: [0, 0], to: [1, 1] }] });
    expect(state().tutorElements.map((el) => el.id)).toEqual(['T2']);
    expect(events().map((e) => e.active_state)).toEqual(['SUPERSEDED', 'ACTIVE']);
  });

  it('logs nothing in Phase 3, where the tutor may not draw at all', () => {
    // applyCanvasDraw refuses the drawing itself (§3.2). The log must agree —
    // an event for a mark that never appeared would describe a lesson the
    // student did not have.
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    state().applyCanvasDraw({ elements: [{ id: 'T1', kind: 'highlight', x: 0.1, y: 0.1 }] });
    expect(events()).toHaveLength(0);
  });
});

describe('support actions', () => {
  it('logs SHOW_CUE against the cue id, which is also its provenance', () => {
    state().setVisualCue({ show: true, cueId: 'VC-T01-ADD-NOT-MULTIPLY', description: 'Look at the +5' });
    expect(events()[0]).toMatchObject({
      actor: 'SYSTEM_SUPPORT',
      action_type: 'SHOW_CUE',
      target_object_id: 'VC-T01-ADD-NOT-MULTIPLY',
      source_id: 'VC-T01-ADD-NOT-MULTIPLY',
      content: 'Look at the +5',
    });
  });

  it('logs HIDE_CUE when the cue is taken away', () => {
    state().setVisualCue({ show: false });
    expect(events()[0].action_type).toBe('HIDE_CUE');
  });

  it('logs a scaffold step with the step id it came from', () => {
    // §13: "Every support action is traceable to DB content."
    state().setActiveScaffold({
      scaffoldId: 'SC-T01-1', currentStepId: 'STEP-2', stepNumber: 2,
      stepText: 'What stays the same each time?', stepVoice: null, totalSteps: 4,
    });
    expect(events()[0]).toMatchObject({
      actor: 'SYSTEM_SUPPORT',
      action_type: 'SCAFFOLD_STEP',
      source_id: 'STEP-2',
      content: 'What stays the same each time?',
    });
  });

  it('logs nothing when the scaffold panel closes', () => {
    state().setActiveScaffold(null);
    expect(events()).toHaveLength(0);
  });
});

describe('question scope', () => {
  it('starts a new question with an empty log', () => {
    // §8's memory answers "where are we in THIS problem". Carrying a finished
    // question's reasoning forward would offer it as unfinished.
    state().addItem(stroke('S1'));
    state().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-005', questionText: 'Next one' });
    expect(events()).toHaveLength(0);
  });

  it('keeps the log while the student is still on the same question', () => {
    state().addItem(stroke('S1'));
    state().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-004', questionText: null });
    expect(events()).toHaveLength(1);
  });

  it('files each event against the turn and question it happened in', () => {
    state().addItem(stroke('S1'));
    useNumeraStore.setState({ currentTurnId: 'TURN-2' });
    state().addItem(stroke('S2'));
    expect(events().map((e) => e.turn_id)).toEqual(['TURN-1', 'TURN-2']);
    expect(events().every((e) => e.question_id === 'Q-T01-004')).toBe(true);
  });
});

describe('the interleaved trail the tutor actually reads', () => {
  it('records a wrong answer, its correction and the support between them, in order', () => {
    // §8's own worked example: the value of the log is that this sequence
    // survives, when the finished board shows only `n + 5`.
    state().addItem(stroke('WRONG'));           // student writes n x 5
    state().setVisualCue({ show: true, cueId: 'VC-T01-ADD-NOT-MULTIPLY' });
    state().applyCanvasDraw({ actionId: 'ACT-1', elements: [{ id: 'T1', kind: 'highlight', x: 0.1, y: 0.1 }] });
    state().undo();                             // student rubs the wrong one out
    state().addItem(stroke('RIGHT'));           // and writes n + 5

    expect(events().map((e) => `${e.actor}:${e.action_type}`)).toEqual([
      'STUDENT:WRITE',
      'SYSTEM_SUPPORT:SHOW_CUE',
      'TUTOR:HIGHLIGHT',
      'STUDENT:ERASE',
      'STUDENT:WRITE',
    ]);
    // The wrong attempt is still there, marked as no longer standing.
    const wrong = events().find((e) => e.target_object_id === 'WRONG')!;
    expect(wrong.active_state).toBe('SUPERSEDED');
  });
});

/**
 * A confirmed component is written on the canvas once.
 *
 * Sanya, 21 Sep 2026: "Start: n / Gain: +5" appeared twice, the second copy
 * written across the first. `seenTutorCanvasActionIds` only stops the SAME
 * action being replayed; it cannot stop the backend confirming the same
 * component again on a later turn under a fresh action id, and when that
 * happens the label ladder allocates a new slot and writes it again.
 *
 * A confirmed component is a fact about the student's work, not a per-turn
 * remark — once it is on the page it stays, so a second copy is always wrong.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore, type DrawnItem } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

const item: DrawnItem = {
  id: 'S1', kind: 'stroke', tool: 'pen', points: [80, 40, 240, 120], color: '#000', size: 3,
};

const confirm = (actionId: string, component: string, text: string) => ({
  action_id: actionId,
  type: 'INSERT_LABEL' as const,
  target_kind: 'CANVAS_OBJECT' as const,
  target_object_id: 'S1',
  confirmed_component_id: component,
  text,
  source_id: null,
  answer_reveal_allowed: false,
});

beforeEach(() => {
  useNumeraStore.setState({
    canvasEvents: [], items: [item], tutorElements: [],
    canvasSize: { width: 800, height: 400 },
    currentTurnId: 'TURN-1', activeQuestionId: 'Q-T01-001',
    currentPhase: 'GUIDED_PRACTICE',
  });
  state().clearTutorMarks();
  useNumeraStore.setState({ items: [item] });
});

const marks = () => state().tutorElements.filter((el) => el.kind === 'text');

describe('the same component confirmed twice', () => {
  it('is written once, not stacked on itself', () => {
    state().applyTutorCanvasActions([confirm('TURN-1:1', 'START_VALUE', 'Start: n')]);
    const afterFirst = marks().length;
    state().applyTutorCanvasActions([confirm('TURN-2:1', 'START_VALUE', 'Start: n')]);
    expect(marks().length).toBe(afterFirst);
  });

  it('still writes a different component', () => {
    state().applyTutorCanvasActions([confirm('TURN-1:1', 'START_VALUE', 'Start: n')]);
    const afterFirst = marks().length;
    state().applyTutorCanvasActions([confirm('TURN-2:1', 'GAIN', 'Gain: +5')]);
    expect(marks().length).toBeGreaterThan(afterFirst);
  });

  it('writes it again on the next question — there it is a new fact', () => {
    state().applyTutorCanvasActions([confirm('TURN-1:1', 'START_VALUE', 'Start: n')]);
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE',
      questionId: 'Q-T01-002',
      questionText: 'Next one.',
      questionType: null,
    });
    useNumeraStore.setState({ items: [item] });
    state().applyTutorCanvasActions([confirm('TURN-9:1', 'START_VALUE', 'Start: n')]);
    expect(marks().length).toBeGreaterThan(0);
  });

  it('leaves actions without a component id alone', () => {
    // An ordinary remark is not a confirmed fact and may legitimately repeat.
    const plain = { ...confirm('TURN-1:1', 'X', 'Look here'), confirmed_component_id: null };
    state().applyTutorCanvasActions([plain]);
    const afterFirst = marks().length;
    state().applyTutorCanvasActions([{ ...plain, action_id: 'TURN-2:1' }]);
    expect(marks().length).toBeGreaterThan(afterFirst);
  });
});

describe('one confirmation in several parts (live, 28 Sep 2026)', () => {
  // `4y` for y + y + y + y: a highlight and a label on each of the four `y`s,
  // all under one component id. Only the first highlight used to survive.
  const Q = 'Write y + y + y + y in compact algebraic notation.';
  const yAt = [6, 10, 14, 18];
  const anchors = yAt.map((at, i) => ({
    token_id: `Q-T02-001:QTOKEN:${2 * i + 2}`, text: 'y', char_start: at, char_end: at + 1,
  }));
  const part = (n: number, type: 'HIGHLIGHT' | 'INSERT_LABEL', token: string) => ({
    action_id: `TURN-d24:${n}:${type}:${token}`,
    type,
    target_kind: 'QUESTION_ANCHOR' as const,
    target_object_id: token,
    confirmed_component_id: 'REPEATED_ADDITION_TO_COEFFICIENT_NOTATION',
    text: type === 'INSERT_LABEL' ? 'y → changes' : null,
    source_id: null,
    answer_reveal_allowed: false,
  });

  beforeEach(() => {
    state().applyBackendPhase({ phase: 'GUIDED_PRACTICE', questionId: 'Q-T02-001', questionText: Q, questionType: null });
    state().setQuestionAnchors(anchors);
  });

  it('applies every part that arrives together', () => {
    const batch = anchors.flatMap((a, i) => [part(2 * i + 1, 'HIGHLIGHT', a.token_id), part(2 * i + 2, 'INSERT_LABEL', a.token_id)]);
    state().applyTutorCanvasActions(batch);
    const marked = state().questionAnchors.filter((a) => a.highlighted && a.label === 'y → changes');
    expect(marked.map((a) => a.token_id)).toEqual(anchors.map((a) => a.token_id));
  });

  it('still skips the same component on a later turn', () => {
    state().applyTutorCanvasActions([part(1, 'HIGHLIGHT', anchors[0].token_id)]);
    state().applyTutorCanvasActions([{ ...part(2, 'INSERT_LABEL', anchors[1].token_id), action_id: 'TURN-next:1' }]);
    expect(state().questionAnchors.find((a) => a.token_id === anchors[1].token_id)?.label ?? null).toBeNull();
  });
});

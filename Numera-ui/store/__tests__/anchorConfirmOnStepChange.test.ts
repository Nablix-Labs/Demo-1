/**
 * #321, reopened by Sanya on 18 Sep: "when I move forward from m changes and
 * say it's an addition, the highlight on m goes away".
 *
 * The reply that confirms `m` also moves the active step on, so its base
 * anchors point at `+` and no longer contain `m`. They are applied before the
 * tutor's actions, so the HIGHLIGHT confirming `m` found no anchor and was
 * dropped — `m` was never confirmed, and its pointing highlight cleared.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore, type TutorCanvasAction } from '@/store/useNumeraStore';

const m = { token_id: 'Q1:QTOKEN:2', text: 'm', char_start: 3, char_end: 4, highlighted: true };
const plus = { token_id: 'Q1:QTOKEN:3', text: '+', char_start: 5, char_end: 6, highlighted: true };
const highlight = (id: string, token: string): TutorCanvasAction => ({
  action_id: id, type: 'HIGHLIGHT', target_kind: 'QUESTION_ANCHOR', target_object_id: token,
  confirmed_component_id: 'C', text: null, source_id: null, answer_reveal_allowed: false,
});
const state = () => useNumeraStore.getState();
const anchor = (id: string) => state().questionAnchors.find((a) => a.token_id === id);

beforeEach(() => {
  useNumeraStore.setState({
    questionAnchors: [], tutorElements: [], canvasEvents: [],
    activeQuestionId: 'Q1', currentPhase: 'GUIDED_PRACTICE',
    canvasSize: { width: 800, height: 600 },
  });
  state().clearTutorMarks();
});

describe('confirming a token the step has already moved past', () => {
  it('keeps the confirmed highlight on m', () => {
    state().setQuestionAnchors([m]);
    // The confirming reply: base anchors already on `+`, then the actions.
    state().setQuestionAnchors([plus]);
    state().applyTutorCanvasActions([highlight('T1:1', m.token_id)]);
    // And the turn after, which does not mention `m` at all.
    state().setQuestionAnchors([plus]);
    expect(anchor(m.token_id)).toMatchObject({ highlighted: true, confirmed: true });
  });

  it('still stops pointing at a token nobody confirmed', () => {
    state().setQuestionAnchors([m]);
    state().setQuestionAnchors([plus]);
    expect(anchor(m.token_id)?.highlighted).toBe(false);
  });
});

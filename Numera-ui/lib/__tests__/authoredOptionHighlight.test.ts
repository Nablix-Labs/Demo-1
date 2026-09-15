/**
 * The authored opening action for a choice question.
 *
 * Q-T01-004 on the VM: `authored_canvas_targets_not_in_question` on every turn.
 * The question is stored as "Which is the general rule: A) 12 + 4 or B) n + 4?"
 * and Student Model serves the stem apart from the options, so the backend's
 * grounding — which only looked at the stem — never found "n + 4" and dropped
 * the action. It now grounds against the options too and emits the
 * QUESTION_OPTION action this store already knows how to render.
 *
 * What is asserted here is the client half of that contract: given the action
 * the backend now sends, the option is highlighted, and an action naming an
 * option this question does not have is refused rather than rendered blind.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore, type TutorCanvasAction } from '@/store/useNumeraStore';

const OPTION_B_HIGHLIGHT: TutorCanvasAction = {
  action_id: 'AUTHORED:Q-T01-004:OPTION:B:HIGHLIGHT',
  type: 'HIGHLIGHT',
  target_kind: 'QUESTION_OPTION',
  target_object_id: 'Q-T01-004:OPTION:B',
  confirmed_component_id: null,
  text: null,
  source_id: 'question_guided_start_prompts',
} as TutorCanvasAction;

const store = () => useNumeraStore.getState();

beforeEach(() => {
  store().clearTutorMarks();
  useNumeraStore.setState({
    activeQuestionId: 'Q-T01-004',
    questionOptions: [
      { option_id: 'A', text: '12 + 4' },
      { option_id: 'B', text: 'n + 4' },
    ],
    tutorOptionActionIds: [],
  });
});

describe('an authored opening action that names an option', () => {
  it('highlights that option', () => {
    store().applyTutorCanvasActions([OPTION_B_HIGHLIGHT]);
    expect(store().tutorOptionActionIds).toEqual(['Q-T01-004:OPTION:B']);
  });

  it('is ignored when the option is not one this question serves', () => {
    // The guard that keeps a stale or mis-grounded action from pointing at
    // nothing. Refused, not rendered blind.
    store().applyTutorCanvasActions([{
      ...OPTION_B_HIGHLIGHT,
      action_id: 'AUTHORED:Q-T01-004:OPTION:Z:HIGHLIGHT',
      target_object_id: 'Q-T01-004:OPTION:Z',
    } as TutorCanvasAction]);
    expect(store().tutorOptionActionIds).toEqual([]);
  });

  it('is ignored when it belongs to a different question', () => {
    store().applyTutorCanvasActions([{
      ...OPTION_B_HIGHLIGHT,
      action_id: 'AUTHORED:Q-T01-009:OPTION:B:HIGHLIGHT',
      target_object_id: 'Q-T01-009:OPTION:B',
    } as TutorCanvasAction]);
    expect(store().tutorOptionActionIds).toEqual([]);
  });
});

/**
 * The tutor's voice and the tutor's text, on a scaffolded turn.
 *
 * Manjusha, row 54 / 26 Aug: "the tutor voice should perfectly match the tutor
 * text — currently it's not matching 100 percent."
 *
 * On a scaffolded turn applyInteractionSupport speaks the STEP, not the reply:
 * it returns `step_voice ?? step_text ?? message`. The chat bubble meanwhile
 * carried `message`, the tutor's conversational line, which on such a turn is
 * never spoken at all. So the student read one sentence and heard a different
 * one, every time a scaffold was open.
 *
 * The fix shows the step as well, ahead of the reply — the same place an
 * authorised hint already goes, and the same place support already goes so the
 * tutor's wording can refer to it (supportBeforeMessage.test.ts).
 *
 * What must NOT happen is the voice wording reaching the screen. The contract
 * has two authored renderings on purpose — `scaffold_step_text` is "the guiding
 * question to show", `scaffold_step_voice` is "what to speak for this step" —
 * and the spoken one is written to be heard. Printing it is how a clean
 * "13 + 5" turns into row 53's "slash 13+5" the other way round.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

const REPLY = 'Good — now look at the step on your screen.';

/** A turn with a scaffold the backend has persisted as active. */
const scaffoldTurn = (step: { step_text: string; step_voice?: string | null }) => ({
  message: REPLY,
  show_scaffold_panel: true,
  active_scaffold: {
    scaffold_id: 'SC-T01-01',
    current_step_id: 'SC-T01-01-S1',
    step_number: 1,
    total_steps: 3,
    ...step,
  },
}) as Parameters<typeof applyInteractionSupport>[0];

const said = () => useNumeraStore.getState().transcript.map((m) => m.text);

beforeEach(() => {
  useNumeraStore.setState({ transcript: [], activeScaffold: null, lastHintText: null });
});

describe('a scaffold step is spoken, so it is also shown', () => {
  it('puts the step in the chat, and speaks its voice wording', () => {
    const spoken = applyInteractionSupport(
      scaffoldTurn({ step_text: 'What is 13 + 5?', step_voice: 'What is thirteen plus five?' }),
    );
    expect(spoken).toBe('What is thirteen plus five?');
    expect(said()).toEqual(['What is 13 + 5?']);
  });

  it('never puts the voice wording on screen', () => {
    applyInteractionSupport(
      scaffoldTurn({ step_text: 'What is 13 + 5?', step_voice: 'What is thirteen plus five?' }),
    );
    expect(said()).not.toContain('What is thirteen plus five?');
  });

  it('speaks the shown wording when the backend authored no voice line', () => {
    const spoken = applyInteractionSupport(scaffoldTurn({ step_text: 'Which part changes?' }));
    expect(spoken).toBe('Which part changes?');
    expect(said()).toEqual(['Which part changes?']);
  });

  it('lands before the reply, which the caller appends next', () => {
    applyInteractionSupport(scaffoldTurn({ step_text: 'Which part changes?' }));
    useNumeraStore.getState().addTranscriptMessage({ role: 'ai', text: REPLY });
    expect(said()).toEqual(['Which part changes?', REPLY]);
  });

  it('says it once when the backend puts the same sentence in both', () => {
    applyInteractionSupport(scaffoldTurn({ step_text: REPLY }));
    expect(said()).toEqual([]);
  });

  it('leaves an ordinary turn alone', () => {
    const spoken = applyInteractionSupport({
      message: REPLY,
      show_scaffold_panel: false,
    } as Parameters<typeof applyInteractionSupport>[0]);
    expect(spoken).toBe(REPLY);
    expect(said()).toEqual([]);
  });
});

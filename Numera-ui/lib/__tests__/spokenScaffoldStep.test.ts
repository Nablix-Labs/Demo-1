/**
 * One tutor bubble on a scaffolded turn, and a voice line that matches it.
 *
 * Manjusha, row 54 / 26 Aug: "the tutor voice should perfectly match the tutor
 * text". The first attempt at that put the scaffold step into the transcript
 * from inside `applyInteractionSupport` — but every caller then appends
 * `response.message` as well, so a scaffolded turn produced TWO tutor bubbles on
 * every transport, and the two said different things.
 *
 * The composition is now the backend's (`interaction_service._scaffold_chat_line`):
 * `message` carries the tailored reply AND the current scaffold prompt, so there
 * is one sentence to show and one to speak. This module's only remaining job is
 * to choose the SPOKEN wording, and to add nothing to the transcript itself.
 *
 * What must still never happen is the voice wording reaching the screen. The
 * contract has two authored renderings on purpose — `step_text` is "the guiding
 * question to show", `step_voice` is "what to speak for this step" — and the
 * spoken one is written to be heard. Printing it is how a clean "13 + 5" turns
 * into row 53's "slash 13+5" the other way round.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

/** What the backend now sends: the reply and the step, composed into one line. */
const COMBINED = 'Good — now look at the step on your screen. What is 13 + 5?';

/** A turn with a scaffold the backend has persisted as active. */
const scaffoldTurn = (step: { step_text: string; step_voice?: string | null }) => ({
  message: COMBINED,
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

describe('a scaffolded turn is one bubble', () => {
  it('adds nothing to the transcript, so the caller appends exactly one line', () => {
    applyInteractionSupport(
      scaffoldTurn({ step_text: 'What is 13 + 5?', step_voice: 'What is thirteen plus five?' }),
    );
    expect(said()).toEqual([]);

    useNumeraStore.getState().addTranscriptMessage({ role: 'ai', text: COMBINED });
    expect(said()).toEqual([COMBINED]);
  });

  it('speaks the step’s voice wording', () => {
    const spoken = applyInteractionSupport(
      scaffoldTurn({ step_text: 'What is 13 + 5?', step_voice: 'What is thirteen plus five?' }),
    );
    expect(spoken).toBe('What is thirteen plus five?');
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
  });

  it('opens the panel on the step the backend authorised', () => {
    applyInteractionSupport(scaffoldTurn({ step_text: 'Which part changes?' }));
    expect(useNumeraStore.getState().activeScaffold?.currentStepId).toBe('SC-T01-01-S1');
  });

  it('leaves an ordinary turn alone', () => {
    const spoken = applyInteractionSupport({
      message: COMBINED,
      show_scaffold_panel: false,
    } as Parameters<typeof applyInteractionSupport>[0]);
    expect(spoken).toBe(COMBINED);
    expect(said()).toEqual([]);
  });
});

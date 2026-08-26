/**
 * The turn where the tutor could not read the student.
 *
 * Revised integration handoff, frontend §5: when `next_expected_input` is WRITE,
 * show a clear prompt, do not submit an answer automatically, and do not
 * increase attempts locally. The backend half is the reliability gate — a
 * low-confidence transcript or unreadable OCR must not increment attempts,
 * create an error event, advance progress, or escalate support.
 *
 * The failure this guards against is silence: a turn where the tutor learned
 * nothing, said nothing about it, and the student concludes they were ignored.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { requiresWriting, writePrompt, WRITE_FALLBACK_PROMPT } from '@/lib/writtenEvidence';
import { applyInteractionSupport } from '@/lib/interactionPresentation';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

describe('a turn that needs written evidence', () => {
  it('is recognised from next_expected_input', () => {
    expect(requiresWriting({ next_expected_input: 'WRITE' })).toBe(true);
  });

  it('is recognised from the reliability flag alone', () => {
    // The two fields travel together today but mean different things — one says
    // what to do next, the other says why. A turn carrying either still means
    // spoken maths cannot settle this step, and reading only one would drop the
    // instruction entirely.
    expect(requiresWriting({ requires_written_math_evidence: true })).toBe(true);
  });

  it('is not triggered by an ordinary turn', () => {
    expect(requiresWriting({})).toBe(false);
    expect(requiresWriting({ next_expected_input: 'VOICE_OR_WRITE' })).toBe(false);
    expect(requiresWriting({ requires_written_math_evidence: false })).toBe(false);
  });

  it('tolerates the backend\'s spacing and casing', () => {
    expect(requiresWriting({ next_expected_input: ' write ' })).toBe(true);
  });
});

describe('the instruction shown', () => {
  it('is the backend\'s own words when it sent some', () => {
    // It can say WHY: "I couldn't quite catch that" and "I couldn't read the
    // board" ask for the same action for different reasons, and the student can
    // only fix the one they are told about.
    expect(writePrompt({ next_expected_input: 'WRITE', write_instruction: "I couldn't read that — write it out?" }))
      .toBe("I couldn't read that — write it out?");
  });

  it('falls back to the handoff wording when it sent none', () => {
    expect(writePrompt({ next_expected_input: 'WRITE' })).toBe(WRITE_FALLBACK_PROMPT);
  });

  it('never echoes the tutor\'s own line', () => {
    // The message is already spoken and in the transcript. The prompt exists to
    // state the ACTION, which the message may not.
    const prompt = writePrompt({ next_expected_input: 'WRITE', message: 'Have another go.' });
    expect(prompt).toBe(WRITE_FALLBACK_PROMPT);
  });

  it('is null on a turn that does not ask for writing', () => {
    expect(writePrompt({ message: 'Nice work!' })).toBeNull();
  });
});

describe('through a real turn', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      writeInstruction: null,
      currentPhase: 'GUIDED_PRACTICE',
      activeQuestionId: 'Q-T01-004',
    });
  });

  const turn = (over: Record<string, unknown> = {}) => ({
    message: 'Let me see that written down.',
    show_visual_cue: false,
    ...over,
  }) as Parameters<typeof applyInteractionSupport>[0];

  it('puts the instruction on screen', () => {
    applyInteractionSupport(turn({ next_expected_input: 'WRITE' }));
    expect(state().writeInstruction).toBe(WRITE_FALLBACK_PROMPT);
  });

  it('takes it down as soon as the tutor can read them again', () => {
    // Not "leave it until the question changes", which is how the hint behaves.
    // The gate is per turn: once a turn is judged normally, an instruction to
    // rewrite refers to evidence the tutor has already accepted.
    applyInteractionSupport(turn({ next_expected_input: 'WRITE' }));
    applyInteractionSupport(turn({ message: 'That is right.' }));
    expect(state().writeInstruction).toBeNull();
  });

  it('comes down when the question changes', () => {
    applyInteractionSupport(turn({ next_expected_input: 'WRITE' }));
    state().applyBackendPhase({
      phase: 'GUIDED_PRACTICE', questionId: 'Q-T01-005', questionText: 'Next one',
    });
    expect(state().writeInstruction).toBeNull();
  });

  it('does not escalate support on the student\'s behalf', () => {
    // The gate exists because nothing was READ, so nothing may be concluded:
    // no attempt, no error event, no progression, no support escalation. A
    // WRITE turn that quietly moved the student up a rung would spend a hint on
    // a turn where they may well have been right.
    useNumeraStore.setState({ visibleHint: null, lastHintText: null, supportShown: null });
    applyInteractionSupport(turn({ next_expected_input: 'WRITE' }));
    expect(state().visibleHint).toBeNull();
    expect(state().lastHintText).toBeNull();
    expect(state().supportShown).toBeNull();
  });
});

/**
 * Every support field a voice turn can carry has to survive the mapping.
 *
 * The mapping is an allow-list, and the failure it produces is silent: a field
 * it forgets is indistinguishable from a field the backend never sent, so the
 * feature is simply absent on voice and works perfectly over REST. That is how
 * `next_expected_input: "WRITE"` was dropped on the one transport where the
 * student has written nothing (Sanya, 18 Aug 2026).
 */

import { describe, expect, it } from 'vitest';
import { voiceSupportFrame } from '@/lib/voiceSupportFrame';
import { requiresWriting, writePrompt } from '@/lib/writtenEvidence';

/** A frame with every field the backend can send, all distinguishable. */
const FULL = {
  text: 'So the rule is n plus four.',
  support_message: 'Think about what stays the same.',
  conversation_action: 'GIVE_HINT',
  next_expected_input: 'WRITE',
  requires_written_math_evidence: true,
  write_instruction: 'Write the rule on the canvas.',
  show_visual_cue: true,
  visual_cue: { show: true, cue_id: 'CUE-1' },
  show_scaffold_panel: true,
  scaffold_id: 'SC-1',
  current_scaffold_step_id: 'STEP-2',
  scaffold_step_number: 2,
  scaffold_step_text: 'Find what changes.',
  scaffold_step_voice: 'Now find what changes.',
  total_scaffold_steps: 4,
};

describe('a voice turn asking the student to write', () => {
  it('carries the WRITE instruction through to the prompt', () => {
    // The regression. Before this mapping existed the three reliability-gate
    // fields were not in the literal, so a voice-only algebra rule reached
    // writePrompt with nothing set and the student was never asked to write.
    const frame = voiceSupportFrame(FULL);
    expect(requiresWriting(frame)).toBe(true);
    expect(writePrompt(frame)).toBe('Write the rule on the canvas.');
  });

  it('still asks for writing when only next_expected_input is sent', () => {
    const frame = voiceSupportFrame({ text: 'x', next_expected_input: 'WRITE' });
    expect(requiresWriting(frame)).toBe(true);
    expect(writePrompt(frame)).toBeTruthy();
  });

  it('does not ask for writing on an ordinary voice turn', () => {
    expect(requiresWriting(voiceSupportFrame({ text: 'Well done.' }))).toBe(false);
  });
});

describe('the allow-list', () => {
  it('drops no field the backend sent', () => {
    // Compares against the frame itself rather than a hand-written list, so a
    // field added to VoiceTutorFrame and forgotten here fails rather than
    // quietly going missing.
    const frame = voiceSupportFrame(FULL) as Record<string, unknown>;
    const carried = Object.entries(FULL).filter(([k]) => k !== 'text');
    for (const [key, value] of carried) {
      expect(frame[key], `voice frame dropped "${key}"`).toEqual(value);
    }
    expect(frame.message).toBe(FULL.text);
  });

  it('leaves an absent field absent rather than inventing a default', () => {
    const frame = voiceSupportFrame({ text: 'x' }) as Record<string, unknown>;
    // A cue defaulted to `true` here would put a card on screen that the tutor
    // never authorised.
    expect(frame.show_visual_cue).toBeUndefined();
    expect(frame.next_expected_input).toBeUndefined();
  });
});

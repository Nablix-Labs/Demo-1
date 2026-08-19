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
import { scaffoldVisible } from '@/lib/responseGate';

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
  active_scaffold: {
    scaffold_id: 'SC-1',
    current_step_id: 'STEP-2',
    step_number: 2,
    step_text: 'Find what changes.',
    step_voice: 'Now find what changes.',
    total_steps: 4,
  },
  guided_rescue: {
    rescue_type: 'PARALLEL_EXAMPLE',
    parallel_example: {
      problem: 'Find a rule for 2 + 6, 5 + 6, 9 + 6.',
      worked_steps: ['The start changes.', 'The six stays.'],
      final_answer: 'n + 6',
    },
  },
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

describe('a rescue served on a voice turn', () => {
  it('reaches the presentation payload', () => {
    // The bottom two support rungs are what a stuck student gets. The streaming
    // server spreads the whole tutor_response onto the frame, so `guided_rescue`
    // was on the wire the entire time — the allow-list simply never read it, and
    // a voice-led student who got stuck was shown no rescue at all while the
    // same turn over REST showed one.
    const frame = voiceSupportFrame(FULL);
    expect(frame.guided_rescue).toEqual(FULL.guided_rescue);
  });

  it('is absent on a turn that serves none, so an open rescue is not disturbed', () => {
    // applyInteractionSupport only writes when a rescue is present: an ordinary
    // turn taken midway through reading one carries no `guided_rescue`, and
    // inventing an empty value here would close the walkthrough between steps.
    expect(voiceSupportFrame({ text: 'Keep going.' }).guided_rescue).toBeUndefined();
  });
});

describe('a scaffold left open across voice turns', () => {
  it('carries the persisted state, which outranks the per-turn booleans', () => {
    // Without this the voice path always fell through to the pre-contract
    // branch, where visibility is decided by `show_scaffold_panel` alone. A
    // reply that served no new support then closed a scaffold the student was
    // still working through — one step to the next, mid-walkthrough.
    expect(voiceSupportFrame(FULL).active_scaffold).toEqual(FULL.active_scaffold);
  });

  it('keeps the scaffold open when the turn serves no new support', () => {
    // The regression itself: persisted state present and non-null, per-turn
    // boolean false. Persisted must win.
    const frame = voiceSupportFrame({
      text: 'Keep going.',
      show_scaffold_panel: false,
      active_scaffold: FULL.active_scaffold,
    });
    expect(scaffoldVisible(frame)).toBe(true);
  });

  it('closes it when the backend explicitly says the scaffold is gone', () => {
    // Null is a statement, not an absence: the scaffold is closed.
    const frame = voiceSupportFrame({ text: 'Done.', active_scaffold: null });
    expect(scaffoldVisible(frame)).toBe(false);
  });
});

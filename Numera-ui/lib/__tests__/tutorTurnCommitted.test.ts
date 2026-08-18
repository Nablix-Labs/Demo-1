/**
 * The lineage of a turn the student walked away from.
 *
 * Reproduces the VM session of 15 Aug 2026, 11:08, which died on a barge-in and
 * failed every turn afterwards. Two separate faults, and fixing either one alone
 * still loses the session:
 *
 *   turn 17  reused turn 16's turn_id            → 409 duplicate
 *   turn 18  fresh id, stale previous_tutor_turn → 409 STALE_TURN
 *
 * The first is closed by opening a new turn on `tutor_audio_cancel`
 * (lib/tutorAudioCancel). The second is closed here: the backend committed the
 * barged-in turn and bumped state_version, and the client has to adopt that
 * tutor_turn_id even though it never heard the answer.
 *
 * The sequence test at the bottom is the one that matters — it asserts on the
 * frame the next turn actually puts on the wire, which is where both faults
 * showed up.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { committedLineage } from '@/lib/tutorTurnCommitted';
import { turnContextFrame } from '@/lib/voiceTurnContext';
import { shouldApply, noteApplied, EMPTY_APPLIED } from '@/lib/responseGate';
import { useNumeraStore } from '@/store/useNumeraStore';

const state = () => useNumeraStore.getState();

describe('the lineage on a committed frame', () => {
  it('is the tutor turn id the next turn must point at', () => {
    expect(committedLineage({ tutor_turn_id: 'TUTOR-abc123' })).toBe('TUTOR-abc123');
  });

  it('is null when the frame carries none', () => {
    // Not an empty string: `lastTutorTurnId` becomes the next
    // `previous_tutor_turn_id`, and the backend rejects a null one outright. A
    // frame with no id has to leave the existing pointer alone — out of date
    // still describes a real turn, erased fails every turn after it.
    expect(committedLineage({})).toBeNull();
    expect(committedLineage({ tutor_turn_id: null })).toBeNull();
    expect(committedLineage({ tutor_turn_id: '   ' })).toBeNull();
  });

  it('ignores a non-string id rather than coercing it', () => {
    expect(committedLineage({ tutor_turn_id: 42 as never })).toBeNull();
  });
});

describe('adopting that lineage', () => {
  beforeEach(() => {
    useNumeraStore.setState({
      currentTurnId: 'TURN-live',
      lastTutorTurnId: 'TUTOR-old',
      expectsStudentResponse: true,
      allowVoiceInput: true,
      tutorTurnFailed: false,
    });
  });

  it('moves the tutor pointer', () => {
    state().noteTutorLineage('TUTOR-abc123');
    expect(state().lastTutorTurnId).toBe('TUTOR-abc123');
  });

  it('leaves the turn the student is speaking into alone', () => {
    // The frame lands two to four seconds INTO the next turn. Touching
    // currentTurnId here would hand the live turn the abandoned turn's identity.
    state().noteTutorLineage('TUTOR-abc123');
    expect(state().currentTurnId).toBe('TURN-live');
  });

  it('does not carry the abandoned turn\'s gating onto the live one', () => {
    // Why this is not setTutorTurn: that also moves expectsStudentResponse and
    // allowVoiceInput. A late frame doing so could shut a mic the student is
    // mid-sentence into.
    useNumeraStore.setState({ expectsStudentResponse: false, allowVoiceInput: false });
    state().noteTutorLineage('TUTOR-abc123');
    expect(state().expectsStudentResponse).toBe(false);
    expect(state().allowVoiceInput).toBe(false);
  });

  it('does not clear a failure the live turn has already hit', () => {
    useNumeraStore.setState({ tutorTurnFailed: true });
    state().noteTutorLineage('TUTOR-abc123');
    expect(state().tutorTurnFailed).toBe(true);
  });
});

describe('the 11:08 session', () => {
  it('sends a fresh turn against the committed lineage', () => {
    // Turn 16: the student answers, the tutor replies, lineage is current.
    useNumeraStore.setState({ currentTurnId: 'TURN-16', lastTutorTurnId: 'TUTOR-15' });

    // The student barges in. tutor_audio_cancel opens turn 17 — this is the
    // half that stops the duplicate-id 409.
    state().beginListeningTurn();
    const turn17 = state().currentTurnId;
    expect(turn17).not.toBe('TURN-16');

    // Two seconds later the suppressed turn reports in.
    state().noteTutorLineage(committedLineage({ tutor_turn_id: 'TUTOR-16' })!);

    // What actually goes on the wire. Before these two fixes this frame carried
    // TURN-16 (duplicate) and then TUTOR-15 (STALE_TURN).
    const frame = turnContextFrame(state().currentTurnId, state().lastTutorTurnId);
    expect(frame).toEqual({
      type: 'turn_context',
      turn_id: turn17,
      previous_tutor_turn_id: 'TUTOR-16',
      transcript_final: true,
    });
  });

  it('refuses a committed frame that would drag the pointer backwards', () => {
    // The frame is already seconds old on arrival, so it is exactly the shape
    // that can land after a newer turn has resolved. Adopting it then would
    // point the next turn at an abandoned one — STALE_TURN on every turn after,
    // which is the failure this whole frame exists to fix.
    const applied = noteApplied(
      { interaction_state_version: 24, accepted_turn_id: 'TURN-18' },
      EMPTY_APPLIED,
    );
    const late = { interaction_state_version: 22, accepted_turn_id: 'TURN-16' };
    expect(shouldApply(late, applied)).toBe(false);
  });

  it('accepts one that is genuinely newer', () => {
    const applied = noteApplied(
      { interaction_state_version: 21, accepted_turn_id: 'TURN-15' },
      EMPTY_APPLIED,
    );
    expect(shouldApply({ interaction_state_version: 22, accepted_turn_id: 'TURN-16' }, applied))
      .toBe(true);
  });
});

/**
 * A canvas reply with no OCR and no tutor block is a SUCCESS, not a failure.
 *
 * Sanya's 12 Aug 2026 payload: an Independent Practice submission the backend
 * accepted (`status: processed`), graded (`evaluation: INCORRECT`) and locked
 * (`independent_attempt_terminal: true`) — carrying `ocr: null` and
 * `tutor: null`, because Phase 3 is silent and has no tutor message to send.
 *
 * The client read `res.ocr.raw_ocr_text` and `res.tutor.tutor_message`
 * straight through. The TypeError landed in the submit catch, so the student
 * was shown "The tutor couldn't take that submission. Your work is still here
 * — try once more" about work that had already been accepted and closed. The
 * worst part is the advice: submitting again is exactly what they must not do.
 */

import { describe, it, expect } from 'vitest';
import { canvasSubmissionView, canvasResponseIdentity } from '@/lib/canvasSubmission';
import { shouldApply, noteApplied, EMPTY_APPLIED } from '@/lib/responseGate';

/** Sanya's payload, reduced to the two fields that mattered. */
const PHASE_3_ACCEPTED = { ocr: null, tutor: null };

const FULL_REPLY = {
  ocr: {
    raw_ocr_text: 'n + 4',
    detected_equation: 'n+4',
    confidence: 0.95,
    needs_clarification: false,
  },
  tutor: { tutor_message: 'Nice work!', evaluation: 'CORRECT' },
};

describe('a Phase 3 reply with no OCR and no tutor', () => {
  it('does not throw — the bug that reported accepted work as failed', () => {
    expect(() => canvasSubmissionView(PHASE_3_ACCEPTED)).not.toThrow();
  });

  it('renders nothing rather than inventing a message', () => {
    const view = canvasSubmissionView(PHASE_3_ACCEPTED);
    expect(view.ocr).toBeNull();
    expect(view.tutorText).toBeNull();
    expect(view.tutorEvaluation).toBeUndefined();
  });

  it('survives the fields being absent entirely, not just null', () => {
    // Not every backend build sends the keys at all.
    for (const reply of [{}, null, undefined, { ocr: undefined, tutor: undefined }]) {
      expect(() => canvasSubmissionView(reply)).not.toThrow();
      expect(canvasSubmissionView(reply).tutorText).toBeNull();
    }
  });
});

describe('a normal reply still renders in full', () => {
  it('shows the OCR read-back with its confidence', () => {
    const view = canvasSubmissionView(FULL_REPLY);
    expect(view.ocr).toEqual({ text: 'n + 4', meta: 'OCR 95%' });
  });

  it('shows the tutor message and its verdict label', () => {
    const view = canvasSubmissionView(FULL_REPLY);
    expect(view.tutorText).toBe('Nice work!');
    expect(view.tutorEvaluation).toBe('CORRECT');
  });

  it('flags an unclear read so the trail says why a rewrite was asked for', () => {
    const view = canvasSubmissionView({
      ...FULL_REPLY,
      ocr: { ...FULL_REPLY.ocr, needs_clarification: true, confidence: 0.4 },
    });
    expect(view.ocr?.meta).toBe('OCR 40% · needs clarification');
  });
});

describe('the partial replies in between', () => {
  it('keeps a trail entry when OCR read nothing at all', () => {
    // An empty read is still a submission; no entry would look like lost work.
    const view = canvasSubmissionView({
      ocr: { raw_ocr_text: '', detected_equation: '', confidence: 0, needs_clarification: false },
      tutor: null,
    });
    expect(view.ocr?.text).toBe('Canvas submitted.');
    expect(view.ocr?.meta).toBe('OCR 0%');
  });

  it('treats a blank tutor message as no message', () => {
    // Phase 3 sends message_voice: "" — whitespace must not become a bubble.
    for (const tutor_message of ['', '   ', '\n']) {
      const view = canvasSubmissionView({ ocr: null, tutor: { tutor_message, evaluation: 'X' } });
      expect(view.tutorText).toBeNull();
      expect(view.tutorEvaluation).toBeUndefined();
    }
  });

  it('shows OCR even when the tutor stayed silent', () => {
    const view = canvasSubmissionView({ ocr: FULL_REPLY.ocr, tutor: null });
    expect(view.ocr?.text).toBe('n + 4');
    expect(view.tutorText).toBeNull();
  });

  it('shows the tutor even when OCR was omitted', () => {
    const view = canvasSubmissionView({ ocr: null, tutor: FULL_REPLY.tutor });
    expect(view.ocr).toBeNull();
    expect(view.tutorText).toBe('Nice work!');
  });
});

describe('who a canvas reply says it is', () => {
  /**
   * Measured against the live backend on 1 Sep 2026:
   *
   *   POST /interaction   (turn_id TURN-AAA) → version 1, accepted_turn_id TURN-AAA
   *   POST /canvas/submit (turn_id TURN-BBB) → version 1, accepted_turn_id TURN-AAA
   *
   * The canvas reply reports the PREVIOUS turn's id and the unchanged version,
   * because nothing on that path advances either (`record_canvas_submission`
   * and `_apply_schema_event` both leave them alone). The response gate then
   * sees a turn it has already applied and drops the whole reply — so the
   * backend advanced the question, said "Nice work. Here is the next question."
   * and the student's screen did not move. Manjusha, 1 Sep.
   */
  const interaction = { interaction_state_version: 1, accepted_turn_id: 'TURN-AAA' };
  const canvas = {
    interaction_state_version: 1,
    accepted_turn_id: 'TURN-AAA',
    submission_id: 'SUB-001',
  };

  const applyRun = (replies: { interaction_state_version?: number; accepted_turn_id?: string | null }[]) => {
    let applied = EMPTY_APPLIED;
    return replies.map((r) => {
      const ok = shouldApply(r, applied);
      if (ok) applied = noteApplied(r, applied);
      return ok;
    });
  };

  it('applies a canvas reply that follows an interaction turn', () => {
    expect(applyRun([interaction, canvasResponseIdentity(canvas)])).toEqual([true, true]);
  });

  it('still drops a genuine replay of the same submission', () => {
    const id = canvasResponseIdentity(canvas);
    expect(applyRun([interaction, id, id])).toEqual([true, true, false]);
  });

  it('still refuses a canvas reply that is genuinely out of date', () => {
    const newer = { interaction_state_version: 2, accepted_turn_id: 'TURN-CCC' };
    const stale = canvasResponseIdentity(canvas); // version 1, older
    expect(applyRun([interaction, newer, stale])).toEqual([true, true, false]);
  });

  it('leaves the reply alone when there is no submission id to use', () => {
    const noId = { interaction_state_version: 1, accepted_turn_id: 'TURN-AAA' };
    expect(canvasResponseIdentity(noId).accepted_turn_id).toBe('TURN-AAA');
  });
});

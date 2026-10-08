/**
 * Teach-Back against the live backend: the request, the restored conversation,
 * and what to do when a turn fails.
 *
 * Kept free of React so the rules are tested on their own
 * (lib/__tests__/teachBackConnected.test.ts). Contract: nablix-backend
 * models/interaction.py (InteractionRequest validators) and
 * services/interaction_service.py (_process_teach_back), plus the handoffs from
 * Chiru and Sanya (8–9 Oct):
 *  - TEACH_BACK_SUBMISSION, current_phase TEACH_BACK, question_id null;
 *  - text, or a FINAL voice transcript (`transcript_final: true`);
 *  - never canvas, never a score or attempt counter;
 *  - a stable turn_id and previous_tutor_turn_id; concept_id and hint_count
 *    from the session record;
 *  - after a failed mutation, GET the session (it runs the backend's pending
 *    recovery) before the next learning turn.
 */
import axios from 'axios';
import type { InteractionPayload, SessionRecord } from '@/lib/api';

export type TeachBackSource = 'TEXT' | 'VOICE';

export interface TeachBackTurnInput {
  text: string;
  source: TeachBackSource;
  /** 0–1 from the speech recogniser, when it reports one. */
  confidence?: number | null;
}

export interface TeachBackSessionFields {
  sessionId: string;
  studentId: string;
  conceptId: string;
  hintCount: number;
  turnId: string;
  previousTutorTurnId: string | null;
}

export function teachBackPayload(input: TeachBackTurnInput, s: TeachBackSessionFields): InteractionPayload {
  const text = input.text.trim();
  const confidence = typeof input.confidence === 'number' && input.confidence >= 0 && input.confidence <= 1
    ? { transcript_confidence: input.confidence }
    : {};
  return {
    session_id: s.sessionId,
    student_id: s.studentId,
    interaction_type: 'TEACH_BACK_SUBMISSION',
    input_source: input.source,
    ...(input.source === 'TEXT'
      ? { text_input: text }
      : { voice_transcript: text, transcript_final: true, ...confidence }),
    current_phase: 'TEACH_BACK',
    concept_id: s.conceptId,
    // Teach-Back has no question; the backend accepts null only in this phase.
    question_id: null,
    hint_count: s.hintCount,
    turn_id: s.turnId,
    previous_tutor_turn_id: s.previousTutorTurnId,
  };
}

export interface TeachBackLine {
  role: 'student' | 'tutor';
  text: string;
}

/**
 * The conversation so far, from the session record. The backend resets or
 * restores conversation_history when Teach-Back opens, so after a reload this
 * is the Teach-Back exchange; with no history the opening line stands alone.
 */
export function restoredLines(rec: Pick<SessionRecord, 'conversation_history' | 'message'>): TeachBackLine[] {
  const lines = (rec.conversation_history ?? [])
    .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content?.trim())
    .map((m) => ({ role: m.role === 'user' ? 'student' as const : 'tutor' as const, text: m.content.trim() }));
  if (lines.length) return lines;
  return rec.message?.trim() ? [{ role: 'tutor', text: rec.message.trim() }] : [];
}

/**
 * What a failed turn means for the next step.
 *
 *  - `retry`: the turn may not have been saved. Refresh the session, then send
 *    the SAME payload again (the backend dedupes on turn_id + content).
 *  - `discard`: the backend refused this answer for good. Refresh, drop the
 *    student's bubble and let them answer again.
 *  - `paused`: a teacher intervention holds the lesson.
 */
export type FailureAction = 'retry' | 'discard' | 'paused';

export function teachBackFailure(err: unknown): FailureAction {
  if (!axios.isAxiosError(err)) return 'retry';
  const status = err.response?.status;
  if (status === undefined) return 'retry'; // network or timeout
  const data = err.response?.data as { error_code?: string; detail?: unknown } | undefined;
  if (status === 409 && data?.error_code === 'INTERVENTION_REQUIRED') return 'paused';
  if (status === 422) return 'discard';
  if (status === 409) {
    const detail = typeof data?.detail === 'string' ? data.detail : '';
    // Same turn_id, different words: the earlier version was kept.
    if (/different Teach-Back evidence/i.test(detail)) return 'discard';
    // The session has moved on (orientation or guided); routing takes over.
    if (/outside Teach-Back|inactive Teach-Back target/i.test(detail)) return 'discard';
    return 'retry'; // recovery pending, version conflict
  }
  return status >= 500 ? 'retry' : 'discard';
}

/** The words a student sees for a failed turn. Never raw server text. */
export function teachBackFailureMessage(action: FailureAction): string {
  switch (action) {
    case 'paused':
      return 'Your teacher is taking a look at this topic for you. You can’t carry on with it just yet.';
    case 'discard':
      return 'That one didn’t go through. Have another go at explaining it.';
    default:
      return 'Your tutor didn’t get that. Your explanation is saved here, so try sending it again.';
  }
}

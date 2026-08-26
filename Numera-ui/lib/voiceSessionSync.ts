/**
 * The voice transport's half of the session sync.
 *
 * The REST path funnels every reply through `syncBackendSession`. The voice path
 * re-implemented the same work inline, and so quietly missed whatever REST
 * gained afterwards. Seven things have been lost that way so far —
 * `next_expected_input`, `guided_rescue`, `active_scaffold`,
 * `tutor_canvas_actions`, the cached-record refresh, `question_number`, and the
 * reveal hold — each invisible because REST forwards the whole response object
 * and so kept working perfectly.
 *
 * It stayed invisible for a second reason: `hooks/useWebSocket.ts` has no test
 * harness, so the wiring could be deleted without a single test failing. The
 * helpers were covered; the code that CALLS them was not.
 *
 * So this is not a tidy-up. Moving the block here is what makes it testable
 * against the real store, which is the only thing that would have caught any of
 * the seven.
 */

import { refreshedRecord } from '@/lib/sessionRecordRefresh';
import { revealDecision } from '@/lib/revealBeforeClear';
import { useNumeraStore } from '@/store/useNumeraStore';
import type { QuestionType } from '@/lib/api';

/** The raw WS frame. Values are unknown because the socket is untyped. */
export type VoiceSessionFrame = Record<string, unknown>;

/**
 * Apply a voice `tutor_response` frame's session state to the store.
 *
 * Returns the milliseconds the phase change was held for, so a caller (and a
 * test) can tell a held transition from an immediate one.
 *
 * `schedule` is injected so tests do not have to wait out a real timer.
 */
export function applyVoiceSessionFrame(
  msg: VoiceSessionFrame,
  schedule: (fn: () => void, ms: number) => void = (fn, ms) => { window.setTimeout(fn, ms); },
): number {
  const store = useNumeraStore.getState();

  // Options do not travel on a reply — they are looked up out of the cached
  // record by question id — so a phase change that issues a new question set
  // must refresh the record first, or the lookup searches the PREVIOUS phase's
  // questions and the student gets a choice question with no choices under it.
  const refreshed = refreshedRecord(store.backendSession, msg as never);
  if (refreshed) store.setBackendSession(refreshed);

  if (typeof msg.question_number === 'number') {
    useNumeraStore.getState().setQuestionNumber(msg.question_number);
  }

  // A reply that both annotates the finished work and moves the student on
  // holds the board briefly, so the annotation is seen rather than added and
  // cleared in the same tick. The marks themselves are applied by
  // applyInteractionSupport, before this runs.
  const { reveal, holdMs } = revealDecision(
    Array.isArray(msg.tutor_canvas_actions) ? msg.tutor_canvas_actions.length : 0,
    useNumeraStore.getState().activeQuestionId,
    (msg.question_id as string | null) ?? null,
  );

  if (typeof msg.current_phase !== 'string') return 0;

  const applyPhase = () => useNumeraStore.getState().applyBackendPhase({
    phase: msg.current_phase as string,
    questionId: (msg.question_id as string | null) ?? null,
    questionText: typeof msg.current_question === 'string' ? msg.current_question : null,
    // The voice server does not always forward this. Passing undefined rather
    // than null lets applyBackendPhase keep the type it already has instead of
    // blanking a choice question into a free-response one mid-lesson.
    questionType:
      typeof msg.question_type === 'string' ? (msg.question_type as QuestionType) : undefined,
  });

  if (reveal) schedule(applyPhase, holdMs);
  else applyPhase();
  return reveal ? holdMs : 0;
}

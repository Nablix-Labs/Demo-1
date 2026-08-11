/**
 * Handing the student from one phase's screen to the next.
 *
 * Both handoffs — /diagnostic/complete and /orientation/complete — return a
 * session record describing the phase being entered, and both screens used to
 * unpack it by hand. They drifted, and each drift was a bug a tester found:
 *
 *   - Writing `questionText` alone left the OPTIONS of the phase being left
 *     sitting under the new phase's question: the canvas asked "3 + 5, 9 + 5,
 *     14 + 5" while the choices below read "2 + 4, 7 + 4, 12 + 4"
 *     (Manjusha, 8 Aug).
 *   - Dropping the record's `message` meant nothing introduced the new phase.
 *     The lesson page speaks an opening line only when IT starts the session,
 *     and by this point one is already open, so the student simply arrived at
 *     a question with no word from the tutor (Manjusha, 8 Aug).
 *
 * One function so there is one place to get it right, and one place to test.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import type { SessionRecord } from '@/lib/api';

export function applyPhaseHandoff(rec: SessionRecord): void {
  const store = useNumeraStore.getState();

  // Options and question type live on the record and must be swapped WITH the
  // question, never after it — that gap is the bug above.
  store.applyBackendPhase({
    phase: rec.current_phase,
    questionId: rec.question_id,
    questionText: rec.current_question ?? null,
  });

  // Shown here, spoken by the screen being entered.
  //
  // Not spoken from this screen because it is unmounting — starting speech on a
  // route that is going away is how this codebase previously ended up with two
  // tutor voices at once. But showing it and never voicing it left the student
  // reading a line the tutor never said, on a voice-first product (row 4,
  // "displayed but not spoken", Sanya 11 Aug). So it is queued, and the
  // arriving screen claims it.
  const message = rec.message?.trim();
  if (message) {
    const store = useNumeraStore.getState();
    store.addTranscriptMessage({ role: 'ai', text: message });
    store.setPendingTutorSpeech(message);
  }
}

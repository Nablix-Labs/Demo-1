/**
 * Who has the floor.
 *
 * Two rules from §1 of the Phase 2 Guided Learning spec, kept here rather than
 * scattered across call sites so there is exactly one place that decides whether
 * the tutor is allowed to talk right now:
 *
 *   "Remain silent while the student writes."
 *   "Highlight first, pause briefly, then speak."
 *
 * The first rule is a *drop*, not a queue. The spec is explicit — once the
 * student starts writing the tutor stops speaking, does not repeat instructions
 * and does not surface hints; it waits for them to submit or ask. A queued
 * utterance that fires the moment they lift the pen would break exactly the
 * concentration the rule exists to protect.
 *
 * The second rule matters because a mark and its narration arriving together
 * gives the student nothing to look at while the words play. Drawing lands
 * first, settles, and only then is it described.
 *
 * Module-level state rather than store state on purpose: this is a property of
 * the audio channel, not of the lesson, and it must be readable synchronously
 * from inside a Konva pointer handler without a subscription.
 */

import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import { useNumeraStore } from '@/store/useNumeraStore';

/**
 * How long a mark sits before it is narrated.
 *
 * Long enough to read as "the tutor drew, then spoke" rather than one event;
 * short enough that it never feels like lag. Tuned by ear against the reveal
 * animation in TutorLayer, which takes roughly this long to finish a short
 * stroke.
 */
export const MARK_SETTLE_MS = 700;

let studentWriting = false;
let penDown = false;
let pendingSpeech: ReturnType<typeof setTimeout> | null = null;
let pendingOnEnd: (() => void) | null = null;

/**
 * Drop a line that is waiting out its settle delay.
 *
 * `settle` decides what happens to its onEnd, and the two cases genuinely
 * differ. Silenced (student picked up the pen): fire it, so the turn machine
 * still advances and the mic is not stranded. Superseded (a newer line arrived):
 * do NOT fire it — the newer line owns the turn now, and reopening the mic from
 * the old one would race it. This mirrors how speakTutor treats its own
 * supersede token.
 */
function cancelPending(settle: 'silenced' | 'superseded'): void {
  if (!pendingSpeech) return;
  clearTimeout(pendingSpeech);
  pendingSpeech = null;
  const onEnd = pendingOnEnd;
  pendingOnEnd = null;
  if (settle === 'silenced') onEnd?.();
}

/** True while the student is mid-stroke or has unsubmitted fresh work. */
export function isStudentWriting(): boolean {
  return studentWriting;
}

/**
 * Is the pen physically down right now?
 *
 * `studentWriting` conflates two things — "mid-stroke" and "has unsubmitted
 * fresh work" — and they need separating for exactly one decision: whether a
 * student transcript may hand the floor back.
 *
 * A transcript is not proof the STUDENT spoke. The mic is open through the whole
 * listening turn, so a sibling, a teacher or a television in the room produces a
 * student-role final just as readily. Handing the floor back on that while the
 * student's hand is still moving would let the tutor talk over the pen, which is
 * the precise thing §1 exists to prevent — so the pen wins while it is down.
 *
 * Once it lifts, a transcript is the ordinary "I've written it, look at this"
 * handoff and clearing is right.
 */
export function isPenDown(): boolean {
  return penDown;
}

/** Called by the canvas on pointer down/up. Not a floor decision by itself. */
export function setPenDown(down: boolean): void {
  penDown = down;
}

/**
 * Hand the floor to the student, or take it back.
 *
 * Taking it (`true`) silences the tutor immediately — including an utterance
 * that was waiting out its settle delay. Handing it back does NOT resume
 * anything; whatever was dropped stays dropped.
 */
export function setStudentWriting(writing: boolean): void {
  if (writing === studentWriting) return;
  studentWriting = writing;
  if (writing) {
    cancelPending('silenced');
    stopTutorSpeech();
    reopenTurnAfterSilencing();
  }
}

/**
 * Give the student's turn back after the pen silenced the tutor.
 *
 * This is the other half of `stopTutorSpeech`, and it was missing.
 *
 * On the server transport `stopTutorSpeech` calls `tutorAudioStream.hardStop()`,
 * which by explicit design tears the stream down WITHOUT firing `onIdle` —
 * "callers own what happens next" (lib/tts.ts). The caller here owned nothing.
 * Every other hardStop site in useWebSocket follows it with `beginListeningTurn()`;
 * pen-down was the one that did not.
 *
 * That left `voiceStatus` at 'speaking' with no audio playing and no onIdle
 * still to come — and because app/page.tsx gates `setTransmitting` on
 * `voiceStatus === 'listening'`, the student's microphone frames stopped being
 * SENT for the rest of the session. Not a muted mic: an open one whose audio
 * went nowhere. Tapping "Check my work" does not recover it either, because
 * submitCanvasWork never touches voiceStatus.
 *
 * So: student writes while the tutor is talking — which §1 actively invites —
 * and is never heard again. That is Manjusha's "after tutor writing something
 * breaks from frontend, it's not listening", and it is a better fit for the
 * report than the transcript_final fix, which cannot even fire once the frames
 * have stopped being transmitted.
 *
 * Only from 'speaking': that is the state this function just caused. Reopening
 * from 'processing' would abandon a turn the server is still working on, and
 * reopening from 'listening' would mint a fresh turn id on every pen stroke.
 */
function reopenTurnAfterSilencing(): void {
  const store = useNumeraStore.getState();
  if (store.voiceStatus !== 'speaking') return;
  store.beginListeningTurn();
}

export interface TutorSayOptions {
  /**
   * True when this turn also drew on the canvas. Delays the words by
   * MARK_SETTLE_MS so the mark is seen before it is described.
   */
  afterMarks?: boolean;
  /**
   * Runs when the audio finishes — and ALSO when the utterance is dropped or
   * superseded, with no audio ever playing.
   *
   * That unconditional guarantee is the whole point. The voice turn machine
   * reopens the mic from this callback (half-duplex, voice contract §12), so a
   * silenced utterance that never called back would leave the student unable to
   * speak for the rest of the session — a far worse outcome than the tutor
   * talking over their pen.
   */
  onEnd?: () => void;
  /** Injection seam for tests. Defaults to the real TTS pipeline. */
  speak?: (text: string, onEnd?: () => void) => void;
}

/**
 * Say something as the tutor, if the tutor is allowed to speak.
 *
 * Returns false when the utterance was dropped because the student has the
 * floor — callers still render the text, they just don't get audio. Rendering
 * and speaking are deliberately separate: the transcript stays complete even
 * when the room is quiet.
 */
export function tutorSay(text: string, options: TutorSayOptions = {}): boolean {
  const { onEnd } = options;
  if (!text) {
    onEnd?.();
    return false;
  }
  if (studentWriting) {
    onEnd?.(); // §1 — silence while the student writes, but never strand the turn
    return false;
  }

  cancelPending('superseded');
  const speak = options.speak ?? speakTutor;

  if (!options.afterMarks) {
    speak(text, onEnd);
    return true;
  }

  pendingOnEnd = onEnd ?? null;
  pendingSpeech = setTimeout(() => {
    pendingSpeech = null;
    pendingOnEnd = null;
    // They may have picked the pen back up during the pause.
    if (studentWriting) onEnd?.();
    else speak(text, onEnd);
  }, MARK_SETTLE_MS);
  return true;
}

/** Drop any pending utterance and give the floor back. For teardown and tests. */
export function resetTutorSpeech(): void {
  cancelPending('superseded');
  studentWriting = false;
  penDown = false;
}

/**
 * Handing the voice floor back around a REST submission.
 *
 * `submitVoiceTurn` has always driven the turn machine by hand: PROCESSING
 * while the request is out, SPEAKING while the reply is voiced, then a fresh
 * LISTENING turn — or WAITING — once the audio ends (voice contract §12,
 * half-duplex). Every OTHER submission skipped it entirely. A typed answer, an
 * option pick, "Check my work", Explain Again and Explain-it-back all mint a
 * submission turn with `beginSubmissionTurn()`, send it, render the reply and
 * speak it without touching `voiceStatus` once.
 *
 * Two things break when they don't, and both are things Manjusha has reported.
 *
 * The mic stays OPEN across the request. `app/page.tsx` computes
 * `listening = voiceStatus === 'listening' && …` and transmits on it, so for
 * the whole round trip the room is still being transcribed against a question
 * the student has just answered another way — a sibling or a television then
 * submits a second answer over the top of theirs.
 *
 * And when the tutor stops speaking, no new listening turn is minted. The
 * server clears its latched turn fields after each turn, so `currentTurnId` is
 * still the SUBMISSION turn it has already resolved; whatever the student says
 * next is attributed to a closed turn and nothing comes back. The mic is open,
 * the level meter moves, and the tutor never answers. That is "when this input
 * option in the canvas is pressed, voice is not listening" (26 Aug), and it is
 * the same shape as rows 5 and 36 — the voice dying after the first question
 * rather than at random.
 *
 * The rule these three functions exist to keep: anything that calls
 * `beginSubmissionTurn()` owes the floor back. `lib/__tests__/voiceFloor.test.ts`
 * asserts it against the source so a sixth submission path cannot forget.
 *
 * All three no-op unless a voice session is actually running. In a typed-only
 * session `voiceStatus` is 'idle', and minting listening turns there would put
 * a student who never opened the mic into a voice turn loop.
 *
 * Deliberately NOT wired into the ordering guard (`acceptResponse` returning
 * false). A response is rejected there because something newer has superseded
 * it, and that newer turn owns the floor — reopening the mic from the stale one
 * would race a request that is still out.
 */

/** Submission is in flight: close the mic so the room cannot answer for them. */
export function closeMicForSubmission(): void {
  const store = useNumeraStore.getState();
  if (store.voiceStatus === 'idle') return;
  store.setVoiceStatus('processing');
}

/**
 * The reply has landed and is about to be spoken.
 *
 * Returns the `onEnd` that hands the floor back, or undefined when no voice
 * session is running. Pass it straight to `tutorSay` — which guarantees it
 * fires even when the utterance is empty, dropped or superseded, so the floor
 * cannot be stranded by a turn the tutor had nothing to say on (Phase 3, where
 * saying nothing is the whole point).
 *
 * Reads `expectsStudentResponse` / `allowVoiceInput` out of the store at the
 * moment the audio ends rather than capturing them, so it makes the same
 * decision as the streaming transport's `onIdle` from the same two fields —
 * both of which this turn's `setTutorTurn` has already written.
 */
export function takeFloorForReply(): (() => void) | undefined {
  const store = useNumeraStore.getState();
  if (store.voiceStatus === 'idle') return undefined;
  store.setVoiceStatus('speaking');
  return () => {
    const s = useNumeraStore.getState();
    if (s.voiceStatus !== 'speaking') return; // superseded meanwhile
    // A reply that expects no answer, or forbids voice, parks rather than
    // reopening: minting a listening turn there invites an answer the backend
    // will reject.
    if (!s.expectsStudentResponse || !s.allowVoiceInput) {
      s.setVoiceStatus('waiting');
      return;
    }
    s.beginListeningTurn();
  };
}

/**
 * The submission failed — give the student their turn back.
 *
 * Only from 'processing', which is the state `closeMicForSubmission` just
 * caused. Reopening from anything else would tread on a turn something else
 * now owns.
 */
export function reopenFloorAfterFailure(): void {
  const store = useNumeraStore.getState();
  if (store.voiceStatus !== 'processing') return;
  store.beginListeningTurn();
}

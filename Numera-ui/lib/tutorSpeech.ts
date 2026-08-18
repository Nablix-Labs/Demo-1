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
  }
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
}

/**
 * Announcing a phase change to the student.
 *
 * Phase 0 → 1 has always announced itself: DiagnosticClient renders
 * `diagnostic_transition_message`. Phases 2 and 3 never did — the backend sends
 * `phase_transition_message` / `phase_transition_voice`, and until now nothing
 * in the frontend read either field, so guided practice and independent
 * practice both opened cold with a question and no framing.
 *
 * Kept separate from the response handlers because all three of them (typed
 * answer, voice turn, canvas submit) need the same behaviour, and the guard
 * below is the part that is easy to get wrong.
 */

export interface PhaseTransitionFields {
  current_phase?: string | null;
  phase_transition_message?: string | null;
  phase_transition_voice?: string | null;
}

export interface PhaseAnnouncement {
  /** Shown in the chat and the trail, ahead of the reply itself. */
  text: string;
  /** Spoken ahead of the reply. Falls back to the shown text. */
  voice: string;
}

/**
 * The announcement for this response, or null when there is nothing to say.
 *
 * Guarded on the phase actually having changed rather than on the field merely
 * being present: a backend that echoes the transition message on every turn of
 * the new phase would otherwise re-announce it on each reply. `previousPhase`
 * must be read BEFORE the store is advanced, or the comparison is always false.
 */
export function phaseAnnouncement(
  res: PhaseTransitionFields,
  previousPhase: string,
): PhaseAnnouncement | null {
  const message = res.phase_transition_message?.trim();
  if (!message) return null;

  const next = res.current_phase?.trim();
  // No phase on the response means we cannot tell a transition from an echo,
  // so say nothing rather than risk repeating it every turn.
  if (!next || next === previousPhase) return null;

  return { text: message, voice: res.phase_transition_voice?.trim() || message };
}

/**
 * The tutor's line for this turn, with the transition in front of it.
 *
 * Deliberately one utterance rather than two `tutorSay` calls: overlapping TTS
 * is how this codebase previously ended up with two tutor voices at once, and
 * the fix for that is not worth undoing for a greeting.
 */
export function withTransitionVoice(announcement: PhaseAnnouncement | null, reply: string): string {
  if (!announcement) return reply;
  if (!reply.trim()) return announcement.voice;
  return `${announcement.voice} ${reply}`;
}

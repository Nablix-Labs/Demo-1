/**
 * The review a student has ALREADY finished, as the login response carries it.
 *
 * A student whose journey is in REVIEW is sent straight to the Review screen on
 * login, and login clears any stored session id on purpose (a stale one opened
 * the wrong topic's review — #359). So the screen arrived with no session to
 * read and said "Results not ready… try again", while the login response had
 * the whole summary in `last_journey_state.phase_payload.review_summary`:
 * mastery and every micro-skill's outcome (ST015, 28 Sep 2026).
 *
 * Read defensively: every field is optional, and a shape we do not recognise
 * is "nothing to show", never an error (see backend-deletes-break-frontend).
 */

export interface LoginReviewSkill {
  id: string;
  status: string;
  highestSupport: string | null;
}

export interface LoginReview {
  topicId: string | null;
  masteryStatus: string | null;
  topicStatus: string | null;
  skills: LoginReviewSkill[];
}

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null);

export function loginReviewFrom(lastJourneyState: unknown): LoginReview | null {
  const state = obj(lastJourneyState);
  if (!state || str(state.current_phase)?.toUpperCase() !== 'REVIEW') return null;
  const summary = obj(obj(state.phase_payload)?.review_summary);
  if (!summary) return null;
  const skills = (Array.isArray(summary.micro_skill_results) ? summary.micro_skill_results : [])
    .map(obj)
    .filter((s): s is Obj => s !== null && str(s.micro_skill_id) !== null)
    .map((s) => ({
      id: str(s.micro_skill_id)!,
      status: str(s.final_status) ?? 'UNKNOWN',
      highestSupport: str(s.highest_support_used),
    }));
  if (!skills.length) return null;
  return {
    topicId: str(summary.topic_id) ?? str(state.topic_id),
    masteryStatus: str(summary.mastery_status) ?? str(state.mastery_status),
    topicStatus: str(state.topic_status),
    skills,
  };
}

/** Plain-English wording for a skill outcome. Unknown codes are shown as-is, tidied. */
export function skillOutcomeLabel(status: string): string {
  switch (status) {
    case 'INDEPENDENTLY_VERIFIED': return 'Done on your own';
    case 'VERIFIED_WITH_SUPPORT': return 'Done with help';
    case 'RESCUE_REQUIRED': return 'Needs more practice';
    default: return status.toLowerCase().replace(/_/g, ' ');
  }
}

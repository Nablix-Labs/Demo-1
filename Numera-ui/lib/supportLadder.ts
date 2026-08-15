/**
 * The support ladder — §6 of the Phase 2 Guided Learning spec.
 *
 * The spec's ladder runs question → hint → visual cue → scaffold → parallel
 * example → tutor solved, one rung per request, never skipping ahead.
 *
 * The Tutor Backend owns which rung a student is allowed to reach: that decision
 * depends on attempt history and the Student Model, neither of which lives here.
 * This module does the one part that IS the frontend's job — given what the last
 * `/interaction` response authorised, work out what "Need help?" should reveal
 * next, and stop when there is nothing left.
 *
 * ── Why this exists at all (3 Aug 2026) ─────────────────────────────────────
 * `POST /hint/request` was deleted in the Schema 3.0 refactor, so the button
 * that used to call it now 404s and every press reports "no hint available".
 * The ladder is not gone though — the backend still sends hint text (as the turn
 * message when `conversation_action` is GIVE_HINT), visual cues and scaffold
 * steps on the normal turn response. This reads the rungs off what already
 * arrives instead of calling an endpoint that no longer exists.
 *
 * PARALLEL_EXAMPLE and TUTOR_SOLVED are in the order because they are in the
 * spec's ladder, but no response field carries them today, so `availableSupport`
 * can never return them. That is deliberate: the gap is recorded in
 * docs/PHASE2-GUIDED-BACKEND-ASKS.md (C7) rather than papered over with a rung
 * the UI would render empty.
 */

export const SUPPORT_ORDER = [
  'HINT',
  'VISUAL_CUE',
  'SCAFFOLD',
  'PARALLEL_EXAMPLE',
  'TUTOR_SOLVED',
] as const;

export type SupportRung = (typeof SUPPORT_ORDER)[number];

/**
 * The support-bearing parts of a turn response, already unpacked.
 *
 * Everything is optional because a turn may authorise nothing at all — which is
 * the normal case on a first attempt, and must read as "no support yet" rather
 * than as missing data.
 */
export interface AuthorisedSupport {
  /** Tutor message from a turn whose conversation_action was GIVE_HINT. */
  hintText?: string | null;
  /** Backend `show_visual_cue` — it decides whether a picture is allowed. */
  showVisualCue?: boolean;
  /** Backend `show_scaffold_panel`, and a step actually being present. */
  showScaffoldPanel?: boolean;
  hasScaffoldStep?: boolean;
}

/**
 * The rungs that are both authorised AND have something to render.
 *
 * The second half of that matters: `show_visual_cue: true` with no cue payload
 * would open an empty card, which reads to a student as the tutor failing rather
 * than as the tutor withholding. A rung with no content is not available.
 */
export function availableSupport(support: AuthorisedSupport): SupportRung[] {
  const rungs: SupportRung[] = [];
  if (support.hintText) rungs.push('HINT');
  if (support.showVisualCue) rungs.push('VISUAL_CUE');
  if (support.showScaffoldPanel && support.hasScaffoldStep) rungs.push('SCAFFOLD');
  return rungs;
}

/**
 * The next rung to reveal, or null when the ladder is exhausted.
 *
 * `shown` is the highest rung already revealed for the current question. Rungs
 * are ordered, so "next" means the first available one strictly above it — a
 * student who has already seen the scaffold is not walked back down to the hint.
 */
export function nextSupport(
  shown: SupportRung | null,
  available: SupportRung[],
): SupportRung | null {
  const floor = shown ? SUPPORT_ORDER.indexOf(shown) : -1;
  for (const rung of SUPPORT_ORDER) {
    if (SUPPORT_ORDER.indexOf(rung) > floor && available.includes(rung)) return rung;
  }
  return null;
}

/**
 * What to tell a student who asks for help when the ladder has nothing left.
 *
 * Deliberately not an apology and not an error. The tutor has not failed — it
 * has given everything this turn allows, and the useful next move is for the
 * student to say which part is stuck, which is also what unblocks the backend
 * into authorising the next rung.
 */
export const LADDER_EXHAUSTED =
  "I've shown you everything I can for this one. Tell me which part is confusing and we'll work on just that.";

/** Shown when the request for a hint failed rather than came back empty. */
export const HINT_UNAVAILABLE =
  "I couldn't fetch a hint just then. Give it another try in a moment.";

/**
 * What the hint card should say when the request threw.
 *
 * A hint request has two very different failure shapes and they must not read
 * the same. Since 11 Aug 2026 the backend answers HELP_REQUEST only by
 * replaying support it has already authorised, and returns 409 NO_ACTIVE_SUPPORT
 * when there is none — which is not an outage, it is the ladder being empty, so
 * it earns the same wording as an exhausted ladder. Anything else (a 500, a
 * dropped connection) really is a failure and has to say so instead of quietly
 * claiming the tutor has nothing more to give.
 *
 * Either way this returns a string: the caller's job is to never leave the card
 * blank, because a hint card that never resolves looks identical to a frozen app.
 */
export function hintFailureMessage(error: unknown): string {
  const response = (error as { response?: { status?: number; data?: unknown } })?.response;
  if (response?.status !== 409) return HINT_UNAVAILABLE;
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' && detail.startsWith('NO_ACTIVE_SUPPORT')
    ? LADDER_EXHAUSTED
    : HINT_UNAVAILABLE;
}

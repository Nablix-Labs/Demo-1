/**
 * A Phase 3 turn that came back 200 and left nothing on the screen.
 *
 * This is the other half of `lib/questionOptions.ts`. Both exist because of one
 * backend behaviour: silent mode strips `student_model_event` from every Phase 3
 * interaction reply —
 *
 *     phase3_silent = (
 *         session.current_phase == "INDEPENDENT_PRACTICE"
 *         and previous_phase != "GUIDED_PRACTICE"
 *         and session.intervention is None
 *     )
 *     ...
 *     student_model_event=None if phase3_silent else session.student_model_event,
 *     routing=None if phase3_silent or stored_event is None else ...
 *
 * (`interaction_service.py:2605` and `:2685`). The strip is deliberate and
 * correct — the event carries `tutor_view`, which holds the answer — so neither
 * module tries to unstrip it. `GET /session` re-declares the same field as the
 * PUBLIC event and serves it in every phase, answers already removed, which is
 * why re-reading the session is the established repair for a stripped turn
 * payload (see `numera-frontend-traps`).
 *
 * `optionsMissing` covers the case where the question survived but its choices
 * did not. This covers the harder one: the reply took the QUESTION away too.
 *
 * ── The run this comes from ────────────────────────────────────────────────
 *
 * Sanya, 14 Sep 2026, issue #309: "phase3 is not moving to phase 4 or to next
 * question untill i refresh". Her session, SESSION682a325d25a84d9c997c85ecf631ee03,
 * in the backend log:
 *
 *   20:26:14.754  student_model_event=PREREQUISITE_ROUTE_RESOLVED
 *                 payload_type=PREREQUISITE_REMEDIATION
 *                 routing_reason_code=PREREQUISITE_REMEDIATION_REQUIRED
 *   20:26:14.851  POST /interaction  200
 *   ── 82 seconds with not one request from her browser ──
 *   20:27:36      GET /session       (she refreshed)
 *   20:27:41      GET /session
 *
 * Her third failure on the same checkpoint escalated to a prerequisite route,
 * and `session_service.py:1480` halts the topic for it: `question_id` is set to
 * None and a backend-authored pause message is written to the record. But that
 * branch sets no `intervention`, so `phase3_silent` — which excepts an
 * intervention precisely so a halted topic is never silenced — did not except
 * this halt. The reply reached the browser with no event, no routing and no
 * question. There was nothing to render and nothing to press.
 *
 * The real fix is one clause in that guard and it is Chiru's. This is the
 * frontend refusing to sit on a dead screen in the meantime, and it is worth
 * having regardless: it covers the next halt nobody has thought of yet, because
 * it keys on the student having nothing to do rather than on any one reason
 * code.
 */

import { isPhase3 } from '@/lib/phase3';

export interface Phase3StallState {
  /** The backend's phase, not the route. */
  phase: string | null | undefined;
  /** The question on screen. Null is the state this module is about. */
  questionId: string | null | undefined;
  /** Already known to be paused — the pause panel is showing. */
  paused: boolean;
  /** §11 intervention stage. Anything but NONE has its own screen. */
  interventionStage: 'NONE' | 'COLLECTING' | 'AWAITING_REVIEW';
}

/**
 * Is the student in Phase 3 with nothing to answer and nothing explaining why?
 *
 * Every clause narrows it to that one state, and each one is load-bearing:
 *
 *   phase       Only Phase 3 strips the reply, so only Phase 3 can arrive here
 *               with a question it did not mean to drop. Re-reading the session
 *               on an empty question elsewhere would put a GET on the wire
 *               during orientation, which legitimately has no question at all.
 *   questionId  The symptom itself.
 *   paused      A pause is a rendered ENDING, not a stall: the panel is on
 *               screen with the backend's own sentence on it. Re-reading would
 *               fetch the same record again and change nothing.
 *   intervention  The §11 popup and the awaiting-review screen are both live
 *               states with their own UI. Neither is stuck.
 */
export function stalledWithNothingToAnswer(state: Phase3StallState): boolean {
  if (!isPhase3(state.phase)) return false;
  if (state.questionId) return false;
  if (state.paused) return false;
  return state.interventionStage === 'NONE';
}

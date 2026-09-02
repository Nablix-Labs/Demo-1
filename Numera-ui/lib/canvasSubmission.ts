/**
 * What a /canvas/submit reply should put on screen.
 *
 * Split out of useDemoTutor because the shape of that reply is not what the
 * client assumed. On 12 Aug 2026 Sanya's Phase 3 payload arrived with both
 * `ocr` and `tutor` null — correctly, because Independent Practice is silent
 * and the tutor says nothing — and the client read straight through both. The
 * TypeError landed in the submit catch, so a submission the backend had
 * ACCEPTED, graded and locked was announced to the student as "the tutor
 * couldn't take that submission", with their work still on the canvas inviting
 * them to submit it a second time.
 *
 * The rule is that every part of the reply is optional and the absence of one
 * is never an error: render what arrived, stay silent about what did not.
 */

export interface CanvasTrailEntry {
  text: string;
  meta: string;
}

export interface CanvasSubmissionView {
  /** The OCR read-back, or null when the reply carried no OCR block. */
  ocr: CanvasTrailEntry | null;
  /** The tutor's words, or null when the tutor said nothing (Phase 3). */
  tutorText: string | null;
  /** Verdict label for the trail. Undefined keeps the entry unlabelled. */
  tutorEvaluation: string | undefined;
}

/**
 * Declared by what this function READS, not by the full response type.
 *
 * Deliberate: the reply is whatever the backend sent that day. Demanding the
 * complete OcrResult/TutorResult here would be a claim about fields we never
 * touch, and it is exactly that kind of claim — "these are always present" —
 * that produced the bug above.
 */
type CanvasReply = {
  ocr?: {
    raw_ocr_text?: string;
    detected_equation?: string;
    confidence?: number;
    needs_clarification?: boolean;
  } | null;
  tutor?: { tutor_message?: string; evaluation?: string } | null;
} | null | undefined;

export function canvasSubmissionView(res: CanvasReply): CanvasSubmissionView {
  const ocr = res?.ocr ?? null;
  const tutor = res?.tutor ?? null;
  const tutorText = tutor?.tutor_message?.trim() || null;
  return {
    ocr: ocr
      ? {
          // An OCR block with nothing readable in it still deserves a trail
          // entry: the student did submit, and a missing line reads as a lost
          // submission.
          text: ocr.raw_ocr_text || ocr.detected_equation || 'Canvas submitted.',
          meta: `OCR ${Math.round((ocr.confidence ?? 0) * 100)}%${
            ocr.needs_clarification ? ' · needs clarification' : ''
          }`,
        }
      : null,
    tutorText,
    // Only label the trail when there is something to label.
    tutorEvaluation: tutorText ? tutor?.evaluation : undefined,
  };
}

/**
 * Give a canvas reply its OWN identity before the response gate reads it.
 *
 * `/canvas/submit` returns an `InteractionResponse`, and the backend stamps it
 * with `accepted_turn_id = session.last_processed_turn_id` and the session's
 * current `interaction_state_version` — but nothing on that path advances
 * either field. `record_canvas_submission` and `_apply_schema_event` both leave
 * them untouched, and the two places that do bump the version
 * (`_option_selected_interaction_response`, `_process_interaction`) are
 * `/interaction` only. Measured against the live backend, 1 Sep 2026:
 *
 *   POST /interaction   (turn_id TURN-AAA) → version 1, accepted_turn_id TURN-AAA
 *   POST /canvas/submit (turn_id TURN-BBB) → version 1, accepted_turn_id TURN-AAA
 *
 * So a canvas reply arrives wearing the PREVIOUS turn's name. `shouldApply`
 * sees a turn id it has already applied at the same version and drops the whole
 * reply, and `submitCanvasWork` returns before syncBackendSession, before the
 * transcript line and before the tutor's message. That is Manjusha's report:
 * the backend advanced the question and said "Nice work. Here is the next
 * question.", and the screen did not move at all — no question, no message, no
 * error. Every canvas Check after a typed turn was being swallowed.
 *
 * The gate is not wrong; the identity it was given is. `submission_id` is this
 * submission's own id — measured, it is the client's `turn_id` echoed straight
 * back, which is the ideal key here: minted per submission by
 * `beginSubmissionTurn`, and deliberately REUSED verbatim on a retry, so it
 * dedupes a resend for the same reason the backend does. Using it restores
 * exactly what the gate was built to do rather than switching it off:
 *
 *   - a first reply applies once, because its id has not been seen;
 *   - a resend of the same submission is still deduped, because it carries the
 *     same submission_id;
 *   - a canvas reply that really IS out of date still loses, because the
 *     version comparison is untouched and an older version never wins.
 *
 * The backend fix — advance both fields on a canvas turn, as /interaction does
 * — is still the right one and is Chiru's. This makes the client correct on its
 * own side either way: once the backend stamps a real turn id, the reply simply
 * arrives with a fresh version and this changes nothing.
 */
export function canvasResponseIdentity<
  T extends { accepted_turn_id?: string | null; submission_id?: string | null },
>(res: T): T {
  const own = res.submission_id?.trim();
  if (!own) return res;
  return { ...res, accepted_turn_id: own };
}

/** How a canvas snapshot was submitted. Mirrors the backend's own two roles. */
export type SubmissionRole = 'STANDALONE_ATTEMPT' | 'VOICE_ATTACHMENT';

/**
 * May this submission's reply move the session on?
 *
 * Only a standalone attempt. A `VOICE_ATTACHMENT` is the canvas that happened
 * to be on screen while the student was speaking: the backend reads its OCR and
 * returns the session **unchanged** — `record_canvas_attachment` stores the
 * record and explicitly does not count a second attempt — so applying its reply
 * would advance a question, phase, version, attempt counter or lock that
 * nothing actually moved.
 *
 * Today the frontend has exactly one `submitCanvas` call site and it always
 * sends `STANDALONE_ATTEMPT`, so the rule already holds — by construction, not
 * by enforcement. That is the reason to write it down rather than a reason not
 * to: the rule is invisible at the moment someone adds the second call site,
 * which is precisely when it would be broken.
 */
export function advancesSession(role: SubmissionRole): boolean {
  return role === 'STANDALONE_ATTEMPT';
}

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

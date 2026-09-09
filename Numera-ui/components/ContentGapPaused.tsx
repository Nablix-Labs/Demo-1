'use client';

/**
 * ContentGapPaused — "that is everything I have ready for this topic".
 *
 * A content gap means the authored question does not exist. It is not mastery,
 * not an intervention, and not a transient error, and it has been read as all
 * three. In the ST017 run the only authored Independent question for T01.M7 had
 * already been used, and with nothing on this side saying "stop", the client
 * asked for a fresh one twice — journey versions 12 then 13.
 *
 * So this screen's real job is to be an ending rather than a wait. Three things
 * it deliberately does NOT do:
 *
 *   - Offer a retry. There is nothing to retry: the question does not exist,
 *     and the backend persists the pause precisely so nothing asks again.
 *   - Claim mastery, or route to Review. The student did not finish the topic;
 *     we ran out of questions. Saying otherwise would put a completion in front
 *     of them that the record does not support.
 *   - Explain the cause. A missing question is our problem to fix, not
 *     something to hand a child mid-lesson.
 *
 * Distinct from InterventionPaused beside it: that one follows a student being
 * asked for input and having given it. Nobody has been asked anything here.
 *
 * The wording is the backend's own CONTENT_GAP_MESSAGE (session_service.py) —
 * it arrives on the record as `message`, and the copy is content the backend
 * owns. Rendered from the record when it is there, with the same sentence as a
 * fallback so a stripped field cannot leave the panel blank.
 */

import { BookmarkCheck } from 'lucide-react';

/** Mirrors CONTENT_GAP_MESSAGE, for when the record does not carry it. */
const FALLBACK = 'That is everything I have ready for this topic right now. Your work so far is saved.';

export default function ContentGapPaused({ message }: { message?: string | null }) {
  return (
    <div
      role="status"
      className="mx-auto max-w-md rounded-2xl border border-muted-gray bg-white/95 px-6 py-6 text-center shadow-sm"
    >
      <BookmarkCheck className="mx-auto mb-3 h-7 w-7 text-slate-blue" aria-hidden />
      <h2 className="font-serif text-[19px] text-ink">That’s everything for now</h2>
      <p className="mt-2 text-[13.5px] leading-relaxed text-slate-blue">
        {message?.trim() || FALLBACK}
      </p>
      <p className="mt-3 text-[12.5px] text-slate-blue/80">
        {/* The one thing a student actually needs to know: this is not their
            fault and nothing they did is gone. Same reassurance as the
            intervention pause, for the same reason — a screen with dead
            controls and no explanation reads as broken. */}
        Nothing you did went wrong, and none of your work is lost.
      </p>
    </div>
  );
}

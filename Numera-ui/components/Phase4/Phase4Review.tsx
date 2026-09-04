'use client';

/**
 * Phase 4 — Review & Feedback (§8).
 *
 * Three panes: the Phase 3 journey on the left, the Tutor Live Review filling
 * the middle, compact feedback on the right. §8.4 says the review workspace
 * "should visually dominate the screen", so the side panes are fixed-width and
 * the centre takes everything that is left.
 *
 * The sequence is §8.8:
 *   no wrong answers   → straight to the Learning Summary
 *   one wrong answer   → one replay, then the summary
 *   several            → replays in order, then the summary
 */

import { useCallback, useEffect } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { stopTutorSpeech } from '@/lib/tts';
import { journeyRows, reviewProgressLabel, replayAt, humanLabel } from '@/lib/phase4Review';
import ReviewRail from './ReviewRail';
import TutorStage from './TutorStage';
import FeedbackRail from './FeedbackRail';
import LearningSummary from './LearningSummary';
import type { Phase4Review as Phase4ReviewPayload } from '@/lib/api';

/**
 * The phase this screen IS.
 *
 * Set on arrival because `applyCanvasDraw` refuses every tutor mark while the
 * store still reads Phase 3 (useNumeraStore.ts:1308) — correctly, since Phase 3
 * forbids tutor ink over an independent attempt. Phase 4 only begins once those
 * requirements are complete (§2.9), so the attempt that rule protects is over;
 * without this the review board silently renders blank and nothing reports why.
 */
const PHASE_4 = 'PHASE_4_REVIEW';

export default function Phase4Review({
  review,
  onEnd,
  replayIndex,
  onReplayIndexChange,
}: {
  review: Phase4ReviewPayload;
  /** Leave the review — the backend's recommended_next_action is the label. */
  onEnd: () => void;
  /**
   * Which replay is on the board; -1 is the Learning Summary.
   *
   * Controlled by the route rather than held here, because the header lives in
   * the page shell and shows "Review progress 2 of 3" — two copies of this
   * number would be two things to keep in step, and the one on screen would be
   * the one that drifted.
   */
  replayIndex: number;
  onReplayIndexChange: (next: number) => void;
}) {
  const setCurrentPhase = useNumeraStore((s) => s.setCurrentPhase);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  useEffect(() => {
    setCurrentPhase(PHASE_4);
    return () => {
      // The tutor layer is global and the marks outlive the route. Leaving them
      // behind puts this topic's corrections on the next screen's canvas.
      stopTutorSpeech();
      clearTutorMarks();
    };
  }, [setCurrentPhase, clearTutorMarks]);

  const total = review.tutor_replays.length;
  const replay = replayIndex >= 0 ? replayAt(review, replayIndex) : null;
  const rows = journeyRows(review);

  const goTo = useCallback((next: number) => {
    // The player narrates on mount; a replay left talking underneath the next
    // one is two tutor voices at once.
    stopTutorSpeech();
    onReplayIndexChange(next);
  }, [onReplayIndexChange]);

  return (
    // No heading of its own: the topic title and the review chips are in the
    // page header on the live route, and a second title directly beneath it
    // reads as two pages.
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 flex gap-4 items-start">
        {/* Left — the Phase 3 journey. Omitted entirely when there is nothing
            to correct, so the summary is not sitting beside an empty column. */}
        {rows.length > 0 && (
          <div className="w-[262px] flex-shrink-0 overflow-y-auto max-h-full">
            <ReviewRail rows={rows} activeReplayIndex={replayIndex} onSelect={goTo} />
          </div>
        )}

        {/* Centre — dominant (§8.4) */}
        <div className="flex-1 min-w-0 h-full min-h-[520px] flex">
          {replay ? (
            <TutorStage
              // Remounts per replay, so the player starts the new explanation
              // from its first step instead of resuming the previous position.
              key={replay.review_item_id}
              replay={replay}
              progressLabel={reviewProgressLabel(replayIndex, total)}
            />
          ) : (
            <div className="flex-1 min-w-0 overflow-y-auto">
              <LearningSummary review={review} onEnd={onEnd} />
            </div>
          )}
        </div>

        {/* Right — feedback, and the control that moves the review on. The
            forward action lives here rather than in the transport bar because
            it advances the REVIEW, not the playback: putting it beside pause
            and speed invited it being read as "next step". */}
        {replay && (
          <div className="w-[300px] flex-shrink-0 overflow-y-auto max-h-full">
            <FeedbackRail
              review={review}
              replay={replay}
              onContinue={() => goTo(replayIndex + 1 < total ? replayIndex + 1 : -1)}
              continueLabel={replayIndex + 1 < total ? 'Continue review' : 'Learning summary'}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The chips and the way out, for the page header.
 *
 * Exported separately rather than rendered inside the review because the route
 * owns the header (PageShell) — putting a second bar of its own directly under
 * it is the two-headings problem this component's own note warns about.
 */
export function Phase4HeaderActions({
  review,
  replayIndex,
  onEnd,
}: {
  review: Phase4ReviewPayload;
  /** -1 once the student has reached the summary. */
  replayIndex: number;
  onEnd: () => void;
}) {
  const total = review.tutor_replays.length;
  // Counted over the REPLAYS, not the journey: "2 of 3" over eight questions
  // would tell a student who got six right that they have six corrections to
  // sit through. On the summary the review is finished, so it reads full.
  const done = replayIndex < 0 ? total : Math.min(replayIndex + 1, total);
  const fraction = total > 0 ? done / total : 1;

  return (
    <div className="flex items-center gap-2.5 flex-wrap justify-end">
      {total > 0 && (
        <div className="rounded-xl border border-muted-gray bg-white px-3.5 py-2 min-w-[150px]">
          <div className="text-[11px] text-slate-blue">Review progress</div>
          <div className="text-[13px] font-semibold text-ink">{done} of {total}</div>
          <div
            role="progressbar"
            aria-label="Review progress"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={done}
            className="mt-1.5 h-1.5 rounded-full bg-muted-gray overflow-hidden"
          >
            <div
              className="h-full rounded-full bg-focus-navy transition-[width] duration-300"
              style={{ width: `${fraction * 100}%` }}
            />
          </div>
        </div>
      )}

      <HeaderChip label="Mastery" value={humanLabel(review.topic_outcome.mastery_status)} />
      <HeaderChip label="Next step" value={humanLabel(review.topic_outcome.recommended_next_action)} />

      <button
        onClick={onEnd}
        className="rounded-xl bg-focus-navy px-5 py-2.5 text-[13px] font-semibold text-white
                   hover:opacity-85 transition-opacity"
      >
        End review
      </button>
    </div>
  );
}

function HeaderChip({ label, value }: { label: string; value: string }) {
  // Nothing to say is rendered as nothing, not as an empty chip: a labelled box
  // with a blank value reads as a value that failed to load.
  if (!value?.trim()) return null;
  return (
    <div className="rounded-xl border border-muted-gray bg-white px-3.5 py-2">
      <div className="text-[11px] text-slate-blue">{label}</div>
      <div className="text-[13px] font-semibold text-ink">{value}</div>
    </div>
  );
}

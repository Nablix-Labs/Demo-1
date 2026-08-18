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

import { useCallback, useEffect, useState } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { stopTutorSpeech } from '@/lib/tts';
import {
  journeyRows, reviewProgressLabel, replayAt, skipsReplay,
} from '@/lib/phase4Review';
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
}: {
  review: Phase4ReviewPayload;
  /** Leave the review — the backend's recommended_next_action is the label. */
  onEnd: () => void;
}) {
  const setCurrentPhase = useNumeraStore((s) => s.setCurrentPhase);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  // Straight to the summary when nothing went wrong (§8.8).
  const [replayIndex, setReplayIndex] = useState(() => (skipsReplay(review) ? -1 : 0));

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
    setReplayIndex(next);
  }, []);

  return (
    // No heading of its own: the topic title is already in the page header on
    // the live route, and a second one directly beneath it reads as two pages.
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 flex gap-4 items-start">
        {/* Left — the Phase 3 journey */}
        <div className="w-[210px] flex-shrink-0 overflow-y-auto max-h-full">
          <ReviewRail rows={rows} activeReplayIndex={replayIndex} onSelect={goTo} />
        </div>

        {/* Centre — dominant */}
        <div className="flex-1 min-w-0 h-full min-h-[520px] flex">
          {replay ? (
            <TutorStage
              // Remounts per replay, so the player starts the new explanation
              // from its first step instead of resuming the previous position.
              key={replay.review_item_id}
              replay={replay}
              progressLabel={reviewProgressLabel(replayIndex, total)}
              hasPrevReplay={replayIndex > 0}
              onPrevReplay={() => goTo(replayIndex - 1)}
              onNextReplay={() => goTo(replayIndex + 1 < total ? replayIndex + 1 : -1)}
              nextLabel={replayIndex + 1 < total ? 'Next review' : 'Learning summary'}
            />
          ) : (
            <div className="flex-1 min-w-0 overflow-y-auto">
              <LearningSummary review={review} onEnd={onEnd} />
            </div>
          )}
        </div>

        {/* Right — compact feedback. Hidden on the summary, which says all of
            this at length; repeating it beside itself is the overcrowding §8.4
            asks us to avoid. */}
        {replay && (
          <div className="w-[280px] flex-shrink-0 overflow-y-auto max-h-full">
            <FeedbackRail review={review} replay={replay} />
          </div>
        )}
      </div>
    </div>
  );
}

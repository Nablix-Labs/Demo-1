'use client';

/**
 * /dev-screens/phase4 — the Phase 4 review running on a fixture.
 *
 * The backend half of Phase 4 does not exist yet (§6.10 never says what Chiru
 * sends here, and his orchestration is unwritten), so this is how the screen is
 * reviewed, demoed and tested until it does. Under /dev-screens, which is
 * already pre-auth and full-bleed in AppFrame, so it needs no routing changes
 * and no login.
 *
 * The toggle covers the branch that has no visible controls of its own: §8.8
 * says a topic with no wrong answers skips the replays entirely, and that path
 * is otherwise unreachable without a second fixture.
 */

import { useMemo, useState } from 'react';
import Link from 'next/link';
import Phase4Review, { Phase4HeaderActions } from '@/components/Phase4/Phase4Review';
import { skipsReplay } from '@/lib/phase4Review';
import { PHASE_4_DEMO } from '@/lib/phase4Demo';

export default function Phase4DevScreen() {
  const [allCorrect, setAllCorrect] = useState(false);
  const [phase4Index, setPhase4Index] = useState<number | null>(null);

  const review = useMemo(() => (
    allCorrect
      ? {
          ...PHASE_4_DEMO,
          topic_outcome: { mastery_status: 'MASTERED', recommended_next_action: 'START_NEXT_TOPIC' },
          question_journey: PHASE_4_DEMO.question_journey.map((q) => ({
            ...q, evaluation: 'CORRECT' as const, review_item_id: null,
          })),
          tutor_replays: [],
          student_insights: {
            ...PHASE_4_DEMO.student_insights,
            // §7.6C/D: with nothing wrong there is no repeated pattern and
            // nothing was repaired, so both sections must disappear.
            learning_pattern_summary: null,
            recent_improvement_summary: null,
          },
        }
      : PHASE_4_DEMO
  ), [allCorrect]);

  // Same rule as the live route: -1 when there is nothing to correct (§8.8),
  // resolved from the fixture rather than defaulted to the first replay.
  const replayIndex = phase4Index ?? (skipsReplay(review) ? -1 : 0);
  const setReplayIndex = setPhase4Index;

  return (
    // `w-full` because the focus-route frame sizes this to its content
    // otherwise, and the review is a full-width three-pane layout.
    <div className="h-screen w-full flex flex-col bg-white p-4 gap-3">
      <div className="flex items-center gap-4 text-[12px] text-slate-blue flex-shrink-0">
        <Link href="/dev-screens" className="font-semibold hover:text-ink">← Dev screens</Link>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={allCorrect}
            onChange={(e) => setAllCorrect(e.target.checked)}
          />
          Every question correct (§8.8 — skips the replays)
        </label>
        <span className="font-semibold text-ink">{review.topic_title}</span>
        <span className="ml-auto">Fixture only. No backend endpoint exists yet.</span>
      </div>

      {/* The header actions render on the live route inside PageShell; here
          they sit above the panes so the fixture exercises them too. */}
      <div className="px-4 py-2 border-b border-muted-gray flex justify-end">
        <Phase4HeaderActions
          review={review}
          replayIndex={replayIndex}
          onEnd={() => undefined}
        />
      </div>

      <div className="flex-1 min-h-0">
        <Phase4Review
          key={allCorrect ? 'all-correct' : 'with-replays'}
          review={review}
          replayIndex={replayIndex}
          onReplayIndexChange={setReplayIndex}
          onEnd={() => undefined}
        />
      </div>
    </div>
  );
}

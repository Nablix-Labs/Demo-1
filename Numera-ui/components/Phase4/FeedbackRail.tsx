'use client';

/**
 * Compact feedback beside the review board (§8.4, Right Pane).
 *
 * Built as the app builds every block of labelled prose — one bordered
 * container, divided rows, a small uppercase label over each — which is exactly
 * the shape the engine's five-category review already uses further down this
 * route. The earlier draft gave each item its own card, icon and tinted
 * background; that is four competing objects next to the board that §8.4 says
 * must dominate, and the section it closes with is "Do not overcrowd this
 * panel".
 *
 * "Repeated pattern" appears only when the engine asserted one. §7.6C makes
 * that field null for a single isolated occurrence precisely so the tutor never
 * tells a student they "always" do something off one mistake, and rendering the
 * heading over an empty box would put that claim back.
 */

import { Chip } from '@/components/PageShell';
import { humanLabel } from '@/lib/phase4Insights';
import type { Phase4Replay, Phase4Review } from '@/lib/api';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section className="px-4 py-3.5">
      <h3 className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">{label}</h3>
      <div className="text-[13px] text-ink leading-relaxed">{children}</div>
    </section>
  );
}

export default function FeedbackRail({
  review,
  replay,
}: {
  review: Phase4Review;
  /** The replay on the board, or null once the replays are finished. */
  replay: Phase4Replay | null;
}) {
  const { learning_pattern_summary, next_practice_focus } = review.student_insights;

  return (
    <aside aria-label="Feedback" className="flex flex-col gap-3">
      <div className="rounded-lg border border-muted-gray bg-white divide-y divide-muted-gray overflow-hidden">
        {/* §7.4: the FIRST point where the reasoning went wrong — not a list of
            every downstream consequence of it. The one accent on this panel,
            because it is the one thing the student is here to understand. */}
        {replay && (
          <section className="px-4 py-3.5 border-l-[3px] border-l-action-orange">
            <h3 className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">
              First error
            </h3>
            <p className="text-[13px] text-ink leading-relaxed">{replay.first_error.summary}</p>
          </section>
        )}

        {learning_pattern_summary?.trim() && (
          <Row label="Repeated pattern">{learning_pattern_summary}</Row>
        )}

        {/* §7.6E: exactly one, never a checklist. */}
        <Row label="Next practice">{next_practice_focus}</Row>
      </div>

      {/* §8.9 Topic Outcome. Separated from the block above because it is the
          state of the whole topic, not feedback on the question on screen —
          and §6.9 makes mastery and routing the backend's, shown as sent. */}
      <div className="rounded-lg border border-muted-gray bg-reading-surface px-4 py-3.5">
        <h3 className="text-[10px] tracking-widest uppercase text-slate-blue mb-1.5">
          Topic outcome
        </h3>
        <Chip tone="solid">{humanLabel(review.topic_outcome.mastery_status)}</Chip>
        <p className="text-[12px] text-slate-blue mt-2">
          Next: {humanLabel(review.topic_outcome.recommended_next_action).toLowerCase()}
        </p>
      </div>
    </aside>
  );
}

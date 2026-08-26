'use client';

/**
 * The Topic Learning Summary (§8.9), shown once the replays are done — or
 * immediately, when the student got everything right (§8.8).
 *
 * Deliberately the same shape as the engine review already rendered further
 * down this route: one bordered container, divided rows, a small uppercase
 * label over each. A student arriving here has seen that block before, and the
 * summary of their topic should not look like a different product.
 *
 * Everything is rendered verbatim from what the engine wrote. §6.9 makes
 * counts, mastery and routing authoritative backend data and §7.7 forbids the
 * engine deciding any of them, so a screen that rephrased or ranked this
 * content would be a third party neither rule allows for.
 *
 * §8.7: no bottom promotional strip — no "You are building…", no "You are
 * strong…", no generic praise card. The engine's strength_summary is specific
 * evidence (§7.6A "Do not use generic ability praise") and a decorated banner
 * beneath it undoes exactly what that rule protects.
 */

import { ChevronRight } from 'lucide-react';
import { insightSections, keyTakeaways, humanLabel } from '@/lib/phase4Insights';
import type { Phase4Review } from '@/lib/api';

export default function LearningSummary({
  review,
  onEnd,
}: {
  review: Phase4Review;
  onEnd: () => void;
}) {
  const sections = insightSections(review.student_insights);
  const takeaways = keyTakeaways(review);

  return (
    <div className="flex flex-col gap-6 max-w-[720px]">
      <div>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue">
          Topic learning summary
        </div>
        <h2 className="text-[19px] font-semibold text-ink mt-1 leading-tight">
          {review.topic_title}
        </h2>
      </div>

      <div className="rounded-lg border border-muted-gray bg-white divide-y divide-muted-gray overflow-hidden">
        {sections.map((section) => (
          <section key={section.key} className="px-5 py-3.5">
            <h3 className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">
              {section.title}
            </h3>
            <p className="text-[13.5px] text-ink leading-relaxed">{section.body}</p>
          </section>
        ))}
      </div>

      {/* §7.9: "approximately 3–5 concise student-specific points". Rendered as
          the engine wrote them — no ids, no error codes (§7.6F). Numbered
          rather than bulleted: these are the notes to take away, and a number
          is what makes a short list read as a set rather than as loose lines. */}
      {takeaways.length > 0 && (
        <section>
          <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2.5">
            Key takeaways
          </div>
          <ol className="rounded-lg border border-muted-gray bg-reading-surface divide-y divide-muted-gray overflow-hidden">
            {takeaways.map((note, i) => (
              <li key={i} className="flex gap-3 px-5 py-3">
                <span className="flex-shrink-0 w-5 text-[12px] font-semibold text-slate-blue tabular-nums">
                  {i + 1}
                </span>
                <span className="text-[13.5px] text-ink leading-relaxed">{note}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Topic outcome and the backend's routing decision — §8.9, and §6.9 makes
          the next action theirs to decide, not a choice offered here. */}
      <div className="flex items-center justify-between gap-4 rounded-lg border border-muted-gray bg-white px-5 py-4">
        <div>
          <div className="text-[10px] tracking-widest uppercase text-slate-blue">Topic outcome</div>
          <div className="text-[15px] font-semibold text-ink mt-0.5">
            {humanLabel(review.topic_outcome.mastery_status)}
          </div>
        </div>
        <button
          onClick={onEnd}
          className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy px-5 py-2.5 text-[13px] font-semibold text-white hover:opacity-80 transition-opacity"
        >
          {humanLabel(review.topic_outcome.recommended_next_action)}
          <ChevronRight size={15} strokeWidth={1.8} />
        </button>
      </div>
    </div>
  );
}

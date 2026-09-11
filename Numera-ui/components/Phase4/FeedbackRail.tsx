'use client';

/**
 * The feedback column: what went wrong, why it matters, and what to do next.
 *
 * Every card is conditional, and that is the design rather than defensiveness.
 * §7.6C: where the engine cannot assert something — a pattern seen once is not
 * a pattern — it returns null, and §8.9 says the section is then hidden. A
 * heading printed over an empty body is the client claiming an insight the
 * engine declined to make.
 *
 * So a student who made one clean mistake sees three cards, and one who has
 * repeated it sees five. Neither is a degraded version of the other.
 */

import { AlertTriangle, Info, RefreshCw, Target, Flag, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/cn';
import { patternSentence } from '@/lib/phase4Review';
import type { Phase4Replay, Phase4Review } from '@/lib/api';

type Tone = 'error' | 'info' | 'warn' | 'focus' | 'go';

const TONE: Record<Tone, { box: string; icon: string }> = {
  error: { box: 'border-red-200 bg-red-50/70', icon: 'text-red-500' },
  info: { box: 'border-sky-200 bg-sky-50/70', icon: 'text-sky-500' },
  warn: { box: 'border-amber-200 bg-amber-50/70', icon: 'text-amber-500' },
  focus: { box: 'border-indigo-200 bg-indigo-50/70', icon: 'text-indigo-500' },
  go: { box: 'border-emerald-200 bg-emerald-50/70', icon: 'text-emerald-600' },
};

function Card({
  tone,
  icon: Icon,
  title,
  children,
}: {
  tone: Tone;
  icon: typeof AlertTriangle;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn('rounded-xl border p-3.5', TONE[tone].box)}>
      <h3 className="flex items-center gap-2 text-[13px] font-semibold text-ink mb-1.5">
        <Icon size={15} strokeWidth={2.1} className={cn('flex-shrink-0', TONE[tone].icon)} aria-hidden />
        {title}
      </h3>
      <div className="text-[12.5px] text-ink/85 leading-relaxed">{children}</div>
    </section>
  );
}

export default function FeedbackRail({
  review,
  replay,
  onContinue,
  continueLabel,
}: {
  review: Phase4Review;
  replay: Phase4Replay;
  /** Advance to the next replay, or to the summary on the last one. */
  onContinue: () => void;
  continueLabel: string;
}) {
  const { learning_pattern_summary, next_practice_focus } = review.student_insights;
  const whyItMatters = replay.first_error.why_it_matters?.trim();
  // The counted sentence when the engine asserted one, the prose summary
  // otherwise, and nothing at all when it asserted neither.
  const pattern = patternSentence(review) ?? learning_pattern_summary?.trim() ?? null;

  return (
    <div className="flex flex-col gap-3">
      <Card tone="error" icon={AlertTriangle} title="First error">
        {replay.first_error.summary}
      </Card>

      {/* Why the mistake IS a mistake — a different sentence from the one above,
          and the backend's to author. Hidden rather than guessed at. */}
      {whyItMatters && (
        <Card tone="info" icon={Info} title="Why it matters">
          {whyItMatters}
        </Card>
      )}

      {pattern && (
        <Card tone="warn" icon={RefreshCw} title="Repeated pattern">
          {pattern}
        </Card>
      )}

      <Card tone="focus" icon={Target} title="Next practice focus">
        {next_practice_focus}
      </Card>

      {/* The way on from this replay, and nothing else.
          `next_action_message` used to be printed here above the button. It
          belongs to `topic_outcome`, beside `mastery_status` — all three are
          statements about the TOPIC, not about one replay — so a rail that
          only renders when a replay exists was the one place a topic-level
          sentence could not always be said. It is on the Learning Summary now
          (Chirudeva, 11 Sep 2026: "move it, and the payload already argues for
          it").
          Unconditional, too. It used to be gated on that same sentence being
          non-empty, which made the only forward control out of a replay
          dependent on a field the engine may legitimately omit. */}
      <Card tone="go" icon={Flag} title="Next action">
        <button
          onClick={onContinue}
          className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg
                     bg-focus-navy px-3 py-2.5 text-[12.5px] font-semibold text-white
                     hover:opacity-85 transition-opacity"
        >
          {continueLabel}
          <ArrowRight size={14} strokeWidth={2.2} aria-hidden />
        </button>
      </Card>
    </div>
  );
}

'use client';

import { useState } from 'react';
import { ChevronDown, Check, X, Minus, Lightbulb } from 'lucide-react';
import clsx from 'clsx';
import Shell from '@/components/Shell';
import { Card, PageHeader, Pill, Empty, dateLabel } from '@/components/ui';
import { sessionsIn, outcomes, formatDuration, phaseLabel, snapshot } from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import type { ChildData, Evaluation, Session } from '@/lib/types';

export default function ActivityPage() {
  return <Shell>{(d) => <Activity d={d} />}</Shell>;
}

function Activity({ d }: { d: ChildData }) {
  const { range } = useChild();
  const first = d.child.name.split(' ')[0];
  const sessions = sessionsIn(d, range).slice().reverse();
  const snap = snapshot(sessions);
  const topicTitle = (id: string) => d.topics.find((t) => t.topic_id === id)?.title ?? id;

  return (
    <>
      <PageHeader
        title="Activity"
        subtitle={`Every session ${first} has had in the last ${range.days} days. Open one to see each question.`}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Mini label="Sessions" value={String(snap.sessions)} />
        <Mini label="Time on maths" value={formatDuration(snap.minutes * 60)} />
        <Mini label="Questions" value={String(snap.questions)} />
        <Mini label="Correct" value={String(snap.correct)} />
      </div>
      <Card>
        {sessions.length ? (
          <ul className="flex flex-col divide-y divide-line">
            {sessions.map((s) => <SessionRow key={s.session_id} s={s} topic={topicTitle(s.topic_id)} />)}
          </ul>
        ) : (
          <Empty title="No sessions in this period" body="Choose a longer date range at the top to see earlier sessions." />
        )}
      </Card>
    </>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-line bg-card px-4 py-3">
      <span className="block text-[12px] text-ink-soft">{label}</span>
      <span className="mt-0.5 block text-[20px] font-extrabold text-ink">{value}</span>
    </div>
  );
}

const EVAL: Record<Evaluation, { icon: typeof Check; label: string; cls: string }> = {
  CORRECT: { icon: Check, label: 'Correct', cls: 'bg-teal-soft text-teal-deep' },
  PARTIALLY_CORRECT: { icon: Minus, label: 'Partly correct', cls: 'bg-mustard-soft text-ink' },
  INCORRECT: { icon: X, label: 'Not yet', cls: 'bg-coral-soft text-[#B5334F]' },
};

function SessionRow({ s, topic }: { s: Session; topic: string }) {
  const [open, setOpen] = useState(false);
  const o = outcomes(s.attempts);
  return (
    <li>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 py-3.5 text-left"
      >
        <span className="w-[120px] text-[13px] font-extrabold text-ink">
          {dateLabel(s.session_date, { weekday: 'short', day: 'numeric', month: 'short' })}
          <span className="block text-[11.5px] font-normal text-ink-soft">
            {new Date(s.session_date).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </span>
        <span className="min-w-[180px] flex-1 text-[13px] text-ink">{topic}</span>
        <span className="text-[12.5px] text-ink-soft">{formatDuration(s.session_duration_seconds)}</span>
        <span className="w-[100px] text-[12.5px] text-ink-soft">{o.total} questions</span>
        <Pill tone={o.score >= 75 ? 'good' : o.score >= 50 ? 'warn' : 'bad'}>{o.score}%</Pill>
        <ChevronDown size={16} className={clsx('text-ink-soft transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <ol className="mb-3 flex flex-col gap-1.5 rounded-[18px] bg-cream-deep p-3">
          {s.attempts.map((a, i) => {
            const e = EVAL[a.evaluation];
            return (
              <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-card px-3 py-2 text-[12.5px]">
                <span className={clsx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-extrabold', e.cls)}>
                  <e.icon size={12} strokeWidth={3} aria-hidden /> {e.label}
                </span>
                <span className="min-w-[160px] flex-1 font-mono text-ink">{a.question_text}</span>
                <span className="text-ink-soft">{phaseLabel(a.phase)}</span>
                {a.hint_level_used > 0 && (
                  <span className="inline-flex items-center gap-1 text-ink-soft"><Lightbulb size={12} aria-hidden /> Hint {a.hint_level_used}</span>
                )}
                <span className="w-[54px] text-right text-ink-soft">{formatDuration(a.time_taken_seconds)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </li>
  );
}

'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { ArrowLeft, Check } from 'lucide-react';
import clsx from 'clsx';
import Shell from '@/components/Shell';
import { MASTERY_TONE, SKILL_TONE, PhaseDots } from '@/components/topic';
import { Card, PageHeader, Pill, ProgressBar, Empty, topicArt, dateLabel } from '@/components/ui';
import {
  MASTERY_LABEL, PHASES, phaseLabel, topicPercent, SKILL_LABEL, outcomes, misconceptionCounts, formatDuration,
} from '@/lib/derive';
import type { ChildData, TopicProgress } from '@/lib/types';

export default function TopicsPage() {
  return (
    <Shell>
      {(d) => (
        <Suspense>
          <Topics d={d} />
        </Suspense>
      )}
    </Shell>
  );
}

function Topics({ d }: { d: ChildData }) {
  const id = useSearchParams().get('id');
  const topic = id ? d.topics.find((t) => t.topic_id === id) : null;
  if (id && topic) return <TopicDetail d={d} t={topic} />;

  const first = d.child.name.split(' ')[0];
  return (
    <>
      <PageHeader title="Topics" subtitle={`Every topic in ${first}'s plan, and how far through each one they are.`} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {d.topics.map((t) => (
          <Link
            key={t.topic_id}
            href={`/topics?id=${encodeURIComponent(t.topic_id)}`}
            className="group flex flex-col overflow-hidden rounded-card border border-line bg-card transition-shadow hover:shadow-lg"
          >
            <div className="flex h-36 items-center justify-center bg-cream-deep">
              {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
              <img src={topicArt(t)} alt="" aria-hidden className="h-28 w-28 object-contain transition-transform group-hover:scale-105" />
            </div>
            <div className="flex flex-1 flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-[15px] font-extrabold leading-snug text-ink">{t.title}</h2>
                <Pill tone={MASTERY_TONE[t.mastery_status]}>{MASTERY_LABEL[t.mastery_status]}</Pill>
              </div>
              <p className="mt-1 text-[12px] text-ink-soft">
                {t.mastery_status === 'IN_PROGRESS' ? `Now: ${phaseLabel(t.current_phase)}` : t.mastery_status === 'MASTERED' ? 'All five stages done' : 'Not started yet'}
              </p>
              <PhaseDots t={t} />
              <div className="mt-auto pt-4">
                <div className="mb-1.5 flex justify-between text-[11.5px] text-ink-soft">
                  <span>{t.micro_skills.filter((s) => s.status === 'INDEPENDENTLY_VERIFIED').length} of {t.micro_skills.length} skills strong</span>
                  <span>{topicPercent(t)}%</span>
                </div>
                <ProgressBar value={topicPercent(t)} tone={t.mastery_status === 'MASTERED' ? 'teal' : 'mustard'} />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}

function TopicDetail({ d, t }: { d: ChildData; t: TopicProgress }) {
  const sessions = d.sessions.filter((s) => s.topic_id === t.topic_id).slice().reverse();
  const attempts = sessions.flatMap((s) => s.attempts);
  const o = outcomes(attempts);
  const mcs = misconceptionCounts(d, attempts);
  return (
    <>
      <Link href="/topics" className="mb-4 inline-flex items-center gap-1.5 text-[13px] font-extrabold text-ink-soft hover:text-ink">
        <ArrowLeft size={15} aria-hidden /> All topics
      </Link>
      <div className="mb-6 flex flex-wrap items-center gap-5">
        <div className="flex h-24 w-24 items-center justify-center rounded-card bg-cream-deep">
          {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
          <img src={topicArt(t)} alt="" aria-hidden className="h-20 w-20 object-contain" />
        </div>
        <div>
          <h1 className="text-[26px] font-extrabold tracking-[-0.02em] text-ink">{t.title}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px] text-ink-soft">
            <Pill tone={MASTERY_TONE[t.mastery_status]}>{MASTERY_LABEL[t.mastery_status]}</Pill>
            {t.started_at && <span>Started {dateLabel(t.started_at, { day: 'numeric', month: 'long' })}</span>}
            {t.last_activity_at && <span>· Last practised {dateLabel(t.last_activity_at, { day: 'numeric', month: 'long' })}</span>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Stages" subtitle="Every topic goes through the same five stages" className="lg:col-span-2">
          <ol className="grid gap-2 sm:grid-cols-5">
            {PHASES.map((p, i) => {
              const done = t.mastery_status === 'MASTERED' || t.phases_completed.includes(p.id);
              const now = t.current_phase === p.id;
              return (
                <li key={p.id} className={clsx('rounded-[18px] border p-3', now ? 'border-teal bg-teal-soft/50' : 'border-line')}>
                  <span className={clsx('flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-extrabold',
                    done ? 'bg-correct text-white' : now ? 'bg-teal text-white' : 'bg-cream-deep text-ink-soft')}>
                    {done ? <Check size={14} strokeWidth={3} aria-label="Done" /> : i + 1}
                  </span>
                  <span className="mt-2 block text-[13px] font-extrabold text-ink">{p.label}</span>
                  <span className="mt-0.5 block text-[11.5px] leading-snug text-ink-soft">{p.parent}</span>
                </li>
              );
            })}
          </ol>
          {t.recommended_next_action && (
            <p className="mt-4 rounded-[18px] bg-cream-deep px-3 py-2.5 text-[12.5px] text-ink"><b>Next:</b> {t.recommended_next_action}</p>
          )}
        </Card>

        <Card title="Results in this topic">
          {o.total ? (
            <dl className="grid grid-cols-2 gap-3 text-[12.5px]">
              <Fact k="Score" v={`${o.score}%`} />
              <Fact k="Questions" v={String(o.total)} />
              <Fact k="Sessions" v={String(sessions.length)} />
              <Fact k="Time spent" v={formatDuration(sessions.reduce((s, x) => s + x.session_duration_seconds, 0))} />
            </dl>
          ) : <Empty title="Not started" body="Results appear after the first session on this topic." />}
        </Card>

        <Card title="Skills in this topic" className="lg:col-span-2">
          <ul className="flex flex-col divide-y divide-line">
            {t.micro_skills.map((s) => (
              <li key={s.id} className="flex items-start justify-between gap-3 py-2.5">
                <span>
                  <span className="block text-[13px] font-extrabold text-ink">{s.label}</span>
                  <span className="mt-0.5 block text-[12px] text-ink-soft">{s.description}</span>
                </span>
                <Pill tone={SKILL_TONE[s.status]}>{SKILL_LABEL[s.status]}</Pill>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Mistakes in this topic" subtitle="Across every session on it">
          {mcs.length ? (
            <ul className="flex flex-col gap-2.5">
              {mcs.map(({ misconception: m, count }) => (
                <li key={m.id} className="flex items-start justify-between gap-3 text-[12.5px]">
                  <span className="text-ink">{m.label}</span>
                  <span className="font-extrabold text-[#B5334F]">{count}×</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-[12.5px] text-ink-soft">No repeated mistakes.</p>}
        </Card>
      </div>
    </>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-[18px] bg-cream-deep px-3 py-2.5">
      <dt className="text-ink-soft">{k}</dt>
      <dd className="mt-0.5 text-[18px] font-extrabold text-ink">{v}</dd>
    </div>
  );
}

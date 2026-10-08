'use client';

import Shell from '@/components/Shell';
import { Card, PageHeader, Pill, StepRow, PillButton, topicArt, dateLabel } from '@/components/ui';
import { MASTERY_TONE } from '@/components/topic';
import { PHASES, MASTERY_LABEL } from '@/lib/derive';
import type { ChildData } from '@/lib/types';
import { ArrowRight } from 'lucide-react';

export default function JourneyPage() {
  return <Shell>{(d) => <Journey d={d} />}</Shell>;
}

function Journey({ d }: { d: ChildData }) {
  const first = d.child.name.split(' ')[0];
  return (
    <>
      <PageHeader title="Learning journey" subtitle={`Every topic goes through the same five stages. Here is where ${first} is in each.`} />
      <div className="grid gap-4 xl:grid-cols-2">
        {d.topics.map((t) => (
          <Card key={t.topic_id} notch>
            <div className="mb-4 flex items-center gap-4">
              <span className="flex h-16 w-16 flex-shrink-0 items-center justify-center rounded-[20px] bg-cream-deep">
                {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
                <img src={topicArt(t)} alt="" aria-hidden className="h-12 w-12 object-contain" />
              </span>
              <div className="min-w-0 flex-1">
                <h2 className="text-[19px] font-black leading-tight text-ink">{t.title}</h2>
                <p className="mt-0.5 text-[12.5px] font-bold text-ink-soft">
                  {t.started_at ? `Started ${dateLabel(t.started_at, { day: 'numeric', month: 'long' })}` : 'Not started yet'}
                </p>
              </div>
              <Pill tone={MASTERY_TONE[t.mastery_status]}>{MASTERY_LABEL[t.mastery_status]}</Pill>
            </div>
            <div className="flex flex-col gap-2">
              {PHASES.map((p, i) => {
                const done = t.mastery_status === 'MASTERED' || t.phases_completed.includes(p.id);
                const now = t.current_phase === p.id;
                return (
                  <StepRow
                    key={p.id}
                    n={i + 1}
                    title={p.label}
                    body={now ? `Here now · ${p.parent}` : p.parent}
                    state={done ? 'done' : now ? 'now' : 'todo'}
                    tint="mustard"
                  />
                );
              })}
            </div>
            <PillButton href={`/topics?id=${encodeURIComponent(t.topic_id)}`} tone="light" className="mt-4 w-full !bg-cream-deep" icon={<ArrowRight size={14} strokeWidth={2.6} />}>
              Topic details
            </PillButton>
          </Card>
        ))}
      </div>
    </>
  );
}

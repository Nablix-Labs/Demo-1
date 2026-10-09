'use client';

import { Compass, Heart, MessageCircle, Clock, PartyPopper, Ban, ArrowRight } from 'lucide-react';
import Shell from '@/components/Shell';
import { Card, Hero, Wave, PageHeader, StepRow, IconTile, PillButton, art, type Tint } from '@/components/ui';
import { nextSteps } from '@/lib/derive';
import type { ChildData } from '@/lib/types';

export default function NextStepsPage() {
  return <Shell>{(d) => <NextSteps d={d} />}</Shell>;
}

const TIPS: { icon: typeof Heart; tint: Tint; title: string; body: string }[] = [
  { icon: MessageCircle, tint: 'teal', title: 'Ask them to teach you', body: 'Ask “how did you work that out?” Explaining a method out loud is one of the best ways to remember it.' },
  { icon: Clock, tint: 'mustard', title: 'Short and often', body: 'Fifteen minutes on most days beats one long session a week.' },
  { icon: Heart, tint: 'coral', title: 'Praise the effort', body: 'Say “you kept going” rather than “you’re clever”. It makes trying again after a mistake feel normal.' },
  { icon: PartyPopper, tint: 'mint', title: 'Notice the wins', body: 'When a topic is mastered, mention it. Small celebrations build confidence.' },
  { icon: Ban, tint: 'info', title: 'Don’t give the answer', body: 'If they are stuck, ask what the question is asking first. The tutor’s hints do the rest.' },
];

function NextSteps({ d }: { d: ChildData }) {
  const first = d.child.name.split(' ')[0];
  const steps = nextSteps(d);
  return (
    <>
      <PageHeader title="Next steps" subtitle={`What ${first} is working on next, and how you can help at home.`} />
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="flex flex-col gap-4 lg:col-span-3">
          <Hero color="bg-coral" className="min-h-[170px] pb-14">
            <Wave className="bottom-0 h-14" color="#3D8C79" />
            {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
            <img src={art('axo-books')} alt="" aria-hidden className="pointer-events-none absolute -bottom-1 right-3 hidden h-[150px] w-auto sm:block" />
            <h2 className="relative max-w-sm text-[24px] font-black leading-tight">You don&apos;t need to set anything up.</h2>
            <p className="relative mt-1.5 max-w-sm text-[13.5px] font-bold text-white/85">
              The tutor picks {first}&apos;s next question from how the last ones went.
            </p>
          </Hero>
          <Card title="Coming up" subtitle="Recommended by the tutor" icon={<Compass size={18} strokeWidth={2.4} />} iconTint="info">
            <div className="flex flex-col gap-2.5">
              {steps.map((s, i) => (
                <StepRow
                  key={s.title}
                  n={i + 1}
                  title={s.title}
                  body={s.detail}
                  state={i === 0 ? 'now' : 'todo'}
                  tint="mustard"
                  trailing={
                    <PillButton href={`/topics?id=${encodeURIComponent(s.topicId)}`} tone="light" className="!px-3 !py-2 text-[12.5px]" icon={<ArrowRight size={12} strokeWidth={2.8} />}>
                      Topic
                    </PillButton>
                  }
                />
              ))}
            </div>
          </Card>
        </div>

        <Card title="How you can help at home" icon={<Heart size={18} strokeWidth={2.4} />} iconTint="coral" className="lg:col-span-2">
          <ul className="flex flex-col gap-2.5">
            {TIPS.map(({ icon: Icon, tint, title, body }) => (
              <li key={title} className="flex gap-3 rounded-[20px] bg-cream p-3.5">
                <IconTile tint={tint}><Icon size={17} strokeWidth={2.4} aria-hidden /></IconTile>
                <span>
                  <span className="block text-[14.5px] font-extrabold text-ink">{title}</span>
                  <span className="mt-0.5 block text-[12.5px] font-semibold leading-snug text-ink-soft">{body}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}

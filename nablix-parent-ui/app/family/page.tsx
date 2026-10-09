'use client';

import { useRouter } from 'next/navigation';
import { ArrowRight, Clock, Flame, HelpCircle, Trophy, FileText, Heart } from 'lucide-react';
import Shell, { initials } from '@/components/Shell';
import { Card, Hero, Wave, PageHeader, StatTile, PillButton, Delta, topicArt, dateLabel } from '@/components/ui';
import { Sparkline } from '@/components/charts';
import {
  attemptsIn, outcomes, previousRange, sessionsIn, snapshot, streak, weeklyScores, phaseLabel, formatDuration, change,
  type Range,
} from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import { useFamily, type FamilyEntry } from '@/lib/useFamily';
import { childLook } from '@/lib/childColor';
import type { ChildData } from '@/lib/types';

export default function FamilyPage() {
  return <Shell>{() => <Family />}</Shell>;
}

/** The numbers a family card and the comparison table both show. */
function summary(d: ChildData, range: Range) {
  const o = outcomes(attemptsIn(d, range));
  const before = outcomes(attemptsIn(d, previousRange(range)));
  const snap = snapshot(sessionsIn(d, range));
  const now = d.topics.find((t) => t.mastery_status === 'IN_PROGRESS') ?? null;
  return {
    o, before, snap,
    streak: streak(d),
    mastered: d.topics.filter((t) => t.mastery_status === 'MASTERED').length,
    now,
    weeks: weeklyScores(d, 6),
  };
}

function Family() {
  const { range, children } = useChild();
  const family = useFamily();
  const ready = family.filter((e): e is Extract<FamilyEntry, { status: 'ready' }> => e.status === 'ready');

  if (children.length <= 1) {
    return (
      <>
        <PageHeader title="Your family" />
        <Card>
          <p className="text-[15px] font-bold text-ink">Only one child is linked to your account.</p>
          <p className="mt-1 text-[13.5px] font-semibold text-ink-soft">
            When a brother or sister signs up with your email as their parent, they appear here, side by side.
          </p>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Your family"
        subtitle={`How each of your ${children.length} children is getting on, over the last ${range.days} days.`}
        action={<PillButton href="/reports?who=family" icon={<FileText size={14} strokeWidth={2.6} />}>Family report</PillButton>}
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {family.map((entry, i) => <ChildCard key={entry.code} entry={entry} index={i} range={range} />)}
      </div>

      {ready.length > 1 && (
        <Card title="Side by side" subtitle={`Last ${range.days} days`} className="mt-4">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[14px]">
              <thead>
                <tr>
                  <th className="pb-3 text-[12px] font-extrabold uppercase tracking-[0.06em] text-ink-soft" />
                  {ready.map((e) => {
                    const i = family.indexOf(e);
                    return (
                      <th key={e.code} className="pb-3 pr-4">
                        <span className="flex items-center gap-2.5">
                          <span className={`flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-black ${childLook(i).avatar}`}>{initials(e.data.child.name, children.map((k) => k.name))}</span>
                          <span>
                            <span className="block text-[14px] font-extrabold text-ink">{e.data.child.name.split(' ')[0]}</span>
                            <span className="block text-[11.5px] font-bold text-ink-soft">{e.data.child.year_group}</span>
                          </span>
                        </span>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {([
                  ['Score', (s) => (s.o.total ? `${s.o.score}%` : '—')],
                  ['Questions answered', (s) => String(s.o.total)],
                  ['Time on maths', (s) => formatDuration(s.snap.minutes * 60)],
                  ['Sessions', (s) => String(s.snap.sessions)],
                  ['Days in a row', (s) => String(s.streak)],
                  ['Topics mastered', (s) => String(s.mastered)],
                  ['Working on', (s) => (s.now ? s.now.title : 'Nothing open')],
                ] as [string, (s: ReturnType<typeof summary>) => string][]).map(([label, value]) => (
                  <tr key={label} className="border-t border-line">
                    <td className="py-3 pr-4 font-bold text-ink-soft">{label}</td>
                    {ready.map((e) => <td key={e.code} className="tabular py-3 pr-4 font-extrabold text-ink">{value(summary(e.data, range))}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-4 flex items-start gap-2 rounded-[18px] bg-mustard-soft px-4 py-3 text-[13px] font-bold text-ink">
            <Heart size={16} className="mt-0.5 flex-shrink-0" aria-hidden />
            Every child learns at their own pace, and they are in different years. Compare each child with how they did
            before, not with each other.
          </p>
        </Card>
      )}
    </>
  );
}

function ChildCard({ entry, index, range }: { entry: FamilyEntry; index: number; range: Range }) {
  const router = useRouter();
  const { selectChild, children } = useChild();
  const look = childLook(index);

  if (entry.status === 'loading') return <div className="h-[520px] animate-pulse rounded-card bg-card" aria-busy="true" />;
  if (entry.status === 'error') {
    return <Card><p className="text-[15px] font-extrabold text-ink">Couldn&apos;t load this child</p><p className="mt-1 text-[13px] font-semibold text-ink-soft">{entry.message}</p></Card>;
  }

  const d = entry.data;
  const first = d.child.name.split(' ')[0];
  const s = summary(d, range);
  const open = (href: string) => { selectChild(d.child.student_code); router.push(href); };

  return (
    <article className="flex flex-col overflow-hidden rounded-card bg-card">
      <Hero color={look.hero} className="rounded-b-none pb-16">
        <Wave className="bottom-0 h-14" color={look.wave} />
        <div className="relative flex items-center gap-3">
          <span className={`flex h-12 w-12 items-center justify-center rounded-full border-[3px] border-white text-[15px] font-black ${look.avatar}`}>
            {initials(d.child.name, children.map((k) => k.name))}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-[22px] font-black leading-tight">{first}</h2>
            <p className="text-[13px] font-bold text-white/80">{d.child.year_group}</p>
          </div>
          <span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-2.5 py-1 text-[12px] font-extrabold">
            <Flame size={13} strokeWidth={2.6} aria-hidden /> {s.streak} day{s.streak === 1 ? '' : 's'}
          </span>
        </div>
        <div className="relative mt-5 flex items-end gap-3">
          <span className="tabular text-[52px] font-black leading-none tracking-[-0.03em]">{s.o.total ? `${s.o.score}%` : '—'}</span>
          <span className="pb-1.5 text-[13px] font-bold text-white/85">score</span>
        </div>
        {s.o.total > 0 && s.before.total > 0 && (
          <div className="relative mt-2"><Delta value={change(s.o.score, s.before.score)} unit=" pts" onDark /></div>
        )}
      </Hero>

      <div className="flex flex-1 flex-col gap-3 p-5 pt-4">
        <div className="grid grid-cols-3 gap-2">
          <StatTile tint="mint" icon={<HelpCircle size={14} strokeWidth={2.6} />} value={s.o.total} label="Questions" className="!py-3 [&>span:nth-child(2)]:text-[22px]" />
          <StatTile tint="mustard" icon={<Clock size={14} strokeWidth={2.6} />} value={s.snap.minutes} label="Minutes" className="!py-3 [&>span:nth-child(2)]:text-[22px]" />
          <StatTile dashed icon={<Trophy size={14} strokeWidth={2.6} />} value={s.mastered} label="Mastered" className="!py-3 [&>span:nth-child(2)]:text-[22px]" />
        </div>

        <div className="flex items-center gap-3 rounded-[18px] bg-cream p-3">
          {s.now ? (
            <>
              <span className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-[14px] bg-cream-deep">
                {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
                <img src={topicArt(s.now)} alt="" aria-hidden className="h-9 w-9 object-contain" />
              </span>
              <span className="min-w-0">
                <span className="block text-[11.5px] font-extrabold uppercase tracking-[0.06em] text-ink-soft">Working on now</span>
                <span className="block truncate text-[14px] font-extrabold text-ink">{s.now.title}</span>
                <span className="block text-[12px] font-bold text-ink-soft">{phaseLabel(s.now.current_phase)}</span>
              </span>
            </>
          ) : <span className="text-[13px] font-bold text-ink-soft">No topic open right now.</span>}
        </div>

        <div className="flex items-center justify-between gap-3 px-1">
          <span>
            <span className="block text-[12px] font-extrabold text-ink">Weekly score</span>
            <span className="block text-[11.5px] font-bold text-ink-soft">Last 6 weeks</span>
          </span>
          <Sparkline values={s.weeks.map((w) => w.score)} labels={s.weeks.map((w) => `Week to ${dateLabel(w.weekEnding)}`)} />
        </div>

        <div className="mt-auto grid grid-cols-2 gap-2 pt-1">
          <PillButton onClick={() => open('/')} className="!px-3 text-[13px]" icon={<ArrowRight size={13} strokeWidth={2.8} />}>Dashboard</PillButton>
          <PillButton onClick={() => open('/reports')} tone="light" className="!bg-cream-deep !px-3 text-[13px]" icon={<FileText size={13} strokeWidth={2.6} />}>Report</PillButton>
        </div>
      </div>
    </article>
  );
}

'use client';

import {
  Clock, BookOpen, HelpCircle, CheckCircle2, Lightbulb, Layers, LifeBuoy, Trophy, TrendingUp, Eye,
  MessageSquareText, UserRound, Flame, ArrowRight, Target, Compass,
} from 'lucide-react';
import Shell from '@/components/Shell';
import {
  Card, Hero, Wave, StatTile, StepRow, RankRow, Bubble, Pill, PillButton, SectionTitle, Delta, Empty, art,
} from '@/components/ui';
import { Donut, Columns, ScoreLine } from '@/components/charts';
import {
  attemptsIn, outcomes, previousRange, questionsPerDay, avgSecondsPerQuestion, formatDuration,
  weeklyScores, strengths, developing, SKILL_LABEL, misconceptionCounts, learnsBest, snapshot, sessionsIn,
  streak, thisWeek, nextSteps, change,
} from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import type { ChildData } from '@/lib/types';

export default function OverviewPage() {
  return <Shell>{(d) => <Overview d={d} />}</Shell>;
}

const HINT_NAME = ['None', 'Level 1', 'Level 2', 'Level 3'];
const RANK_FILL = ['bg-mustard', 'bg-coral-soft', 'bg-teal-soft'];

function Overview({ d }: { d: ChildData }) {
  const { range } = useChild();
  const first = d.child.name.split(' ')[0];
  const now = attemptsIn(d, range);
  const before = attemptsIn(d, previousRange(range));
  const o = outcomes(now);
  const ob = outcomes(before);
  const perQ = avgSecondsPerQuestion(now);
  const perQBefore = avgSecondsPerQuestion(before);
  const weeks = weeklyScores(d, 6);
  const scored = weeks.filter((w) => w.score !== null);
  const gain = scored.length > 1 ? scored[scored.length - 1].score! - scored[0].score! : 0;
  const strong = strengths(d);
  const dev = developing(d);
  const mcs = misconceptionCounts(d, now).slice(0, 3);
  const lb = learnsBest(now);
  const snap = snapshot(sessionsIn(d, range));
  const inProgress = d.topics.filter((t) => t.mastery_status === 'IN_PROGRESS').length;
  const mastered = d.topics.filter((t) => t.mastery_status === 'MASTERED').length;
  const steps = nextSteps(d).slice(0, 3);
  const days = streak(d);
  const week = thisWeek(d);
  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <>
      <div className="mb-5 px-1">
        <h1 className="text-[32px] font-black leading-[1.05] tracking-[-0.025em] text-ink">Hi there</h1>
        <p className="mt-1 text-[14px] font-bold text-ink-soft">{today}</p>
      </div>

      {/* ── Hero + streak ── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Hero className="min-h-[300px] pb-24 lg:col-span-2">
          <Wave className="bottom-0 h-24" color="#F4B63F" />
          {/* eslint-disable-next-line @next/next/no-img-element -- static export */}
          <img src={art('axo-wave')} alt="" aria-hidden className="pointer-events-none absolute -bottom-2 right-4 hidden h-[230px] w-auto sm:block" />
          <div className="relative flex items-start justify-between gap-3">
            <div className="max-w-md">
              <h2 className="text-[28px] font-black leading-tight tracking-[-0.02em]">How {first} is doing</h2>
              <p className="mt-1.5 text-[14px] font-bold text-white/80">Last {range.days} days of maths on Numera.</p>
            </div>
            <span className="rounded-full bg-white/20 px-3 py-1 text-[12px] font-extrabold">{d.child.year_group}</span>
          </div>
          {o.total ? (
            <div className="relative mt-6 flex flex-wrap items-center gap-6">
              <div className="rounded-full bg-card p-2.5">
                <Donut
                  center={`${o.score}%`}
                  sub="score"
                  slices={[
                    { label: 'Correct', value: o.correct, color: '#1F9A78' },
                    { label: 'Partly correct', value: o.partial, color: '#E3A41E' },
                    { label: 'Not yet', value: o.incorrect, color: '#E65A78' },
                  ]}
                />
              </div>
              <ul className="flex flex-col gap-2 text-[13px] font-bold">
                <Legend dot="bg-correct" pct={o.correctPct} label="Correct" />
                <Legend dot="bg-partial" pct={o.partialPct} label="Partly correct" />
                <Legend dot="bg-incorrect" pct={o.incorrectPct} label="Not yet" />
                {ob.total > 0 && <li className="mt-1"><Delta value={change(o.score, ob.score)} unit=" pts" onDark /></li>}
              </ul>
            </div>
          ) : (
            <p className="relative mt-8 text-[15px] font-bold">No questions answered in this period yet.</p>
          )}
        </Hero>

        <Card title="Learning streak" icon={<Flame size={18} strokeWidth={2.4} />} iconTint="coral" fill="bg-card">
          <div className="flex items-baseline gap-2">
            <span className="tabular text-[56px] font-black leading-none tracking-[-0.03em] text-ink">{days}</span>
            <span className="text-[15px] font-extrabold text-ink-soft">day{days === 1 ? '' : 's'} in a row</span>
          </div>
          <div className="mt-5 grid grid-cols-7 gap-1.5" aria-label="This week">
            {week.map((w, i) => (
              <span key={i} className="flex flex-col items-center gap-1.5">
                <span
                  title={w.done ? 'Practised' : w.done === false ? 'No session' : 'Still to come'}
                  className={
                    'flex h-10 w-full items-center justify-center rounded-full text-[12px] font-black ' +
                    (w.done ? 'bg-teal text-white' : w.done === false ? 'border-[1.5px] border-dashed border-ink/30 text-ink-soft' : 'bg-cream-deep text-ink-soft')
                  }
                >
                  {w.label}
                </span>
              </span>
            ))}
          </div>
          <p className="mt-5 rounded-[18px] bg-mustard-soft px-4 py-3 text-[13px] font-bold text-ink">
            A little every day builds confidence fastest.
          </p>
        </Card>
      </div>

      {/* ── Stat tiles ── */}
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile tint="mint" icon={<HelpCircle size={16} strokeWidth={2.6} />} value={o.total} label={`Questions in ${range.days} days`} />
        <StatTile tint="mustard" icon={<Clock size={16} strokeWidth={2.6} />} value={perQ ? formatDuration(perQ) : '—'} label="Per question" />
        <StatTile tint="coral" icon={<BookOpen size={16} strokeWidth={2.6} />} value={inProgress} label="Topics in progress" />
        <StatTile dashed icon={<Trophy size={16} strokeWidth={2.6} />} value={mastered} label="Topics mastered" />
      </div>
      {perQ > 0 && perQBefore > 0 && (
        <p className="mt-2 px-1 text-[12.5px] font-bold text-ink-soft">
          Time per question <Delta value={change(perQ, perQBefore)} unit="s" goodWhenUp={false} />
        </p>
      )}

      {/* ── Charts ── */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Questions answered" subtitle="Per day" icon={<HelpCircle size={18} strokeWidth={2.4} />} iconTint="mint">
          <Columns data={questionsPerDay(d, range)} height={150} />
        </Card>
        <Card title="Score over time" subtitle="Weekly, last 6 weeks" icon={<TrendingUp size={18} strokeWidth={2.4} />}>
          <ScoreLine data={weeks} height={150} />
          {scored.length > 1 && (
            <p className="mt-3 rounded-[18px] bg-teal-soft px-4 py-3 text-[13px] font-bold text-ink">
              {gain > 0
                ? <>Great progress! {first}&apos;s weekly score is up {gain} points over six weeks.</>
                : gain < 0
                  ? <>{first}&apos;s weekly score is down {-gain} points. Harder topics often cause a dip at first.</>
                  : <>{first}&apos;s weekly score has held steady over six weeks.</>}
            </p>
          )}
        </Card>
      </div>

      {/* ── Strengths / developing / learns best ── */}
      <SectionTitle trailing={`${strong.length} strong · ${dev.length} developing`}>Skills</SectionTitle>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Strengths" subtitle={`What ${first} does really well`} icon={<Trophy size={18} strokeWidth={2.4} />}>
          {strong.length ? (
            <div className="flex flex-col gap-2">
              {strong.slice(0, 3).map(({ skill, topic }) => (
                <SkillRow key={skill.id} title={skill.label} body={topic.title} pill={<Pill tone="good">{SKILL_LABEL[skill.status]}</Pill>} fill="bg-teal-soft/60" />
              ))}
            </div>
          ) : <Empty title="Nothing yet" body="Strengths appear once a skill is solved without help." />}
        </Card>

        <Card title="Still developing" subtitle="Needs more practice" icon={<Target size={18} strokeWidth={2.4} />} iconTint="coral">
          {dev.length ? (
            <div className="flex flex-col gap-2">
              {dev.slice(0, 3).map(({ skill, topic }) => (
                <SkillRow
                  key={skill.id}
                  title={skill.label}
                  body={topic.title}
                  fill={skill.status === 'RESCUE_REQUIRED' ? 'bg-coral-soft/60' : 'bg-mustard-soft/60'}
                  pill={<Pill tone={skill.status === 'RESCUE_REQUIRED' ? 'bad' : 'warn'}>{SKILL_LABEL[skill.status]}</Pill>}
                />
              ))}
            </div>
          ) : <Empty title="All caught up" body="No skill needs extra practice right now." />}
        </Card>

        <Card title={`How ${first} learns best`} subtitle="From the help used and the results" icon={<Lightbulb size={18} strokeWidth={2.4} />} iconTint="mustard">
          <div className="grid grid-cols-3 gap-2">
            <StatTile tint="mint" icon={<Eye size={15} strokeWidth={2.6} />} value={`${lb.visualRate}%`} label="With pictures" className="!py-3 [&>span:nth-child(2)]:text-[22px]" />
            <StatTile tint="mustard" icon={<MessageSquareText size={15} strokeWidth={2.6} />} value={HINT_NAME[lb.commonHintLevel]} label="Usual hint" className="!py-3 [&>span:nth-child(2)]:text-[18px]" />
            <StatTile tint="teal" icon={<UserRound size={15} strokeWidth={2.6} />} value={`${lb.independentPct}%`} label="On their own" className="!py-3 [&>span:nth-child(2)]:text-[22px]" />
          </div>
          <p className="mt-3 text-[13px] font-semibold leading-relaxed text-ink-soft">
            {lb.visualRate > lb.plainRate
              ? <>{first} gets <b className="text-ink">{lb.visualRate}%</b> right when the tutor shows a picture, against {lb.plainRate}% without.</>
              : <>Pictures make no clear difference for {first} yet.</>}{' '}
            {lb.commonHintLevel <= 1 ? 'A gentle first hint is usually enough.' : 'Fuller hints still help most.'}
          </p>
        </Card>
      </div>

      {/* ── Mistakes + next ── */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Common mistakes" subtitle="Patterns the tutor is working on" icon={<Target size={18} strokeWidth={2.4} />} iconTint="coral">
          {mcs.length ? (
            <div className="flex flex-col gap-2.5">
              {mcs.map(({ misconception: m, count }, i) => (
                <RankRow
                  key={m.id}
                  rank={`#${i + 1}`}
                  title={m.label}
                  body={m.description}
                  fill={RANK_FILL[i]}
                  trailing={<Bubble dark={i === 0}><span className="text-[15px] font-black">{count}</span><span className="text-[9px] font-bold opacity-70">times</span></Bubble>}
                />
              ))}
            </div>
          ) : <Empty title="No repeated mistakes" body="Nothing came up more than once in this period." />}
          <PillButton href="/skills" tone="light" className="mt-4 w-full !bg-cream-deep" icon={<ArrowRight size={14} strokeWidth={2.6} />}>See all mistakes</PillButton>
        </Card>

        <Card title="What's next" subtitle="Recommended by the tutor" icon={<Compass size={18} strokeWidth={2.4} />} iconTint="info">
          <div className="flex flex-col gap-2.5">
            {steps.map((s, i) => (
              <StepRow key={s.title} n={i + 1} title={s.title} body={s.detail} state={i === 0 ? 'now' : 'todo'} tint="mustard" />
            ))}
          </div>
          <PillButton href="/next-steps" className="mt-4 w-full" icon={<ArrowRight size={14} strokeWidth={2.6} />}>How you can help at home</PillButton>
        </Card>
      </div>

      {/* ── Activity ── */}
      <SectionTitle trailing={`${snap.sessions} sessions · ${snap.minutes} min`}>Activity</SectionTitle>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <StatTile tint="mint" icon={<BookOpen size={16} strokeWidth={2.6} />} value={snap.topicsStudied} label="Topics studied" />
        <StatTile tint="teal" icon={<CheckCircle2 size={16} strokeWidth={2.6} />} value={snap.correct} label="Correct" />
        <StatTile tint="mustard" icon={<Lightbulb size={16} strokeWidth={2.6} />} value={snap.hints} label="Hints used" />
        <StatTile tint="info" icon={<Layers size={16} strokeWidth={2.6} />} value={snap.scaffolds} label="Step-by-step help" />
        <StatTile tint="coral" icon={<LifeBuoy size={16} strokeWidth={2.6} />} value={snap.interventions} label="Tutor stepped in" />
        <StatTile dashed icon={<Clock size={16} strokeWidth={2.6} />} value={snap.minutes} label="Minutes" />
      </div>
      <div className="mt-4 flex justify-end">
        <PillButton href="/activity" icon={<ArrowRight size={14} strokeWidth={2.6} />}>See every session</PillButton>
      </div>
    </>
  );
}

function Legend({ dot, pct, label }: { dot: string; pct: number; label: string }) {
  return (
    <li className="flex items-center gap-2.5">
      <span className={`h-3 w-3 rounded-full border-2 border-white ${dot}`} aria-hidden />
      <span className="tabular w-10 text-[17px] font-black">{pct}%</span>
      <span className="text-white/85">{label}</span>
    </li>
  );
}

function SkillRow({ title, body, pill, fill }: { title: string; body: string; pill: React.ReactNode; fill: string }) {
  return (
    <div className={`flex items-center justify-between gap-3 rounded-[18px] px-4 py-3 ${fill}`}>
      <span className="min-w-0">
        <span className="block text-[14px] font-extrabold leading-tight text-ink">{title}</span>
        <span className="mt-0.5 block text-[12px] font-semibold text-ink-soft">{body}</span>
      </span>
      {pill}
    </div>
  );
}


'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Printer, Users } from 'lucide-react';
import clsx from 'clsx';
import Shell, { Logo, initials } from '@/components/Shell';
import { useFamily, type FamilyEntry } from '@/lib/useFamily';
import { childLook } from '@/lib/childColor';
import { PageHeader, dateLabel } from '@/components/ui';
import {
  attemptsIn, outcomes, sessionsIn, snapshot, strengths, developing, misconceptionCounts, nextSteps,
  MASTERY_LABEL, phaseLabel, formatDuration, avgSecondsPerQuestion, SKILL_LABEL,
} from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import type { ChildData } from '@/lib/types';

export default function ReportsPage() {
  return (
    <Shell>
      {(d) => (
        <Suspense>
          <Reports d={d} />
        </Suspense>
      )}
    </Shell>
  );
}

/**
 * One child's report, or every child's one after another ("Whole family"),
 * each on its own printed page. "Download" is the browser's Save as PDF, which
 * keeps the report exactly as shown and needs no server.
 */
function Reports({ d }: { d: ChildData }) {
  const { range, children, selectChild } = useChild();
  const params = useSearchParams();
  const router = useRouter();
  const [who, setWho] = useState<'child' | 'family'>(params.get('who') === 'family' ? 'family' : 'child');
  const family = useFamily();
  const many = children.length > 1;
  const showFamily = many && who === 'family';
  const ready = family.filter((e): e is Extract<FamilyEntry, { status: 'ready' }> => e.status === 'ready');

  const pick = (next: 'family' | string) => {
    if (next === 'family') { setWho('family'); router.replace('/reports?who=family'); return; }
    selectChild(next);
    setWho('child');
    router.replace('/reports');
  };

  return (
    <>
      <div className="no-print">
        <PageHeader
          title="Reports"
          subtitle={`A one-page summary of the last ${range.days} days to keep or share.`}
          action={
            <button
              onClick={() => window.print()}
              disabled={showFamily && ready.length < family.length}
              className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-[14px] font-extrabold text-white transition-transform active:scale-[0.97] disabled:opacity-50"
            >
              <Printer size={16} aria-hidden /> Print or save as PDF
            </button>
          }
        />
        {many && (
          <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Whose report">
            {children.map((k, i) => {
              const on = !showFamily && k.student_code === d.child.student_code;
              return (
                <button
                  key={k.student_code}
                  onClick={() => pick(k.student_code)}
                  aria-pressed={on}
                  className={clsx(
                    'flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4 text-[14px] font-extrabold transition-colors',
                    on ? 'bg-ink text-white' : 'bg-card text-ink hover:bg-white',
                  )}
                >
                  <span className={clsx('flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-black', childLook(i).avatar)}>{initials(k.name, children.map((x) => x.name))}</span>
                  {k.name.split(' ')[0]}
                </button>
              );
            })}
            <button
              onClick={() => pick('family')}
              aria-pressed={showFamily}
              className={clsx(
                'flex items-center gap-2 rounded-full px-4 py-1.5 text-[14px] font-extrabold transition-colors',
                showFamily ? 'bg-ink text-white' : 'bg-card text-ink hover:bg-white',
              )}
            >
              <Users size={16} aria-hidden /> Whole family
            </button>
          </div>
        )}
      </div>

      {showFamily ? (
        <div className="flex flex-col gap-6">
          {family.map((e) => e.status === 'ready'
            ? <div key={e.code} className="break-after-page"><Report d={e.data} /></div>
            : <div key={e.code} className="mx-auto h-64 w-full max-w-[820px] animate-pulse rounded-card bg-card" />)}
        </div>
      ) : <Report d={d} />}
    </>
  );
}

function Report({ d }: { d: ChildData }) {
  const { range } = useChild();
  const first = d.child.name.split(' ')[0];
  const attempts = attemptsIn(d, range);
  const o = outcomes(attempts);
  const snap = snapshot(sessionsIn(d, range));
  const lastDay = new Date(range.to.getTime() - 86_400_000);

  return (
    <>
      <article className="mx-auto max-w-[820px] rounded-card border border-line bg-card p-8 print:border-0 print:p-0 print:shadow-none">
        <header className="flex items-start justify-between gap-4 border-b border-line pb-5">
          <div>
            <h1 className="text-[22px] font-extrabold text-ink">{d.child.name}: maths progress report</h1>
            <p className="mt-1 text-[13px] text-ink-soft">
              {d.child.year_group} · {dateLabel(range.from, { day: 'numeric', month: 'long' })} to {dateLabel(lastDay, { day: 'numeric', month: 'long', year: 'numeric' })}
            </p>
          </div>
          <Logo />
        </header>

        <Section title="Summary">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Figure k="Score" v={o.total ? `${o.score}%` : '—'} />
            <Figure k="Questions" v={String(o.total)} />
            <Figure k="Sessions" v={String(snap.sessions)} />
            <Figure k="Time on maths" v={formatDuration(snap.minutes * 60)} />
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-ink">
            {o.total
              ? <>{first} answered {o.total} questions: {o.correct} correct, {o.partial} partly correct and {o.incorrect} not yet right.
                On average each question took {formatDuration(avgSecondsPerQuestion(attempts))}.</>
              : <>{first} had no sessions in this period.</>}
          </p>
        </Section>

        <Section title="Topics">
          <table className="w-full text-left text-[13px]">
            <tbody>
              {d.topics.map((t) => (
                <tr key={t.topic_id} className="border-b border-line last:border-0">
                  <td className="py-2 font-extrabold text-ink">{t.title}</td>
                  <td className="py-2 text-ink-soft">{MASTERY_LABEL[t.mastery_status]}</td>
                  <td className="py-2 text-right text-ink-soft">{t.mastery_status === 'IN_PROGRESS' ? phaseLabel(t.current_phase) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <div className="grid gap-6 sm:grid-cols-2">
          <Section title="Strengths">
            <List items={strengths(d).slice(0, 4).map((r) => `${r.skill.label} — ${r.skill.description}`)} empty="None yet." />
          </Section>
          <Section title="Still developing">
            <List items={developing(d).slice(0, 4).map((r) => `${r.skill.label} (${SKILL_LABEL[r.skill.status].toLowerCase()})`)} empty="Nothing flagged." />
          </Section>
        </div>

        <Section title="Mistakes that came up most">
          <List items={misconceptionCounts(d, attempts).slice(0, 3).map((m) => `${m.misconception.label} — ${m.count} time${m.count === 1 ? '' : 's'}`)} empty="No repeated mistakes." />
        </Section>

        <Section title="Next steps">
          <List items={nextSteps(d).slice(0, 3).map((s) => `${s.title}. ${s.detail}`)} empty="—" />
        </Section>

        <footer className="mt-6 border-t border-line pt-4 text-[11.5px] text-ink-soft">
          Made by Numera on {dateLabel(new Date(), { day: 'numeric', month: 'long', year: 'numeric' })}. Scores count a correct answer as 1 and a partly correct answer as ½.
        </footer>
      </article>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6 break-inside-avoid">
      <h2 className="mb-2.5 text-[12px] font-extrabold uppercase tracking-wider text-ink-soft">{title}</h2>
      {children}
    </section>
  );
}

function Figure({ k, v }: { k: string; v: string }) {
  return (
    <div className="rounded-[18px] bg-cream-deep px-3 py-2.5 print:border print:border-line">
      <span className="block text-[11.5px] text-ink-soft">{k}</span>
      <span className="block text-[18px] font-extrabold text-ink">{v}</span>
    </div>
  );
}

function List({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="text-[13px] text-ink-soft">{empty}</p>;
  return (
    <ul className="flex list-disc flex-col gap-1.5 pl-5 text-[13px] text-ink">
      {items.map((i) => <li key={i}>{i}</li>)}
    </ul>
  );
}

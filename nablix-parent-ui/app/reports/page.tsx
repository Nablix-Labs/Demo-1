'use client';

import { Printer } from 'lucide-react';
import Shell, { Logo } from '@/components/Shell';
import { PageHeader, dateLabel } from '@/components/ui';
import {
  attemptsIn, outcomes, sessionsIn, snapshot, strengths, developing, misconceptionCounts, nextSteps,
  MASTERY_LABEL, phaseLabel, formatDuration, avgSecondsPerQuestion, SKILL_LABEL,
} from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import type { ChildData } from '@/lib/types';

export default function ReportsPage() {
  return <Shell>{(d) => <Report d={d} />}</Shell>;
}

/**
 * One printable page. "Download" is the browser's Save as PDF, which keeps the
 * report exactly as shown and needs no server.
 */
function Report({ d }: { d: ChildData }) {
  const { range } = useChild();
  const first = d.child.name.split(' ')[0];
  const attempts = attemptsIn(d, range);
  const o = outcomes(attempts);
  const snap = snapshot(sessionsIn(d, range));
  const lastDay = new Date(range.to.getTime() - 86_400_000);

  return (
    <>
      <div className="no-print">
        <PageHeader
          title="Reports"
          subtitle={`A one-page summary of the last ${range.days} days to keep or share.`}
          action={
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-2 rounded-[18px] bg-ink px-4 py-2.5 text-[13px] font-extrabold text-white hover:opacity-90"
            >
              <Printer size={16} aria-hidden /> Print or save as PDF
            </button>
          }
        />
      </div>

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

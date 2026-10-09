'use client';

import Shell from '@/components/Shell';
import { Card, PageHeader, Pill, Empty } from '@/components/ui';
import { SKILL_TONE } from '@/components/topic';
import { SKILL_LABEL, attemptsIn, misconceptionCounts, outcomes } from '@/lib/derive';
import { useChild } from '@/lib/useChild';
import type { ChildData, SkillStatus } from '@/lib/types';

export default function SkillsPage() {
  return <Shell>{(d) => <Skills d={d} />}</Shell>;
}

const COLUMNS: { status: SkillStatus; title: string; body: string }[] = [
  { status: 'INDEPENDENTLY_VERIFIED', title: 'Strong', body: 'Solved again and again with no help.' },
  { status: 'VERIFIED_WITH_SUPPORT', title: 'Developing', body: 'Gets there, but still leans on hints.' },
  { status: 'RESCUE_REQUIRED', title: 'Needs practice', body: 'The tutor often has to step in.' },
];

function Skills({ d }: { d: ChildData }) {
  const { range } = useChild();
  const first = d.child.name.split(' ')[0];
  const attempts = attemptsIn(d, range);
  const mcs = misconceptionCounts(d, attempts);
  const topicTitle = (id: string) => d.topics.find((t) => t.topic_id === id)?.title ?? id;
  const notStarted = d.topics.flatMap((t) => t.micro_skills).filter((s) => s.status === 'UNKNOWN').length;

  return (
    <>
      <PageHeader title="Strengths & weaknesses" subtitle={`Every skill ${first} has met so far, and the mistakes that keep coming up.`} />

      <div className="grid gap-4 lg:grid-cols-3">
        {COLUMNS.map((c) => {
          const rows = d.topics.flatMap((t) => t.micro_skills.filter((s) => s.status === c.status).map((s) => ({ t, s })));
          return (
            <Card key={c.status} title={`${c.title} (${rows.length})`} subtitle={c.body}>
              {rows.length ? (
                <ul className="flex flex-col gap-2.5">
                  {rows.map(({ t, s }) => (
                    <li key={s.id} className="rounded-[18px] border border-line p-3">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[13px] font-extrabold text-ink">{s.label}</span>
                        <Pill tone={SKILL_TONE[s.status]}>{SKILL_LABEL[s.status]}</Pill>
                      </div>
                      <p className="mt-1 text-[12px] text-ink-soft">{s.description}</p>
                      <p className="mt-1.5 text-[11px] text-ink-soft/80">{t.title}</p>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-[12.5px] text-ink-soft">None right now.</p>}
            </Card>
          );
        })}
      </div>
      {notStarted > 0 && (
        <p className="mt-3 text-[12.5px] text-ink-soft">{notStarted} more skill{notStarted === 1 ? '' : 's'} in topics {first} has not started yet.</p>
      )}

      <Card title="Mistakes that keep coming up" subtitle={`Last ${range.days} days · how often each one happened`} className="mt-4">
        {mcs.length ? (
          <table className="w-full text-left text-[13px]">
            <thead>
              <tr className="border-b border-line text-[11.5px] uppercase tracking-wider text-ink-soft">
                <th className="py-2 font-extrabold">Mistake</th>
                <th className="hidden py-2 font-extrabold md:table-cell">What it looks like</th>
                <th className="py-2 font-extrabold">Topic</th>
                <th className="py-2 text-right font-extrabold">Times</th>
              </tr>
            </thead>
            <tbody>
              {mcs.map(({ misconception: m, count }) => (
                <tr key={m.id} className="border-b border-line last:border-0">
                  <td className="py-3 pr-3 font-extrabold text-ink">{m.label}</td>
                  <td className="hidden py-3 pr-3 text-ink-soft md:table-cell">{m.description}</td>
                  <td className="py-3 pr-3 text-ink-soft">{topicTitle(m.topic_id)}</td>
                  <td className="py-3 text-right font-extrabold text-[#B5334F]">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty title="No repeated mistakes" body={`Nothing came up more than once in the last ${range.days} days.`} image="hints" />
        )}
        {attempts.length > 0 && (
          <p className="mt-3 text-[12px] text-ink-soft">
            Out of {attempts.length} questions, {outcomes(attempts).incorrect} were not right first time. Mistakes are a normal part of
            learning — the tutor uses them to choose what to practise next.
          </p>
        )}
      </Card>
    </>
  );
}

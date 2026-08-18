/**
 * History — a record of past tutoring sessions.
 *
 * This was five identical rows with the score crushed into a 32px corner, so a
 * student could see THAT they had worked without seeing how it went.
 *
 * It uses the card grid the Workbook used to use: a tinted panel on top, then
 * title and meta, then a progress bar. That layout was already the strongest
 * thing in this app's library screens — it reads at a glance, it aligns on a
 * grid, and reusing it means History and the rest of the library share one
 * visual language instead of each inventing its own.
 *
 * The panel carries the score, where the Workbook card carried its folder
 * illustration: for a past session, how it went IS the picture. Colour follows
 * the brand rule that colour always means something — sage for a clean sweep,
 * blue for solid, amber where enough went wrong to be worth going back to.
 */

import Link from 'next/link';
import PageShell, { ProgressBar, Chip } from '@/components/PageShell';
import SessionTrail from '@/components/SessionTrail';

interface Session {
  date: string;
  topic: string;
  duration: string;
  questions: number;
  correct: number;
}

const SESSIONS: Session[] = [
  { date: 'Today', topic: 'Solving for x', duration: '24 min', questions: 6, correct: 5 },
  { date: '11 Jun', topic: 'Linear Equations', duration: '31 min', questions: 8, correct: 8 },
  { date: '9 Jun', topic: 'Fractions & Ratios', duration: '28 min', questions: 9, correct: 6 },
  { date: '6 Jun', topic: 'Angles & Polygons', duration: '19 min', questions: 5, correct: 4 },
  { date: '3 Jun', topic: 'Linear Equations', duration: '22 min', questions: 7, correct: 5 },
];

/** Score band. The thresholds are the ones the tutor already treats as mastery. */
function band(pct: number) {
  if (pct === 100) return { label: 'All correct', tone: 'text-success-sage' };
  if (pct >= 70) return { label: 'Solid', tone: 'text-learning-blue' };
  return { label: 'Worth another look', tone: 'text-highlight-amber' };
}

const minutes = (d: string) => parseInt(d, 10) || 0;

export default function HistoryPage() {
  const totalMin = SESSIONS.reduce((n, s) => n + minutes(s.duration), 0);
  const totalQ = SESSIONS.reduce((n, s) => n + s.questions, 0);
  const totalC = SESSIONS.reduce((n, s) => n + s.correct, 0);
  const hours = Math.floor(totalMin / 60);
  const mins = totalMin % 60;

  return (
    <PageShell title="History" subtitle="A record of your past tutoring sessions.">
      {/* What the record adds up to — the question a student opens this with. */}
      <div className="mb-5 flex items-center justify-between gap-4 rounded-lg border border-muted-gray bg-reading-surface px-5 py-3.5">
        {[
          ['Sessions', String(SESSIONS.length)],
          ['Time spent', hours ? `${hours}h ${mins}m` : `${mins}m`],
          ['Questions right', `${totalC} of ${totalQ}`],
        ].map(([label, value]) => (
          <div key={label}>
            <div className="text-[11px] font-semibold uppercase tracking-widest text-slate-blue">
              {label}
            </div>
            <div className="mt-0.5 text-[15px] font-semibold text-ink">{value}</div>
          </div>
        ))}
      </div>

      <SessionTrail />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {SESSIONS.map((s, i) => {
          const pct = Math.round((s.correct / s.questions) * 100);
          const look = band(pct);
          return (
            <Link
              key={`${s.date}-${i}`}
              href="/"
              className="group flex flex-col rounded-xl border border-muted-gray bg-white p-4 transition-all hover:border-slate-blue/40 hover:shadow-[0_8px_24px_rgba(27,42,74,0.08)]"
            >
              {/* Where the Workbook card put its folder, a session puts its score. */}
              <div className="flex flex-col items-center justify-center rounded-lg bg-reading-surface/70 px-4 py-7">
                <div className="text-[34px] font-semibold leading-none tracking-[-0.02em] tabular-nums text-ink transition-transform duration-300 group-hover:-translate-y-0.5">
                  {s.correct}
                  <span className="text-[19px] font-normal text-slate-blue">/{s.questions}</span>
                </div>
                <div
                  className={
                    'mt-2 text-[10.5px] font-semibold uppercase tracking-[0.5px] ' + look.tone
                  }
                >
                  {look.label}
                </div>
              </div>

              <div className="mt-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="truncate text-[15px] font-semibold text-ink">{s.topic}</h2>
                  <p className="mt-0.5 line-clamp-1 text-[11.5px] text-slate-blue">
                    {s.duration} · {s.questions} questions
                  </p>
                </div>
                <Chip>{s.date}</Chip>
              </div>

              <div className="mt-3.5">
                <div className="mb-1.5 flex items-center justify-between text-[11px] text-slate-blue">
                  <span>Score</span>
                  <span>{pct}%</span>
                </div>
                <ProgressBar value={pct} />
              </div>
            </Link>
          );
        })}
      </div>
    </PageShell>
  );
}

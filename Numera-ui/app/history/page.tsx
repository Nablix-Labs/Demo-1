import Link from 'next/link';
import PageShell, { ProgressBar } from '@/components/PageShell';
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

export default function HistoryPage() {
  return (
    <PageShell
      title="History"
      subtitle="A record of your past tutoring sessions."
    >
      <SessionTrail />
      <div className="rounded-lg border border-muted-gray divide-y divide-muted-gray overflow-hidden">
        {SESSIONS.map((s, i) => {
          const pct = Math.round((s.correct / s.questions) * 100);
          return (
            <div key={i} className="flex items-center gap-5 px-5 py-4 hover:bg-reading-surface transition-colors">
              <div className="flex-shrink-0 w-16 text-[12px] font-semibold text-slate-blue">{s.date}</div>
              <div className="min-w-0 flex-1">
                <div className="text-[14px] font-semibold text-ink">{s.topic}</div>
                <div className="text-[11.5px] text-slate-blue mt-0.5">
                  {s.duration} · {s.questions} questions
                </div>
              </div>
              <div className="flex-shrink-0 w-32 hidden sm:block">
                <div className="flex items-center justify-between text-[11px] text-slate-blue mb-1">
                  <span>{s.correct}/{s.questions}</span>
                  <span>{pct}%</span>
                </div>
                <ProgressBar value={pct} />
              </div>
              <Link
                href="/"
                className="flex-shrink-0 text-[12px] font-semibold text-ink underline-offset-4 hover:underline"
              >
                Open
              </Link>
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}

import Link from 'next/link';
import PageShell, { Chip } from '@/components/PageShell';

interface Flagged {
  equation: string;
  module: string;
  topic: string;
  reason: string;
  when: string;
}

const FLAGGED: Flagged[] = [
  { equation: '3(x − 2) = 9', module: 'Algebra', topic: 'Expanding Brackets', reason: 'Got stuck expanding', when: 'Today' },
  { equation: '2x + 5 = 13', module: 'Algebra', topic: 'Solving for x', reason: 'Want to revisit', when: 'Yesterday' },
  { equation: 'x² − 5x + 6 = 0', module: 'Algebra', topic: 'Quadratics', reason: 'For later', when: '4 days ago' },
  { equation: '7/8 − 1/3', module: 'Number', topic: 'Fractions', reason: 'Common denominator', when: '2 days ago' },
  { equation: '3 : 5 = 12 : ?', module: 'Number', topic: 'Ratio', reason: 'Scaling up', when: '5 days ago' },
];

export default function FlaggedPage() {
  // Segregate by module → topic
  const byModule = FLAGGED.reduce<Record<string, Flagged[]>>((acc, f) => {
    (acc[f.module] ??= []).push(f);
    return acc;
  }, {});

  return (
    <PageShell
      title="Flagged"
      subtitle="Problems you saved to come back to, grouped by module."
      action={<Chip tone="outline">{FLAGGED.length} saved</Chip>}
    >
      <div className="flex flex-col gap-7 max-w-3xl">
        {Object.entries(byModule).map(([module, items]) => (
          <section key={module}>
            <div className="flex items-center gap-2 mb-2.5">
              <span className="text-[11px] font-semibold tracking-widest uppercase text-slate-blue">{module}</span>
              <Chip>{items.length}</Chip>
            </div>
            <div className="flex flex-col gap-3">
              {items.map((f) => (
                <div
                  key={f.equation}
                  className="flex items-center gap-4 rounded-lg border border-muted-gray bg-white px-5 py-4 hover:border-muted-gray transition-colors"
                >
                  <div className="flex-shrink-0 min-w-[120px] h-12 px-4 rounded-md border border-muted-gray bg-reading-surface flex items-center justify-center text-[16px] text-ink font-[Cambria_Math,Georgia,serif]">
                    {f.equation}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] tracking-[1px] uppercase text-slate-blue">{f.topic}</div>
                    <div className="text-[13px] text-ink mt-0.5">{f.reason}</div>
                    <div className="text-[11px] text-slate-blue mt-0.5">Flagged {f.when}</div>
                  </div>
                  <Link
                    href="/"
                    className="flex-shrink-0 inline-flex items-center justify-center rounded-md border border-focus-navy text-ink text-[12px] font-semibold px-3.5 py-2 hover:bg-focus-navy hover:text-white transition-colors"
                  >
                    Review
                  </Link>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </PageShell>
  );
}

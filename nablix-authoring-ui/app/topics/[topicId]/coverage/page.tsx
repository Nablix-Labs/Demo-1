'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { BarChart3, Check, AlertTriangle, X } from 'lucide-react';
import { CoverageBadge } from '@/components/nablix/CoverageBadge';
import { CardHeader } from '@/components/nablix/GlassCard';
import { api, type CoverageGrid } from '@/lib/api';

export default function CoveragePage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [grid, setGrid] = useState<CoverageGrid | null>(null);

  useEffect(() => {
    api.getCoverageGrid(topicId).then(setGrid);
  }, [topicId]);

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <div>
        <div className="flex items-center gap-2 text-2xs font-bold uppercase tracking-widest text-learning-blue">
          <BarChart3 className="h-3.5 w-3.5" /> Coverage &amp; Validation
        </div>
        <h1 className="mt-1 font-display text-xl font-bold text-focus-navy">Coverage Grid</h1>
        <p className="mt-0.5 text-sm text-slate-blue">
          Counts <em>and</em> status per micro-skill. Click a warning or missing cell to open the correct prefilled creation form.
        </p>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-blue">
        <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-[#5c6b58]" strokeWidth={3} /> Requirement satisfied</span>
        <span className="flex items-center gap-1.5"><AlertTriangle className="h-3.5 w-3.5 text-action-orange" strokeWidth={3} /> Below recommended count / diversity</span>
        <span className="flex items-center gap-1.5"><X className="h-3.5 w-3.5 text-danger" strokeWidth={3} /> Mandatory content missing</span>
      </div>

      <section className="sheet overflow-hidden">
        <CardHeader icon={<BarChart3 className="h-4 w-4" />} title="Micro-skill coverage" />
        {grid === null ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-9 animate-pulse rounded-lg bg-muted-gray/50" />
            ))}
          </div>
        ) : (
          <div className="lg-scroll overflow-x-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead>
                <tr className="border-b border-muted-gray/70 text-left text-2xs uppercase tracking-wide text-slate-blue">
                  <th className="sticky left-0 z-10 bg-white px-5 py-2.5 font-bold">Micro-skill</th>
                  {grid.columns.map((c) => (
                    <th key={c.id} className="px-3 py-2.5 text-center font-bold">{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {grid.rows.map((row) => (
                  <tr key={row.micro_skill_id} className="border-b border-muted-gray/50 last:border-0 hover:bg-reading-surface">
                    <td className="sticky left-0 z-10 bg-white px-5 py-2.5 font-mono text-xs font-bold text-focus-navy">
                      {row.micro_skill_id}
                    </td>
                    {grid.columns.map((c) => {
                      const cell = row.cells[c.id];
                      return (
                        <td key={c.id} className="px-3 py-2.5 text-center">
                          {cell ? (
                            <CoverageBadge
                              state={cell.state}
                              count={cell.count}
                              onClick={cell.state !== 'ok' ? () => {} : undefined}
                            />
                          ) : (
                            <span className="text-slate-blue/40">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

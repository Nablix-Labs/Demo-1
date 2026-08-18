'use client';

/**
 * Coverage & Validation — v3 page 14. The grid is the primary surface; there is
 * no editor default. Cells carry their own health and required_min, and issues
 * carry the navigation metadata needed to open the affected record (guide §10.2).
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { BarChart3, ShieldCheck } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading } from '@/components/nablix/SectionHeader';
import { HealthBadge } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { CoverageData } from '@/lib/api/v3-contracts';
import { linkForCoverageCell, linkForIssue } from '@/lib/tree';
import { cn } from '@/lib/utils';

export default function CoveragePage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<CoverageData | null>(null);

  useEffect(() => {
    apiV3.getCoverage(topicId).then(setData);
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const columns = Object.keys(data.coverage_rows[0]?.cells ?? {});
  const { blocking_count, warning_count, issues } = data.validation_summary;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Coverage & Validation"
        icon={<BarChart3 className="h-3.5 w-3.5" />}
        title="Coverage & Validation"
        description="Every micro-skill against every content type. Red is mandatory content missing; amber is below recommendation."
      />

      <div className="flex flex-wrap gap-2">
        <span
          className={cn(
            'rounded-lg px-3 py-1.5 text-sm font-semibold',
            blocking_count > 0 ? 'bg-danger/10 text-danger' : 'bg-success-sage/18 text-[#5c6b58]',
          )}
        >
          {blocking_count} blocking
        </span>
        <span className="rounded-lg bg-highlight-amber/15 px-3 py-1.5 text-sm font-semibold text-action-orange">
          {warning_count} warnings
        </span>
      </div>

      <section className="sheet overflow-hidden">
        <CardHeader icon={<BarChart3 className="h-4 w-4" />} title="Coverage Grid" />
        {/* The grid is intentionally wide — it scrolls inside its own box. */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="border-b border-muted-gray/70 bg-reading-surface/60">
                <th className="sticky left-0 z-10 bg-reading-surface/95 px-4 py-2.5 text-left text-2xs font-bold uppercase tracking-wider text-slate-blue">
                  Micro-skill
                </th>
                {columns.map((c) => (
                  <th
                    key={c}
                    className="px-3 py-2.5 text-center text-2xs font-bold uppercase tracking-wider text-slate-blue"
                  >
                    {c.replace(/_/g, ' ')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.coverage_rows.map((r) => (
                <tr key={r.micro_skill_id} className="border-b border-muted-gray/50 last:border-0">
                  <td className="sticky left-0 z-10 bg-white px-4 py-2.5">
                    <div className="text-sm font-semibold text-focus-navy">{r.skill_name}</div>
                    <div className="font-mono text-2xs text-slate-blue">{r.micro_skill_id}</div>
                  </td>
                  {columns.map((c) => {
                    const cell = r.cells[c];
                    return (
                      <td key={c} className="px-3 py-2.5 text-center">
                        {cell ? (
                          <CoverageCellLink topicId={topicId} column={c}>
                            <HealthBadge health={cell.content_health} count={cell.count} />
                            <span className="text-[10px] text-slate-blue/70">min {cell.required_min}</span>
                          </CoverageCellLink>
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
      </section>

      <section className="sheet overflow-hidden">
        <CardHeader icon={<ShieldCheck className="h-4 w-4" />} title={`Validation · ${issues.length}`} />
        <ul>
          {issues.map((i) => (
            <li key={`${i.code}-${i.record_id}`} className="border-b border-muted-gray/50 last:border-0">
              <IssueBody topicId={topicId} issue={i}>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    'rounded px-1.5 py-0.5 text-2xs font-bold',
                    i.blocking ? 'bg-danger/10 text-danger' : 'bg-highlight-amber/15 text-action-orange',
                  )}
                >
                  {i.blocking ? 'BLOCKING' : 'WARNING'}
                </span>
                <span className="font-mono text-2xs text-slate-blue">{i.code}</span>
              </div>
              <p className="mt-1 text-sm text-ink">{i.message}</p>
              <p className="mt-0.5 font-mono text-2xs text-slate-blue">
                {i.record_type} · {i.record_id}
              </p>
              </IssueBody>
            </li>
          ))}
          {issues.length === 0 && (
            <li className="px-5 py-6 text-center text-sm text-slate-blue">Nothing outstanding.</li>
          )}
        </ul>
      </section>
    </div>
  );
}

/** A cell links to the section that owns it, when the column maps to one. */
function CoverageCellLink({
  topicId,
  column,
  children,
}: {
  topicId: string;
  column: string;
  children: React.ReactNode;
}) {
  const href = linkForCoverageCell(topicId, column);
  const inner = <span className="inline-flex flex-col items-center gap-0.5">{children}</span>;
  return href ? (
    <Link href={href} className="inline-block rounded transition-transform hover:scale-105">
      {inner}
    </Link>
  ) : (
    inner
  );
}

/** An issue links to its own record through navigate_to. */
function IssueBody({
  topicId,
  issue,
  children,
}: {
  topicId: string;
  issue: { navigate_to?: Parameters<typeof linkForIssue>[1]['navigate_to'] };
  children: React.ReactNode;
}) {
  const href = linkForIssue(topicId, issue);
  const inner = <div className="px-5 py-3">{children}</div>;
  return href ? (
    <Link href={href} className="block transition-colors hover:bg-reading-surface/60">
      {inner}
    </Link>
  ) : (
    inner
  );
}

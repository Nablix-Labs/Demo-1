'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { CircleAlert, TriangleAlert, ShieldCheck } from 'lucide-react';
import type { CoverageLine, ValidationIssue } from '@/lib/api/contracts';
import { CoverageBadge } from './CoverageBadge';
import { cn } from '@/lib/utils';

export function ValidationPanel({
  coverage,
  validation,
}: {
  coverage: CoverageLine[];
  validation: ValidationIssue[];
}) {
  const { topicId } = useParams<{ topicId: string }>();
  const blocking = validation.filter((v) => v.severity === 'blocking');
  const warnings = validation.filter((v) => v.severity === 'warning');

  return (
    <div className="lg-scroll flex h-full flex-col gap-4 overflow-y-auto p-4">
      {/* Coverage summary */}
      <section>
        <h3 className="mb-2 px-1 text-2xs font-bold uppercase tracking-wide text-slate-blue">Coverage Summary</h3>
        <div className="space-y-1.5">
          {coverage.map((c) => (
            <div key={c.label} className="flex items-center justify-between rounded-lg border border-muted-gray/60 bg-reading-surface px-3 py-2">
              <span className="text-[13px] font-medium text-ink/85">{c.label}</span>
              <div className="flex items-center gap-2">
                <span className="text-2xs font-bold tabular-nums text-slate-blue">
                  {c.have}/{c.need}
                </span>
                <CoverageBadge state={c.state} />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Validation */}
      <section>
        <h3 className="mb-2 px-1 text-2xs font-bold uppercase tracking-wide text-slate-blue">Validation</h3>
        {blocking.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg bg-success-sage/15 px-3 py-2.5 text-[13px] font-semibold text-[#5c6b58]">
            <ShieldCheck className="h-4 w-4" />
            No blocking errors
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg bg-danger/10 px-3 py-2.5 text-[13px] font-semibold text-danger">
            <CircleAlert className="h-4 w-4" />
            {blocking.length} blocking {blocking.length === 1 ? 'error' : 'errors'} — publishing blocked
          </div>
        )}

        <div className="mt-2 space-y-1.5">
          {[...blocking, ...warnings].map((v) => (
            <IssueRow key={v.id} issue={v} topicId={topicId} />
          ))}
        </div>
      </section>
    </div>
  );
}

function IssueRow({ issue, topicId }: { issue: ValidationIssue; topicId: string }) {
  const isBlocking = issue.severity === 'blocking';
  const body = (
    <div
      className={cn(
        'flex gap-2 rounded-lg px-3 py-2 text-xs leading-snug transition-colors',
        issue.node_route ? 'hover:bg-reading-surface' : '',
        'bg-reading-surface/60',
      )}
    >
      {isBlocking ? (
        <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
      ) : (
        <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-action-orange" />
      )}
      <span className="text-ink/80">{issue.message}</span>
    </div>
  );
  return issue.node_route ? <Link href={`/topics/${topicId}/${issue.node_route}`}>{body}</Link> : body;
}

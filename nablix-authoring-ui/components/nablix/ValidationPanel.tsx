'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { CircleAlert, TriangleAlert, ShieldCheck } from 'lucide-react';
import type { TopicDetailsData, ValidationIssue } from '@/lib/api/v3-contracts';
import { routeForPage } from '@/lib/tree';
import { cn } from '@/lib/utils';

/**
 * Right-hand panel: what this topic contains, and what is wrong with it.
 * Issues link through their own navigate_to metadata rather than a hard-coded
 * route table per issue code (guide §3.2).
 */
export function ValidationPanel({
  counts,
  issues,
}: {
  counts?: TopicDetailsData['hierarchy_counts'];
  issues: ValidationIssue[];
}) {
  const { topicId } = useParams<{ topicId: string }>();
  const blocking = issues.filter((i) => i.blocking);
  const warnings = issues.filter((i) => !i.blocking);

  return (
    <div className="lg-scroll flex h-full flex-col gap-4 overflow-y-auto p-4">
      {counts && (
        <section>
          <h3 className="mb-2 px-1 text-2xs font-bold uppercase tracking-wide text-slate-blue">Content</h3>
          <div className="space-y-1.5">
            {Object.entries(counts).map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between rounded-lg border border-muted-gray/60 bg-reading-surface px-3 py-2"
              >
                <span className="text-[13px] font-medium capitalize text-ink/85">{label.replace(/_/g, ' ')}</span>
                <span className="text-2xs font-bold tabular-nums text-slate-blue">{value}</span>
              </div>
            ))}
          </div>
        </section>
      )}

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
          {[...blocking, ...warnings].map((issue) => (
            <IssueRow key={`${issue.code}-${issue.record_id}`} issue={issue} topicId={topicId} />
          ))}
        </div>
      </section>
    </div>
  );
}

function IssueRow({ issue, topicId }: { issue: ValidationIssue; topicId: string }) {
  const route = routeForPage(issue.navigate_to?.page_id);
  const body = (
    <div
      className={cn(
        'flex gap-2 rounded-lg bg-reading-surface/60 px-3 py-2 text-xs leading-snug transition-colors',
        route && 'hover:bg-reading-surface',
      )}
    >
      {issue.blocking ? (
        <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
      ) : (
        <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-action-orange" />
      )}
      <span className="text-ink/80">{issue.message}</span>
    </div>
  );
  return route ? <Link href={`/topics/${topicId}/${route}`}>{body}</Link> : body;
}

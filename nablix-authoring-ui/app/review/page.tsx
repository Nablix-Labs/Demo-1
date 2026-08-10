'use client';

/**
 * Review Queue — v3 page 02. Blocking validation is visible before the reviewer
 * enters the topic, and approval is not offered from here when the topic has
 * blocking issues (guide §5.2).
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Check, Undo2, Eye, ShieldCheck, TriangleAlert } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { ReviewQueueItem } from '@/lib/api/v3-contracts';

export default function ReviewPage() {
  const [rows, setRows] = useState<ReviewQueueItem[] | null>(null);
  useEffect(() => {
    apiV3.getReviewQueue().then((d) => setRows(d.items));
  }, []);

  return (
    <LibraryPage
      crumb="Review"
      eyebrow="Workflow · Review Queue"
      title="Review Queue"
      description="Topics submitted for review. Approve when clean, or return with changes."
    >
      <div className="grid gap-3">
        {rows === null ? (
          Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-card bg-white/50" />)
        ) : rows.length === 0 ? (
          <div className="rounded-card border border-muted-gray/70 bg-white p-8 text-center text-sm text-slate-blue shadow-card">
            Nothing waiting for review.
          </div>
        ) : (
          rows.map((r) => {
            const blocked = r.validation.blocking_count > 0;
            return (
              <section key={r.topic_id} className="rounded-card border border-muted-gray/70 bg-white p-4 shadow-card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <TopicTag code={r.topic_code} />
                      <Link
                        href={`/topics/${r.topic_id}/details`}
                        className="font-display text-base font-bold text-focus-navy hover:text-learning-blue"
                      >
                        {r.title}
                      </Link>
                      <StatusPill status={r.workflow_status} />
                    </div>
                    <div className="mt-1 text-2xs text-slate-blue">{r.ks_stage}</div>
                    <div className="mt-2 flex items-center gap-3 text-2xs font-semibold">
                      {blocked ? (
                        <span className="text-danger">{r.validation.blocking_count} blocking</span>
                      ) : (
                        <span className="flex items-center gap-1 text-[#5c6b58]">
                          <ShieldCheck className="h-3.5 w-3.5" /> No blocking errors
                        </span>
                      )}
                      {r.validation.warning_count > 0 && (
                        <span className="flex items-center gap-1 text-action-orange">
                          <TriangleAlert className="h-3.5 w-3.5" /> {r.validation.warning_count} warnings
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/topics/${r.topic_id}/publish`} className="btn btn-secondary">
                      <Eye className="h-4 w-4" /> Review
                    </Link>
                    <button className="btn btn-secondary">
                      <Undo2 className="h-4 w-4" /> Return
                    </button>
                    <button className="btn btn-primary" disabled={blocked}>
                      <Check className="h-4 w-4" /> Approve
                    </button>
                  </div>
                </div>
              </section>
            );
          })
        )}
      </div>
    </LibraryPage>
  );
}

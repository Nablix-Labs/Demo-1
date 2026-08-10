'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ClipboardCheck, Check, Undo2, Eye, ShieldCheck, TriangleAlert } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { api, type ReviewItem } from '@/lib/api';
import { formatDateTime } from '@/lib/utils';

export default function ReviewPage() {
  const [rows, setRows] = useState<ReviewItem[] | null>(null);
  useEffect(() => { api.getReviewQueue().then(setRows); }, []);

  return (
    <LibraryPage
      crumb="Review"
      eyebrow="Workflow · Review Queue"
      title="Review Queue"
      description="Topics submitted for review. Approve when clean, or return with changes."
    >
      <div className="grid gap-3">
        {rows === null
          ? Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-28 animate-pulse rounded-card bg-white/50" />)
          : rows.length === 0 ? (
            <div className="rounded-card border border-muted-gray/70 bg-white p-8 text-center text-sm text-slate-blue shadow-card">Nothing waiting for review.</div>
          ) : rows.map((r) => (
            <section key={r.topic_id} className="rounded-card border border-muted-gray/70 bg-white p-4 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <TopicTag code={r.topic_code} />
                    <Link href={`/topics/${r.topic_id}/details`} className="font-display text-base font-bold text-focus-navy hover:text-learning-blue">{r.topic_title}</Link>
                    <StatusPill status={r.status} />
                  </div>
                  <div className="mt-1 text-2xs text-slate-blue">
                    {r.ks_stage} · submitted by {r.submitted_by} · {formatDateTime(r.submitted_at)}
                  </div>
                  <div className="mt-1 text-xs text-slate-blue">Changed: {r.changed}</div>
                  <div className="mt-2 flex items-center gap-3 text-2xs font-semibold">
                    {r.blocking_errors === 0 ? (
                      <span className="flex items-center gap-1 text-[#5c6b58]"><ShieldCheck className="h-3.5 w-3.5" /> No blocking errors</span>
                    ) : (
                      <span className="flex items-center gap-1 text-danger">{r.blocking_errors} blocking</span>
                    )}
                    {r.warnings > 0 && <span className="flex items-center gap-1 text-action-orange"><TriangleAlert className="h-3.5 w-3.5" /> {r.warnings} warnings</span>}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link href={`/topics/${r.topic_id}/publish`} className="btn btn-secondary"><Eye className="h-4 w-4" /> Review</Link>
                  <button className="btn btn-secondary"><Undo2 className="h-4 w-4" /> Return</button>
                  <button className="btn btn-primary" disabled={r.blocking_errors > 0}><Check className="h-4 w-4" /> Approve</button>
                </div>
              </div>
            </section>
          ))}
      </div>
    </LibraryPage>
  );
}

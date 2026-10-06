'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, ArrowRight } from 'lucide-react';
import { Topbar } from '@/components/nablix/Topbar';
import { StatusPill } from '@/components/nablix/StatusPill';
import { ValidationDot } from '@/components/nablix/CoverageBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { DashboardData, DashboardTopicRow } from '@/lib/api/v3-contracts';
import { cn, formatDate } from '@/lib/utils';

function Kpi({ label, value, sub }: { label: string; value?: number; sub?: string }) {
  return (
    <div className="min-w-[92px]">
      <div className="text-2xs font-semibold uppercase tracking-wide text-slate-blue">{label}</div>
      <div className="mt-1 font-display text-3xl font-bold tabular-nums leading-none text-focus-navy">
        {value ?? '—'}
      </div>
      {sub && <div className="mt-1 text-2xs text-slate-blue/80">{sub}</div>}
    </div>
  );
}

// One bar per topic from the dashboard rows' completion_percent — the only
// per-topic progress figure v3 sends (there is no history to chart a trend).
function CompletionBars({ topics }: { topics: DashboardTopicRow[] | null }) {
  if (topics === null) return <div className="h-14 animate-pulse rounded bg-reading-surface" />;
  if (topics.length === 0) return <div className="text-2xs text-slate-blue">No topics yet.</div>;
  return (
    <div className="flex flex-col gap-1.5">
      {topics.map((t) => (
        <Link key={t.topic_id} href={`/topics/${t.topic_id}/details`} className="group flex items-center gap-3" title={t.title}>
          <span className="w-12 shrink-0 font-mono text-2xs font-bold text-focus-navy group-hover:text-learning-blue">{t.topic_code}</span>
          <div className="h-1.5 min-w-0 flex-1 overflow-hidden bg-muted-gray">
            <div
              className={cn('h-full', t.completion_percent === 100 ? 'bg-lime-deep' : t.completion_percent < 60 ? 'bg-danger' : 'bg-lime')}
              style={{ width: `${t.completion_percent}%` }}
            />
          </div>
          <span className="w-9 shrink-0 text-right font-mono text-2xs font-bold tabular-nums text-slate-blue">{t.completion_percent}%</span>
        </Link>
      ))}
    </div>
  );
}

const FILTERS = ['All', 'KS3', 'KS4', 'Draft', 'In Review', 'Needs attention'];

export default function DashboardPage() {
  const [topics, setTopics] = useState<DashboardTopicRow[] | null>(null);
  const [stats, setStats] = useState<DashboardData['summary'] | null>(null);
  const [filter, setFilter] = useState('All');
  useEffect(() => {
    apiV3.getDashboard().then((d) => {
      setTopics(d.topics);
      setStats(d.summary);
    });
  }, []);

  const all = topics ?? [];
  const rows = all.filter((t) => {
    if (filter === 'All') return true;
    if (filter === 'KS3' || filter === 'KS4') return t.ks_stage === filter;
    if (filter === 'Draft') return t.workflow_status === 'DRAFT';
    if (filter === 'In Review') return t.workflow_status === 'IN_REVIEW';
    if (filter === 'Needs attention') return t.validation.state !== 'COMPLETE';
    return true;
  });
  // The card is the queue: only topics actually waiting on a decision.
  const queue = all.filter((t) => t.workflow_status === 'IN_REVIEW');
  const inReview = queue.length;
  // v3's dashboard summary has no totals for these — they roll up from the rows.
  const blockingTotal = queue.reduce((n, t) => n + t.validation.blocking_count, 0);
  const warningTotal = queue.reduce((n, t) => n + t.validation.warning_count, 0);

  return (
    <>
      <Topbar title="Content Authoring Portal" crumb="Dashboard" />
      <main className="lg-scroll flex-1 overflow-y-auto px-6 pb-10">
        {/* Masthead */}
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-2xs font-bold uppercase tracking-[0.2em] text-slate-blue">
              Curriculum · KS3–KS4 Mathematics
            </div>
            <h1 className="mt-1 font-display text-3xl font-bold tracking-tight text-focus-navy">Content readiness</h1>
          </div>
        </div>

        {/* Hero: content bank + spotlight */}
        <div className="grid items-stretch gap-4 lg:grid-cols-[1.7fr_1fr]">
          {/* Content bank card */}
          <section className="lg-glass flex flex-col rounded-card p-5">
            <div className="flex items-start justify-between">
              <div className="flex flex-wrap gap-x-8 gap-y-4">
                <Kpi label="Micro-skills" value={stats?.micro_skills} />
                <Kpi label="Diagnostic" value={stats?.diagnostic_questions} sub="questions" />
                <Kpi label="Guided" value={stats?.guided_questions} sub="questions" />
                <Kpi label="Independent" value={stats?.independent_questions} sub="questions" />
              </div>
            </div>
            <div className="mt-auto pt-6">
              <div className="mb-1.5 text-2xs font-semibold text-slate-blue">Completion by topic</div>
              <CompletionBars topics={topics} />
            </div>
          </section>

          {/* Review queue — light card, same surface as the content bank beside it */}
          <section className="lg-glass flex flex-col overflow-hidden rounded-card p-5">
            <div>
              <div className="flex items-center gap-2 text-2xs font-bold uppercase tracking-widest text-slate-blue">
                <span className="h-2 w-2 rounded-full bg-lime ring-2 ring-lime/30" />
                Review Queue
              </div>
              <div className="mt-2 flex items-end gap-2">
                <span className="font-display text-5xl font-bold tabular-nums leading-none text-focus-navy">{topics ? inReview : '—'}</span>
                <span className="max-w-[110px] pb-1 text-sm leading-tight text-slate-blue">topics awaiting review</span>
              </div>
            </div>

            <div className="mt-auto grid grid-cols-2 gap-2 pt-6">
              <div className="rounded-[14px] bg-white/70 px-3 py-2.5 ring-1 ring-inset ring-muted-gray">
                <div className="font-display text-2xl font-bold tabular-nums text-focus-navy">{topics ? warningTotal : '—'}</div>
                <div className="text-2xs font-semibold uppercase tracking-wide text-slate-blue">Warnings</div>
              </div>
              <div className="rounded-[14px] bg-white/70 px-3 py-2.5 ring-1 ring-inset ring-muted-gray">
                <div className="font-display text-2xl font-bold tabular-nums text-danger">{topics ? blockingTotal : '—'}</div>
                <div className="text-2xs font-semibold uppercase tracking-wide text-slate-blue">Blocking</div>
              </div>
            </div>

            <Link href="/review" className="btn btn-primary mt-3 w-full">
              Open review queue <ArrowRight className="h-4 w-4" />
            </Link>
          </section>
        </div>

        {/* Topics table */}
        <section className="mt-4 overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-muted-gray/70 px-5 py-3.5">
            <h2 className="font-display text-base font-bold text-focus-navy">Topics</h2>
            <div className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    'rounded-pill px-3 py-1 text-xs font-semibold transition-colors',
                    filter === f ? 'bg-lime text-focus-navy' : 'text-slate-blue hover:bg-reading-surface',
                  )}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="border-b border-muted-gray/70 text-left text-2xs uppercase tracking-wide text-slate-blue">
                  <th className="w-16 px-5 py-2.5 font-bold">Code</th>
                  <th className="px-3 py-2.5 font-bold">Topic</th>
                  <th className="px-3 py-2.5 font-bold">Stage</th>
                  <th className="px-3 py-2.5 font-bold">Completion</th>
                  <th className="px-3 py-2.5 font-bold">Coverage · D/G/I</th>
                  <th className="px-3 py-2.5 font-bold">Valid.</th>
                  <th className="px-3 py-2.5 font-bold">Status</th>
                  <th className="px-3 py-2.5 font-bold">Updated</th>
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {topics === null
                  ? Array.from({ length: 4 }).map((_, i) => (
                      <tr key={i} className="border-b border-muted-gray/50">
                        <td colSpan={9} className="px-5 py-4">
                          <div className="h-5 w-full animate-pulse rounded bg-reading-surface" />
                        </td>
                      </tr>
                    ))
                  : rows.length === 0
                  ? (
                      <tr>
                        <td colSpan={9} className="px-5 py-6 text-center text-sm text-slate-blue">
                          No topics match “{filter}”.
                        </td>
                      </tr>
                    )
                  : rows.map((t) => (
                      <tr key={t.topic_id} className="group border-b border-muted-gray/50 transition-colors last:border-0 hover:bg-reading-surface">
                        <td className="px-5 py-3">
                          <span className="font-mono text-xs font-bold text-focus-navy">{t.topic_code}</span>
                        </td>
                        <td className="px-3 py-3">
                          <Link href={`/topics/${t.topic_id}/details`} className="block">
                            <div className="font-semibold text-focus-navy group-hover:text-learning-blue">{t.title}</div>
                            <div className="font-mono text-2xs text-slate-blue/80">{t.topic_id}</div>
                          </Link>
                        </td>
                        <td className="px-3 py-3">
                          <span className="rounded-md bg-reading-surface px-2 py-0.5 text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">
                            {t.ks_stage}
                          </span>
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted-gray">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  t.completion_percent === 100 ? 'bg-lime-deep' : t.completion_percent < 60 ? 'bg-danger' : 'bg-lime',
                                )}
                                style={{ width: `${t.completion_percent}%` }}
                              />
                            </div>
                            <span className="font-mono text-2xs font-bold tabular-nums text-slate-blue">{t.completion_percent}%</span>
                          </div>
                        </td>
                        <td className="px-3 py-3 font-mono text-2xs font-semibold tabular-nums text-slate-blue">
                          {t.coverage.diagnostic} · {t.coverage.guided} · {t.coverage.independent}
                        </td>
                        <td className="px-3 py-3">
                          <ValidationDot state={t.validation.state} />
                        </td>
                        <td className="px-3 py-3">
                          <StatusPill status={t.workflow_status} />
                        </td>
                        <td className="px-3 py-3 text-2xs text-slate-blue">
                          {formatDate(t.updated_at)}
                        </td>
                        <td className="px-3 py-3">
                          <Link
                            href={`/topics/${t.topic_id}/details`}
                            className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-blue opacity-0 transition-all hover:bg-reading-surface hover:text-learning-blue group-hover:opacity-100"
                          >
                            <ArrowUpRight className="h-4 w-4" />
                          </Link>
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </section>

      </main>
    </>
  );
}

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Upload, ArrowUpRight, ArrowRight, TrendingUp } from 'lucide-react';
import { Topbar } from '@/components/nablix/Topbar';
import { StatusPill } from '@/components/nablix/StatusPill';
import { ValidationDot } from '@/components/nablix/CoverageBadge';
import { Modal } from '@/components/nablix/Modal';
import { api, type DashboardStats, type KsStage, type TopicSummary } from '@/lib/api';
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

// Mini coverage-trend bars (Sep–Dec), lime-tinted — the reference's chart cue.
const TREND = [40, 62, 55, 78, 70, 88, 82, 95, 60, 74, 90, 84];
function TrendBars() {
  return (
    <div className="flex h-14 items-end gap-1.5">
      {TREND.map((h, i) => (
        <div
          key={i}
          className={cn('w-full rounded-t-[3px]', i >= TREND.length - 3 ? 'bg-lime' : 'bg-focus-navy/15')}
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}

const FILTERS = ['All', 'KS3', 'KS4', 'Draft', 'In Review', 'Needs attention'];

export default function DashboardPage() {
  const [topics, setTopics] = useState<TopicSummary[] | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [filter, setFilter] = useState('All');
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ code: '', title: '', ks_stage: 'KS3' as KsStage });

  useEffect(() => {
    api.listTopics().then(setTopics);
    api.dashboardStats().then(setStats);
  }, []);

  const canCreate = form.code.trim() !== '' && form.title.trim() !== '';
  function createTopic() {
    if (!canCreate) return;
    const newTopic: TopicSummary = {
      topic_id: `NEW-${form.code.trim().toUpperCase()}`,
      topic_code: form.code.trim().toUpperCase(),
      topic_title: form.title.trim(),
      ks_stage: form.ks_stage,
      completion_pct: 0,
      coverage: { diagnostic: '0/0', guided: '0/0', independent: '0/0' },
      validation: 'red',
      status: 'DRAFT',
      updated_at: new Date().toISOString(),
      updated_by: 'You',
      blocking_errors: 0,
      warnings: 0,
    };
    setTopics((t) => [newTopic, ...(t ?? [])]);
    setForm({ code: '', title: '', ks_stage: 'KS3' });
    setCreating(false);
  }

  const all = topics ?? [];
  const rows = all.filter((t) => {
    if (filter === 'All') return true;
    if (filter === 'KS3' || filter === 'KS4') return t.ks_stage === filter;
    if (filter === 'Draft') return t.status === 'DRAFT';
    if (filter === 'In Review') return t.status === 'IN_REVIEW';
    if (filter === 'Needs attention') return t.validation !== 'green';
    return true;
  });
  const inReview = all.filter((t) => t.status === 'IN_REVIEW' || t.status === 'APPROVED').length;
  const authors = Array.from(new Set(all.map((t) => t.updated_by))).slice(0, 5);

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
          <div className="flex items-center gap-2">
            <button className="btn btn-secondary">
              <Upload className="h-4 w-4" /> Import Workbook
            </button>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> New Topic
            </button>
          </div>
        </div>

        {/* Hero: content bank + spotlight */}
        <div className="grid items-stretch gap-4 lg:grid-cols-[1.7fr_1fr]">
          {/* Content bank card */}
          <section className="lg-glass flex flex-col rounded-card p-5">
            <div className="flex items-start justify-between">
              <div className="flex flex-wrap gap-x-8 gap-y-4">
                <Kpi label="Micro-skills" value={stats?.micro_skills} sub="active" />
                <Kpi label="Diagnostic" value={stats?.diagnostic_questions} sub="questions" />
                <Kpi label="Guided" value={stats?.guided_questions} sub="questions" />
                <Kpi label="Independent" value={stats?.independent_questions} sub="questions" />
              </div>
              <span className="flex items-center gap-1 rounded-pill bg-lime/20 px-2.5 py-1 text-2xs font-bold text-[#5b6b12]">
                <TrendingUp className="h-3.5 w-3.5" /> +12% this month
              </span>
            </div>
            <div className="mt-auto flex items-end justify-between gap-6 pt-6">
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center justify-between text-2xs font-semibold text-slate-blue">
                  <span>Authoring throughput</span>
                  <span className="font-mono">Sep — Dec</span>
                </div>
                <TrendBars />
              </div>
              <div className="flex -space-x-2">
                {authors.map((a, i) => (
                  <span key={i} className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-focus-navy text-2xs font-bold text-white" title={a}>
                    {a.split(/[ .]/).filter(Boolean).map((p) => p[0]).slice(0, 2).join('')}
                  </span>
                ))}
              </div>
            </div>
          </section>

          {/* Spotlight — dark panel with liquid glass + lime CTA */}
          <section className="spotlight flex flex-col overflow-hidden rounded-card p-5">
            <div>
              <div className="text-2xs font-bold uppercase tracking-widest text-lime">Review Queue</div>
              <div className="mt-2 flex items-end gap-2">
                <span className="font-display text-5xl font-bold tabular-nums leading-none text-white">{inReview}</span>
                <span className="max-w-[110px] pb-1 text-sm leading-tight text-white/60">topics awaiting review</span>
              </div>
            </div>

            <div className="mt-auto grid grid-cols-2 gap-2 pt-6">
              <div className="rounded-[14px] bg-white/5 px-3 py-2.5 ring-1 ring-inset ring-white/10">
                <div className="font-display text-2xl font-bold tabular-nums text-white">{stats?.warnings ?? '—'}</div>
                <div className="text-2xs font-semibold uppercase tracking-wide text-white/55">Warnings</div>
              </div>
              <div className="rounded-[14px] bg-white/5 px-3 py-2.5 ring-1 ring-inset ring-white/10">
                <div className="font-display text-2xl font-bold tabular-nums text-danger">{stats?.blocking_errors ?? '—'}</div>
                <div className="text-2xs font-semibold uppercase tracking-wide text-white/55">Blocking</div>
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
                  : rows.map((t) => (
                      <tr key={t.topic_id} className="group border-b border-muted-gray/50 transition-colors last:border-0 hover:bg-reading-surface">
                        <td className="px-5 py-3">
                          <span className="font-mono text-xs font-bold text-focus-navy">{t.topic_code}</span>
                        </td>
                        <td className="px-3 py-3">
                          <Link href={`/topics/${t.topic_id}/details`} className="block">
                            <div className="font-semibold text-focus-navy group-hover:text-learning-blue">{t.topic_title}</div>
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
                                  t.completion_pct === 100 ? 'bg-lime-deep' : t.completion_pct < 60 ? 'bg-danger' : 'bg-lime',
                                )}
                                style={{ width: `${t.completion_pct}%` }}
                              />
                            </div>
                            <span className="font-mono text-2xs font-bold tabular-nums text-slate-blue">{t.completion_pct}%</span>
                          </div>
                        </td>
                        <td className="px-3 py-3 font-mono text-2xs font-semibold tabular-nums text-slate-blue">
                          {t.coverage.diagnostic} · {t.coverage.guided} · {t.coverage.independent}
                        </td>
                        <td className="px-3 py-3">
                          <ValidationDot state={t.validation} />
                        </td>
                        <td className="px-3 py-3">
                          <StatusPill status={t.status} />
                        </td>
                        <td className="px-3 py-3 text-2xs text-slate-blue">
                          {formatDate(t.updated_at)}
                          <div className="text-slate-blue/70">{t.updated_by}</div>
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

        <Modal
          open={creating}
          onOpenChange={setCreating}
          title="New Topic"
          description="Create a draft topic. The backend generates the topic ID on save."
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setCreating(false)}>Cancel</button>
              <button className="btn btn-primary" onClick={createTopic} disabled={!canCreate}>
                <Plus className="h-4 w-4" /> Create Draft
              </button>
            </>
          }
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Topic Code</label>
                <input className="field font-mono" placeholder="T12" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} />
              </div>
              <div>
                <label className="label">KS Stage</label>
                <div className="inline-flex overflow-hidden rounded-btn ring-1 ring-inset ring-muted-gray/70">
                  {(['KS3', 'KS4'] as const).map((s) => (
                    <button key={s} onClick={() => setForm((f) => ({ ...f, ks_stage: s }))} className={cn('px-4 py-2 text-sm font-semibold', form.ks_stage === s ? 'bg-focus-navy text-white' : 'bg-white text-slate-blue')}>{s}</button>
                  ))}
                </div>
              </div>
            </div>
            <div>
              <label className="label">Title</label>
              <input className="field" placeholder="e.g. Collecting Like Terms" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
            </div>
          </div>
        </Modal>
      </main>
    </>
  );
}

'use client';

import { Send, Eye, ShieldCheck, CircleAlert, TriangleAlert, Lock, ArrowRight } from 'lucide-react';
import { useWorkspace, useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';

export default function PublishPage() {
  const ws = useWorkspace();
  const c = useContent();
  if (!ws || !c) return <SectionLoading />;

  const blocking = ws.validation.filter((v) => v.severity === 'blocking');
  const warnings = ws.validation.filter((v) => v.severity === 'warning');
  const canPublish = blocking.length === 0;

  const flow = [
    { label: 'Diagnostic', detail: `${c.questions.filter((q) => q.phase === 'PHASE_0_DIAGNOSTIC').length} questions` },
    { label: 'Orientation', detail: `${c.orientation_video.scenes.length} scenes · ${c.support_cards.length} cards` },
    { label: 'Guided', detail: `${c.questions.filter((q) => q.phase === 'PHASE_2_GUIDED_LEARNING').length} questions` },
    { label: 'Independent', detail: `${c.questions.filter((q) => q.phase === 'PHASE_3_INDEPENDENT_PRACTICE').length} questions` },
    { label: 'Review', detail: 'readiness check' },
  ];

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Preview & Publish"
        icon={<Send className="h-3.5 w-3.5" />}
        title="Preview & Publish"
        description="Preview the topic in learner-flow order, then publish. Publishing creates an immutable version and retains the previous one."
        action={
          <button className="btn btn-secondary">
            <Eye className="h-4 w-4" /> Open Preview
          </button>
        }
      />

      {/* Learner-flow preview */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Eye className="h-4 w-4" />} title="Learner Flow" />
        <div className="flex flex-wrap items-stretch gap-2 p-4">
          {flow.map((f, i) => (
            <div key={f.label} className="flex items-center gap-2">
              <div className="rounded-lg border border-muted-gray/70 bg-white px-3 py-2 text-center">
                <div className="font-display text-sm font-bold text-focus-navy">{f.label}</div>
                <div className="text-2xs text-slate-blue">{f.detail}</div>
              </div>
              {i < flow.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-slate-blue/50" />}
            </div>
          ))}
        </div>
      </section>

      {/* Publish gate */}
      <section className="sheet">
        <CardHeader icon={<ShieldCheck className="h-4 w-4" />} title="Publish Readiness" action={<StatusPill status={ws.details.lifecycle} />} />
        <div className="space-y-3 px-5 py-4">
          {canPublish ? (
            <div className="flex items-center gap-2 rounded-lg bg-success-sage/15 px-3 py-2.5 text-sm font-semibold text-[#5c6b58]">
              <ShieldCheck className="h-4 w-4" /> No blocking errors — this topic can be published.
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-lg bg-danger/10 px-3 py-2.5 text-sm font-semibold text-danger">
              <CircleAlert className="h-4 w-4" /> {blocking.length} blocking {blocking.length === 1 ? 'error' : 'errors'} must be cleared before publishing.
            </div>
          )}

          {warnings.length > 0 && (
            <ul className="space-y-1.5">
              {warnings.map((w) => (
                <li key={w.id} className="flex items-start gap-2 rounded-lg bg-reading-surface px-3 py-2 text-xs text-ink/80">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-action-orange" />
                  {w.message}
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-center justify-between border-t border-muted-gray/60 pt-3">
            <p className="text-xs text-slate-blue">
              Publishing is blocked while any blocking validation exists (spec §15).
            </p>
            <button className="btn btn-action" disabled={!canPublish}>
              {canPublish ? <Send className="h-4 w-4" /> : <Lock className="h-4 w-4" />} Publish Topic
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

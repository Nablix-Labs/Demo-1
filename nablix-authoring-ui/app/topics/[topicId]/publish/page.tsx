'use client';

/**
 * Preview, Review & Publish — v3 page 15. Sections render in learner order, not
 * table order, and the action buttons come from workflow.available_actions —
 * they are not hard-coded here (guide §10.3).
 */
import { useEffect, useState } from 'react';
import { Send, Eye, ShieldCheck, CircleAlert, ArrowRight, Lock } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading } from '@/components/nablix/SectionHeader';
import { HealthBadge } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { PreviewPublishData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

/** Label for an action id the backend offers. Unknown ids render title-cased. */
function actionLabel(action: string) {
  return action
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export default function PublishPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<PreviewPublishData | null>(null);

  useEffect(() => {
    apiV3.getPreviewPublish(topicId).then(setData);
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const { workflow, learner_flow_sections } = data;
  const primary = workflow.available_actions.find((a) => /PUBLISH|APPROVE|SUBMIT/.test(a));

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Preview & Publish"
        icon={<Send className="h-3.5 w-3.5" />}
        title="Preview & Publish"
        description="Preview the topic in learner-flow order, then act. Available actions come from the topic's workflow state."
        action={
          <button className="btn btn-secondary">
            <Eye className="h-4 w-4" /> Open Preview
          </button>
        }
      />

      <section className="sheet overflow-hidden">
        <CardHeader icon={<Eye className="h-4 w-4" />} title="Learner Flow" />
        <div className="flex flex-wrap items-stretch gap-2 p-4">
          {learner_flow_sections.map((s, i) => (
            <div key={s.section} className="flex items-center gap-2">
              <div className="rounded-lg border border-muted-gray/70 bg-white px-3 py-2 text-center">
                <div className="font-display text-sm font-bold text-focus-navy">{s.section.replace(/_/g, ' ')}</div>
                <div className="mt-0.5 flex items-center justify-center gap-1.5 text-2xs text-slate-blue">
                  {s.count} items
                  <HealthBadge health={s.content_health} />
                </div>
              </div>
              {i < learner_flow_sections.length - 1 && <ArrowRight className="h-4 w-4 shrink-0 text-slate-blue/50" />}
            </div>
          ))}
        </div>
      </section>

      <section className="sheet">
        <CardHeader
          icon={<ShieldCheck className="h-4 w-4" />}
          title="Publish Readiness"
          action={
            <span className="rounded-pill bg-reading-surface px-2 py-0.5 text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">
              {workflow.current_status}
            </span>
          }
        />
        <div className="space-y-3 px-5 py-4">
          {workflow.publish_allowed ? (
            <div className="flex items-center gap-2 rounded-lg bg-success-sage/15 px-3 py-2.5 text-sm font-semibold text-[#5c6b58]">
              <ShieldCheck className="h-4 w-4" /> This topic can be published.
            </div>
          ) : (
            <div className="flex items-start gap-2 rounded-lg bg-danger/10 px-3 py-2.5 text-sm font-semibold text-danger">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              {workflow.publish_block_reason || 'Publishing is blocked.'}
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-t border-muted-gray/50 pt-3">
            {workflow.available_actions.length === 0 ? (
              <span className="flex items-center gap-1.5 text-xs text-slate-blue">
                <Lock className="h-3.5 w-3.5" /> No actions available in this state.
              </span>
            ) : (
              workflow.available_actions.map((a) => (
                <button
                  key={a}
                  disabled={a === primary && !workflow.publish_allowed}
                  className={cn('btn', a === primary ? 'btn-primary' : 'btn-secondary')}
                >
                  {actionLabel(a)}
                </button>
              ))
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

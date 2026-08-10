'use client';

/**
 * Topic Details — v3 page 03. The topic record itself; PUT touches only this
 * record, never the child collections (guide §6.1).
 */
import { FileText, Pencil } from 'lucide-react';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { useWorkspace } from '@/lib/workspace-context';
import { formatDateTime } from '@/lib/utils';

export default function TopicDetailsPage() {
  const ws = useWorkspace();
  if (!ws) return <SectionLoading />;

  const t = ws.topic;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic"
        icon={<FileText className="h-3.5 w-3.5" />}
        title={t.topic_title}
        description="The topic record. Editing these fields updates the topic only."
        action={
          <button className="btn btn-secondary">
            <Pencil className="h-4 w-4" /> Edit Topic
          </button>
        }
      />

      <HealthIssues health={ws.content_health} />

      <section className="sheet overflow-hidden">
        <CardHeader
          icon={<FileText className="h-4 w-4" />}
          title="Basic Details"
          action={
            <span className="flex items-center gap-2">
              <HealthBadge health={ws.content_health} />
              <StatusPill status={t.status} />
            </span>
          }
        />
        <div className="grid gap-x-8 px-5 py-4 sm:grid-cols-2">
          <Meta label="Topic ID" value={<span className="font-mono text-xs">{t.topic_id}</span>} />
          <Meta label="Topic Code" value={<span className="font-mono text-xs">{t.topic_code}</span>} />
          <Meta label="KS Stage" value={t.ks_stage} />
          <Meta label="Sequence No." value={t.sequence_no} />
          <Meta label="Version" value={t.version} />
          <Meta label="Status" value={t.status} />
          <Meta label="Created" value={formatDateTime(t.created_at)} />
          <Meta label="Last Updated" value={formatDateTime(t.updated_at)} />
        </div>
        <div className="border-t border-muted-gray/50 px-5 py-4">
          <Meta label="Learning Goal" value={t.learning_goal} />
          <Meta label="Core Message" value={t.core_message} />
        </div>
      </section>

      <section className="sheet overflow-hidden">
        <CardHeader icon={<FileText className="h-4 w-4" />} title="Content in this Topic" />
        <div className="flex flex-wrap gap-2 px-5 py-4">
          {Object.entries(ws.hierarchy_counts).map(([k, v]) => (
            <span
              key={k}
              className="inline-flex items-center gap-1.5 rounded-lg bg-reading-surface px-2.5 py-1.5 text-2xs font-semibold capitalize text-slate-blue ring-1 ring-inset ring-muted-gray/70"
            >
              {k.replace(/_/g, ' ')}
              <span className="font-mono font-bold tabular-nums text-focus-navy">{v}</span>
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

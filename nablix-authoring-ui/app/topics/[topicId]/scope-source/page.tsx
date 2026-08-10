'use client';

/**
 * Scope & Source — v3 page 04. Selecting a group shows only that group's items;
 * the source group carries provenance fields rather than scope text (guide §6.2).
 */
import { useEffect, useState } from 'react';
import { ListFilter, Plus } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { ScopeSourceData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

const str = (v: unknown) => (typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v ?? '—'));

export default function ScopeSourcePage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<ScopeSourceData | null>(null);
  const [groupId, setGroupId] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getScopeSource(topicId).then((d) => {
      setData(d);
      setGroupId(d.default_selection.group_id);
    });
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const groups = data.hierarchy.groups;
  const group = groups.find((g) => g.group_id === groupId) ?? groups[0];

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Scope & Source"
        icon={<ListFilter className="h-3.5 w-3.5" />}
        title="Scope & Source"
        description="What this topic covers, what it deliberately does not, and where the content came from."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Scope Item
          </button>
        }
      />

      <HealthIssues health={data.content_health} />

      <div className="flex flex-wrap items-center gap-1 border-b border-muted-gray/70">
        {groups.map((g) => (
          <button
            key={g.group_id}
            onClick={() => setGroupId(g.group_id)}
            className={cn(
              'flex items-center gap-2 rounded-t-lg px-3 py-2 text-sm font-semibold',
              group?.group_id === g.group_id
                ? 'bg-white text-focus-navy shadow-[inset_0_-2px_0_0_var(--lime)]'
                : 'text-slate-blue hover:text-ink',
            )}
          >
            {g.label}
            <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold tabular-nums text-slate-blue ring-1 ring-inset ring-muted-gray/70">
              {g.items.length}
            </span>
            {g.content_health && <HealthBadge health={g.content_health} />}
          </button>
        ))}
      </div>

      <section className="sheet overflow-hidden">
        <CardHeader icon={<ListFilter className="h-4 w-4" />} title={group?.label ?? 'Items'} />
        {!group || group.items.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <p className="text-sm font-semibold text-action-orange">Nothing recorded in this group.</p>
            <button className="btn btn-secondary mt-3">
              <Plus className="h-4 w-4" /> Add
            </button>
          </div>
        ) : (
          <ul>
            {group.items.map((item, i) => {
              const text = item.item_text as string | undefined;
              return (
                <li key={i} className="border-b border-muted-gray/50 px-5 py-3 last:border-0">
                  {text ? (
                    <>
                      <p className="text-sm text-ink">{text}</p>
                      <p className="mt-0.5 font-mono text-2xs text-slate-blue">{str(item.scope_item_id)}</p>
                    </>
                  ) : (
                    <div className="grid gap-x-8 sm:grid-cols-2">
                      {Object.entries(item).map(([k, v]) => (
                        <Meta key={k} label={k.replace(/_/g, ' ')} value={str(v)} />
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

'use client';

import { ListChecks, Plus, BookMarked, Check, X } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, Meta, Toggle, SectionLoading } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { cn } from '@/lib/utils';

export default function ScopeSourcePage() {
  const c = useContent();
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Scope & Source"
        icon={<ListChecks className="h-3.5 w-3.5" />}
        title="Scope & Source"
        description="What this topic does and does not cover, and where its content came from."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Scope Item
          </button>
        }
      />

      {/* Scope */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<ListChecks className="h-4 w-4" />} title="Topic Scope" />
        <ul>
          {c.scope.map((s) => {
            const included = s.scope_type === 'INCLUDED';
            return (
              <li key={s.scope_item_id} className="flex items-start gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
                <span
                  className={cn(
                    'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md',
                    included ? 'bg-success-sage/18 text-[#5c6b58]' : 'bg-danger/10 text-danger',
                  )}
                >
                  {included ? <Check className="h-3.5 w-3.5" strokeWidth={3} /> : <X className="h-3.5 w-3.5" strokeWidth={3} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-ink">{s.item_text}</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <span className={cn('text-2xs font-bold uppercase tracking-wide', included ? 'text-[#5c6b58]' : 'text-danger')}>
                      {s.scope_type}
                    </span>
                    <span className="font-mono text-2xs text-slate-blue/70">{s.scope_item_id}</span>
                  </div>
                </div>
                <Toggle on={s.active} />
              </li>
            );
          })}
        </ul>
      </section>

      {/* Source provenance */}
      <section className="sheet">
        <CardHeader icon={<BookMarked className="h-4 w-4" />} title="Source Provenance" />
        <div className="px-5 py-3">
          <Meta label="Source Type" value={<span className="font-mono text-xs">{c.source.source_type}</span>} />
          <Meta label="Source Name" value={c.source.source_name} />
          <Meta label="License" value={<span className="font-mono text-xs">{c.source.license_name}</span>} />
          <Meta label="Adapted" value={<Toggle on={c.source.adapted} labels={['Yes', 'No']} />} />
          <Meta label="Text Copied" value={<Toggle on={c.source.direct_text_copied} labels={['Yes', 'No']} />} />
          <Meta
            label="Review Status"
            value={<StatusPill status={c.source.review_status === 'APPROVED' ? 'APPROVED' : 'IN_REVIEW'} />}
          />
        </div>
      </section>
    </div>
  );
}

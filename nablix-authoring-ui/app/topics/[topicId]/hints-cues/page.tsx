'use client';

import { Lightbulb, Plus, Eye, Image as ImageIcon } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, Toggle, SectionLoading } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';

const HINT_TONE: Record<string, string> = {
  ATTENTION: 'bg-learning-blue/12 text-learning-blue',
  CONCEPT_REMINDER: 'bg-ai-cyan/12 text-dark-cyan',
  PARTIAL_STEP: 'bg-highlight-amber/12 text-action-orange',
};

export default function HintsCuesPage() {
  const c = useContent();
  if (!c) return <SectionLoading />;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Hints & Visual Cues"
        icon={<Lightbulb className="h-3.5 w-3.5" />}
        title="Hints & Visual Cues"
        description="Escalating hints and the visual cues that support them, with retrieval metadata for the tutor."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Hint
          </button>
        }
      />

      {/* Hints — ordered escalation */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Lightbulb className="h-4 w-4" />} title={`Hints · escalation order`} />
        <ol>
          {c.hints.map((h) => (
            <li key={h.hint_id} className="flex items-center gap-3 border-b border-muted-gray/50 px-5 py-3 last:border-0">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                {h.hint_level}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">{h.content}</p>
                <span className={`mt-0.5 inline-block rounded px-1.5 py-0.5 text-2xs font-bold ${HINT_TONE[h.hint_type]}`}>
                  {h.hint_type}
                </span>
              </div>
              <Toggle on={h.active} />
            </li>
          ))}
        </ol>
      </section>

      {/* Visual cues */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Eye className="h-4 w-4" />} title={`Visual Cues · ${c.visual_cues.length}`} />
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          {c.visual_cues.map((cue) => (
            <div key={cue.visual_cue_id} className="rounded-lg border border-muted-gray/70 bg-white p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-reading-surface text-slate-blue">
                    <ImageIcon className="h-4 w-4" />
                  </span>
                  <h4 className="text-sm font-semibold text-focus-navy">{cue.cue_name}</h4>
                </div>
                <StatusPill status={cue.status} />
              </div>
              <p className="mt-2 text-xs text-slate-blue">{cue.cue_purpose}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {cue.retrieval_keywords.map((k) => (
                  <span key={k} className="rounded bg-reading-surface px-1.5 py-0.5 text-2xs text-slate-blue ring-1 ring-inset ring-muted-gray/70">
                    {k}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex gap-3 font-mono text-2xs text-slate-blue/70">
                <span>embed: {cue.embedding_status}</span>
                <span>review: {cue.review_status}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

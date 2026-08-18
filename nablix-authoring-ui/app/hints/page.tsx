'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Plus, Lightbulb } from 'lucide-react';
import { LibraryPage, TopicTag } from '@/components/nablix/LibraryPage';
import { Toggle } from '@/components/nablix/SectionHeader';
import { api, type LibHint } from '@/lib/api';

const TONE: Record<string, string> = {
  ATTENTION: 'bg-learning-blue/12 text-learning-blue',
  CONCEPT_REMINDER: 'bg-ai-cyan/12 text-dark-cyan',
  PARTIAL_STEP: 'bg-highlight-amber/12 text-action-orange',
};

export default function HintsPage() {
  const [rows, setRows] = useState<LibHint[] | null>(null);
  useEffect(() => { api.getLibrary().then((l) => setRows(l.hints)); }, []);

  return (
    <LibraryPage
      crumb="Hints"
      eyebrow="Library · Hints"
      title="Hint Library"
      description="Escalating hints across topics, ordered by support level."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Hint</button>}
    >
      <section className="overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <ul className="divide-y divide-muted-gray/50">
          {rows === null ? (
            Array.from({ length: 4 }).map((_, i) => <li key={i} className="px-5 py-3"><div className="h-6 animate-pulse rounded bg-reading-surface" /></li>)
          ) : rows.map((h) => (
            <li key={`${h.topic_id}-${h.hint_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-reading-surface">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">L{h.hint_level}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">{h.content}</p>
                <div className="mt-1 flex items-center gap-2">
                  <Link href={`/topics/${h.topic_id}/hints-cues`}><TopicTag code={h.topic_code} /></Link>
                  <span className={`rounded px-1.5 py-0.5 text-2xs font-bold ${TONE[h.hint_type]}`}>{h.hint_type}</span>
                </div>
              </div>
              <Toggle on={h.active} />
            </li>
          ))}
        </ul>
      </section>
    </LibraryPage>
  );
}

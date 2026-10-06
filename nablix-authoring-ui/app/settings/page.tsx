'use client';

import { ListTree } from 'lucide-react';
import { LibraryNotice, LibraryPage } from '@/components/nablix/LibraryPage';
import { loadReferenceValues } from '@/lib/api/library';
import { useLibrary } from '@/lib/useLibrary';

/**
 * There is no settings or vocabulary endpoint. This page lists the distinct
 * values live content actually uses — read off the dashboard and every topic's
 * questions — so it reflects the data, not an allowed list.
 */
export default function SettingsPage() {
  const { data, error } = useLibrary(loadReferenceValues);

  return (
    <LibraryPage
      crumb="Settings"
      eyebrow="Settings · Reference Data"
      title="Reference values in live content"
      description="The distinct values present across the dashboard and every topic's questions. A value no record uses yet does not appear."
    >
      <LibraryNotice error={error} failed={data?.failed} />
      <div className="grid gap-3 md:grid-cols-2">
        {data === null
          ? !error && Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-card bg-white/50" />)
          : data.rows.map((s) => (
            <section key={s.label} className="rounded-card border border-muted-gray/70 bg-white p-4 shadow-card">
              <div className="flex items-center gap-2">
                <ListTree className="h-4 w-4 text-learning-blue" />
                <h2 className="font-display text-sm font-bold text-focus-navy">{s.label}</h2>
                <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">{s.values.length}</span>
              </div>
              <p className="mt-0.5 font-mono text-2xs text-slate-blue">{s.source}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {s.values.length === 0
                  ? <span className="text-xs text-slate-blue">None present.</span>
                  : s.values.map((v) => (
                    <span key={v} className="rounded-md bg-reading-surface px-2 py-0.5 font-mono text-2xs text-focus-navy ring-1 ring-inset ring-muted-gray/70">{v}</span>
                  ))}
              </div>
            </section>
          ))}
      </div>
    </LibraryPage>
  );
}

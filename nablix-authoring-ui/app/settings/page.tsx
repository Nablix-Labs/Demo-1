'use client';

import { useEffect, useState } from 'react';
import { Upload, ListTree } from 'lucide-react';
import { LibraryPage } from '@/components/nablix/LibraryPage';
import { api, type SettingsData } from '@/lib/api';

export default function SettingsPage() {
  const [data, setData] = useState<SettingsData | null>(null);
  useEffect(() => { api.getSettings().then(setData); }, []);

  return (
    <LibraryPage
      crumb="Settings"
      eyebrow="Settings · Reference Data"
      title="Portal Settings"
      description="Allowed vocabularies the authoring forms enforce, and workbook import."
      action={<button className="btn btn-secondary"><Upload className="h-4 w-4" /> Import Workbook</button>}
    >
      <div className="grid gap-3 md:grid-cols-2">
        {data === null
          ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-40 animate-pulse rounded-card bg-white/50" />)
          : data.reference_sets.map((s) => (
            <section key={s.label} className="rounded-card border border-muted-gray/70 bg-white p-4 shadow-card">
              <div className="flex items-center gap-2">
                <ListTree className="h-4 w-4 text-learning-blue" />
                <h2 className="font-display text-sm font-bold text-focus-navy">{s.label}</h2>
                <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold text-slate-blue ring-1 ring-inset ring-muted-gray/70">{s.values.length}</span>
              </div>
              <p className="mt-0.5 text-xs text-slate-blue">{s.description}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {s.values.map((v) => (
                  <span key={v} className="rounded-md bg-reading-surface px-2 py-0.5 font-mono text-2xs text-focus-navy ring-1 ring-inset ring-muted-gray/70">{v}</span>
                ))}
              </div>
            </section>
          ))}
      </div>
    </LibraryPage>
  );
}

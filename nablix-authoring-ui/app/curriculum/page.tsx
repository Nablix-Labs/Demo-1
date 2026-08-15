'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Folder, FolderOpen, BookOpen, Target, Plus, ArrowUpRight } from 'lucide-react';
import { LibraryPage } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { api, type CurriculumNode } from '@/lib/api';
import { cn } from '@/lib/utils';

function Node({ node, depth }: { node: CurriculumNode; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = !!node.children?.length;
  const Icon = node.kind === 'topic' ? BookOpen : node.kind === 'micro-skill' ? Target : open ? FolderOpen : Folder;

  const labelContents = (
    <>
      <Icon className={cn('h-4 w-4 shrink-0', node.kind === 'topic' ? 'text-learning-blue' : node.kind === 'micro-skill' ? 'text-slate-blue' : 'text-highlight-amber')} />
      <span className={cn('truncate text-sm', node.kind === 'stage' ? 'font-bold text-focus-navy' : node.kind === 'subject' ? 'font-semibold text-focus-navy' : 'text-ink')}>
        {node.label}
      </span>
      {node.status && <StatusPill status={node.status} className="ml-1 shrink-0" />}
      {node.topic_id && <ArrowUpRight className="ml-auto h-3.5 w-3.5 shrink-0 text-slate-blue opacity-0 transition-opacity group-hover:opacity-100" />}
    </>
  );

  return (
    <li>
      <div
        className="group flex items-center gap-2 rounded-lg py-1.5 pr-2 transition-colors hover:bg-reading-surface"
        style={{ paddingLeft: 8 + depth * 18 }}
      >
        {hasChildren ? (
          <button onClick={() => setOpen((o) => !o)} className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-blue/70 hover:text-ink">
            <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} />
          </button>
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        {node.topic_id ? (
          <Link href={`/topics/${node.topic_id}/details`} className="flex min-w-0 flex-1 items-center gap-2">{labelContents}</Link>
        ) : (
          <div className="flex min-w-0 flex-1 items-center gap-2">{labelContents}</div>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children!.map((c) => <Node key={c.id} node={c} depth={depth + 1} />)}
        </ul>
      )}
    </li>
  );
}

export default function CurriculumPage() {
  const [tree, setTree] = useState<CurriculumNode[] | null>(null);
  useEffect(() => { api.getCurriculum().then(setTree); }, []);

  return (
    <LibraryPage
      crumb="Curriculum"
      eyebrow="Curriculum · KS3–KS4"
      title="Curriculum Explorer"
      description="Every stage, subject, topic and micro-skill in one tree. Open a topic to author its content."
      action={<button className="btn btn-primary"><Plus className="h-4 w-4" /> New Topic</button>}
    >
      <section className="max-w-3xl overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="border-b border-muted-gray/70 px-5 py-3">
          <h2 className="font-display text-base font-bold text-focus-navy">Content Tree</h2>
        </div>
        {tree === null ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-7 animate-pulse rounded bg-reading-surface" style={{ marginLeft: (i % 3) * 16 }} />)}
          </div>
        ) : (
          <ul className="p-2">{tree.map((n) => <Node key={n.id} node={n} depth={0} />)}</ul>
        )}
      </section>
    </LibraryPage>
  );
}

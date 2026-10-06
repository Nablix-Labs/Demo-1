'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Folder, FolderOpen, BookOpen, Target, ArrowUpRight } from 'lucide-react';
import { LibraryNotice, LibraryPage, RowHealth } from '@/components/nablix/LibraryPage';
import { StatusPill } from '@/components/nablix/StatusPill';
import { loadCurriculum, type CurriculumStage } from '@/lib/api/library';
import type { ContentHealth } from '@/lib/api/v3-contracts';
import { useLibrary } from '@/lib/useLibrary';
import { cn } from '@/lib/utils';

/** One row of the tree, built from the dashboard topic list and each topic's
 *  micro-skills page. */
interface TreeNode {
  id: string;
  kind: 'stage' | 'topic' | 'micro-skill';
  label: string;
  code?: string;
  href?: string;
  status?: string;
  health?: ContentHealth;
  note?: string;
  children?: TreeNode[];
}

function toTree(stages: CurriculumStage[]): TreeNode[] {
  return stages.map((s) => ({
    id: `stage-${s.ks_stage}`,
    kind: 'stage',
    label: s.ks_stage,
    note: `${s.topics.length} topic${s.topics.length === 1 ? '' : 's'}`,
    children: s.topics.map(({ topic: t, micro_skills }) => ({
      id: `topic-${t.topic_id}`,
      kind: 'topic',
      label: t.title,
      code: t.topic_code,
      href: `/topics/${t.topic_id}/details`,
      status: t.workflow_status,
      note: micro_skills === null ? 'micro-skills could not be loaded' : undefined,
      children: (micro_skills ?? []).map((m) => ({
        id: `ms-${t.topic_id}-${m.micro_skill_id}`,
        kind: 'micro-skill',
        label: m.label,
        code: m.micro_skill_id,
        href: `/topics/${t.topic_id}/micro-skills`,
        health: m.content_health,
      })),
    })),
  }));
}

function Node({ node, depth }: { node: TreeNode; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = !!node.children?.length;
  const Icon = node.kind === 'topic' ? BookOpen : node.kind === 'micro-skill' ? Target : open ? FolderOpen : Folder;

  const labelContents = (
    <>
      <Icon className={cn('h-4 w-4 shrink-0', node.kind === 'topic' ? 'text-learning-blue' : node.kind === 'micro-skill' ? 'text-slate-blue' : 'text-highlight-amber')} />
      {node.code && <span className="shrink-0 font-mono text-2xs font-bold text-slate-blue">{node.code}</span>}
      <span className={cn('truncate text-sm', node.kind === 'stage' ? 'font-bold text-focus-navy' : node.kind === 'topic' ? 'font-semibold text-focus-navy' : 'text-ink')}>
        {node.label}
      </span>
      {node.status && <StatusPill status={node.status} className="ml-1 shrink-0" />}
      {node.health && <RowHealth health={node.health} />}
      {node.note && <span className={cn('shrink-0 text-2xs', node.kind === 'topic' ? 'font-semibold text-danger' : 'text-slate-blue')}>{node.note}</span>}
      {node.href && <ArrowUpRight className="ml-auto h-3.5 w-3.5 shrink-0 text-slate-blue opacity-0 transition-opacity group-hover:opacity-100" />}
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
        {node.href ? (
          <Link href={node.href} className="flex min-w-0 flex-1 items-center gap-2">{labelContents}</Link>
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
  const { data, error } = useLibrary(loadCurriculum);
  const tree = data ? toTree(data) : null;

  return (
    <LibraryPage
      crumb="Curriculum"
      eyebrow="Curriculum · Key stages"
      title="Curriculum Explorer"
      description="Every key stage, topic and micro-skill in one tree. Open a topic to review its content."
    >
      <LibraryNotice error={error} />
      <section className="max-w-3xl overflow-hidden rounded-card border border-muted-gray/70 bg-white shadow-card">
        <div className="border-b border-muted-gray/70 px-5 py-3">
          <h2 className="font-display text-base font-bold text-focus-navy">Content Tree</h2>
        </div>
        {tree === null ? (
          !error && (
            <div className="space-y-2 p-5">
              {Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-7 animate-pulse rounded bg-reading-surface" style={{ marginLeft: (i % 3) * 16 }} />)}
            </div>
          )
        ) : tree.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-blue">No topics in live content.</p>
        ) : (
          <ul className="p-2">{tree.map((n) => <Node key={n.id} node={n} depth={0} />)}</ul>
        )}
      </section>
    </LibraryPage>
  );
}

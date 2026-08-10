'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronRight,
  Plus,
  FileText,
  Target,
  PlayCircle,
  FlaskConical,
  HelpCircle,
  AlertOctagon,
  Lightbulb,
  Layers,
  BarChart3,
  Send,
  Folder,
  Dot,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TreeNode, TreeNodeKind } from '@/lib/api/contracts';

const ICON: Partial<Record<TreeNodeKind, React.ComponentType<{ className?: string }>>> = {
  topic: Folder,
  details: FileText,
  'scope-source': FileText,
  'micro-skills': Target,
  'micro-skill': Dot,
  orientation: PlayCircle,
  'worked-examples': FlaskConical,
  questions: HelpCircle,
  phase: ChevronRight,
  misconceptions: AlertOctagon,
  'hints-cues': Lightbulb,
  scaffolds: Layers,
  coverage: BarChart3,
  publish: Send,
  group: Dot,
};

function nodeHref(topicId: string, route?: string) {
  if (!route) return undefined;
  return `/topics/${topicId}/${route}`;
}

function Row({
  node,
  topicId,
  depth,
  activeRoute,
}: {
  node: TreeNode;
  topicId: string;
  depth: number;
  activeRoute: string;
}) {
  const hasChildren = !!node.children?.length;
  const [open, setOpen] = useState(depth < 1);
  const href = nodeHref(topicId, node.route);
  const active = !!node.route && activeRoute === node.route.split('?')[0];
  const Icon = ICON[node.kind] ?? Dot;

  const inner = (
    <div
      className={cn(
        'group/row flex items-center gap-1.5 rounded-lg py-1.5 pr-1.5 text-[13px] transition-colors',
        active
          ? 'bg-learning-blue/12 font-semibold text-learning-blue'
          : 'text-ink/80 hover:bg-reading-surface',
      )}
      style={{ paddingLeft: 6 + depth * 14 }}
    >
      {hasChildren ? (
        <button
          onClick={(e) => {
            e.preventDefault();
            setOpen((o) => !o);
          }}
          className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-blue/70 hover:text-ink"
          aria-label={open ? 'Collapse' : 'Expand'}
        >
          <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')} />
        </button>
      ) : (
        <span className="h-4 w-4 shrink-0" />
      )}

      <Icon className={cn('h-4 w-4 shrink-0', active ? 'text-learning-blue' : 'text-slate-blue')} />
      <span className="min-w-0 flex-1 truncate">{node.label}</span>

      {node.count !== undefined && (
        <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold tabular-nums text-slate-blue ring-1 ring-inset ring-muted-gray/70">
          {node.count}
        </span>
      )}

      {node.addable && (
        <button
          className="lg-chip flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-learning-blue opacity-0 transition-opacity group-hover/row:opacity-100"
          title={`Add to ${node.label}`}
          onClick={(e) => e.preventDefault()}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
        </button>
      )}
    </div>
  );

  return (
    <li>
      {href ? <Link href={href}>{inner}</Link> : inner}
      {hasChildren && open && (
        <ul className="lg-anim-fade">
          {node.children!.map((child) => (
            <Row key={child.id} node={child} topicId={topicId} depth={depth + 1} activeRoute={activeRoute} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Tree({
  root,
  topicId,
  activeRoute,
}: {
  root: TreeNode;
  topicId: string;
  activeRoute: string;
}) {
  return (
    <ul className="lg-scroll space-y-0.5 overflow-y-auto px-2 py-2">
      {root.children?.map((node) => (
        <Row key={node.id} node={node} topicId={topicId} depth={0} activeRoute={activeRoute} />
      ))}
    </ul>
  );
}

'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronRight,
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
import { ValidationDot } from './CoverageBadge';
import type { TreeNode, TreeNodeKind } from '@/lib/tree';

const ICON: Partial<Record<TreeNodeKind, React.ComponentType<{ className?: string }>>> = {
  topic: Folder,
  details: FileText,
  'scope-source': FileText,
  'micro-skills': Target,
  orientation: PlayCircle,
  'worked-examples': FlaskConical,
  questions: HelpCircle,
  phase: ChevronRight,
  misconceptions: AlertOctagon,
  'hints-cues': Lightbulb,
  scaffolds: Layers,
  coverage: BarChart3,
  publish: Send,
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
        // Each row is its own bordered box (Manav, 6 Oct), so the sections
        // read as separate items rather than a run of text.
        'flex items-center gap-1.5 border py-2 pr-2 text-[13px] transition-colors',
        active
          ? 'border-learning-blue/50 bg-learning-blue/10 font-semibold text-learning-blue'
          : 'border-muted-gray/80 bg-white/70 text-ink/80 hover:border-slate-blue/40 hover:bg-white',
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

      {node.health && <ValidationDot state={node.health} className="shrink-0" />}

      {node.count !== undefined && (
        <span className="rounded-pill bg-reading-surface px-1.5 text-2xs font-bold tabular-nums text-slate-blue ring-1 ring-inset ring-muted-gray/70">
          {node.count}
        </span>
      )}

      {/* node.addable is ignored: there is no create endpoint behind it. */}
    </div>
  );

  return (
    <li>
      {href ? <Link href={href}>{inner}</Link> : inner}
      {hasChildren && open && (
        <ul className="lg-anim-fade mt-1 space-y-1">
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
    <ul className="lg-scroll space-y-1.5 overflow-y-auto px-3 py-2">
      {root.children?.map((node) => (
        <Row key={node.id} node={node} topicId={topicId} depth={0} activeRoute={activeRoute} />
      ))}
    </ul>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useParams, usePathname } from 'next/navigation';
import { Save, ShieldCheck, Eye, Send, MoreHorizontal } from 'lucide-react';
import { Topbar } from '@/components/nablix/Topbar';
import { Tree } from '@/components/nablix/Tree';
import { ValidationPanel } from '@/components/nablix/ValidationPanel';
import { StatusPill } from '@/components/nablix/StatusPill';
import { WorkspaceProvider } from '@/lib/workspace-context';
import { buildTopicTree, healthByRoute } from '@/lib/tree';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { CoverageData, TopicDetailsData } from '@/lib/api/v3-contracts';

export default function TopicWorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { topicId } = useParams<{ topicId: string }>();
  const pathname = usePathname();
  const [ws, setWs] = useState<TopicDetailsData | null>(null);
  const [coverage, setCoverage] = useState<CoverageData | null>(null);

  useEffect(() => {
    let alive = true;
    setCoverage(null);
    apiV3.getTopicDetails(topicId).then((w) => alive && setWs(w));
    apiV3.getCoverage(topicId).then((c) => alive && setCoverage(c));
    return () => {
      alive = false;
    };
  }, [topicId]);

  // Active tree route = the path segment(s) after /topics/[topicId]/
  const activeRoute = pathname.split(`/topics/${topicId}/`)[1]?.split('/')[0] ?? 'details';

  return (
    <>
      <Topbar title="Content Authoring Portal" crumb={ws?.topic.topic_title ?? topicId} />

      {/* Workspace action bar */}
      <div className="relative z-10 flex flex-wrap items-center gap-3 px-6 pb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h2 className="truncate font-display text-lg font-bold text-focus-navy">
              {ws ? ws.topic.topic_title : 'Loading…'}
            </h2>
            {ws && <StatusPill status={ws.topic.status} />}
          </div>
          {ws && (
            <div className="mt-0.5 flex items-center gap-2 font-mono text-2xs font-medium text-slate-blue">
              <span>{ws.topic.topic_id}</span>
              <span className="text-slate-blue/40">·</span>
              <span>{ws.topic.ks_stage}</span>
              <span className="text-slate-blue/40">·</span>
              <span>v{ws.topic.version}</span>
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button className="btn btn-secondary">
            <Save className="h-4 w-4" /> Save Draft
          </button>
          <button className="btn btn-secondary">
            <ShieldCheck className="h-4 w-4" /> Validate
          </button>
          <button className="btn btn-secondary">
            <Eye className="h-4 w-4" /> Preview
          </button>
          <button className="btn btn-primary">
            <Send className="h-4 w-4" /> Submit for Review
          </button>
          <button className="lg-chip flex h-9 w-9 items-center justify-center rounded-btn text-slate-blue">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Three-pane frame — contained horizontal scroll on very narrow windows
          so the editor never crushes (spec §17 targets laptop widths). */}
      <div className="lg-scroll relative z-10 min-h-0 flex-1 overflow-x-auto px-4 pb-4">
      <div className="grid h-full min-w-[1000px] grid-cols-[240px_minmax(0,1fr)_300px] gap-3 xl:grid-cols-[260px_minmax(0,1fr)_320px]">
        {/* Left — hierarchy tree */}
        <div className="lg-glass flex min-h-0 flex-col rounded-card">
          <div className="flex items-center justify-between px-4 py-3">
            <h3 className="text-2xs font-bold uppercase tracking-wide text-slate-blue">Content Hierarchy</h3>
          </div>
          {ws ? (
            <Tree
              root={buildTopicTree(ws.hierarchy_counts, healthByRoute(coverage?.validation_summary.issues ?? []))}
              topicId={topicId}
              activeRoute={activeRoute}
            />
          ) : (
            <TreeSkeleton />
          )}
        </div>

        {/* Center — editor canvas (light, so white sub-cards read as sheets on a desk) */}
        <div className="min-h-0 overflow-hidden rounded-card bg-reading-surface shadow-[0_1px_2px_rgba(11,16,32,0.06),0_16px_38px_rgba(8,12,24,0.2)]">
          {ws ? (
            <WorkspaceProvider value={{ workspace: ws, coverage }}>
              <div className="lg-scroll h-full overflow-y-auto">{children}</div>
            </WorkspaceProvider>
          ) : (
            <div className="p-6">
              <div className="h-8 w-52 animate-pulse rounded bg-white/50" />
              <div className="mt-4 h-40 w-full animate-pulse rounded-card bg-white/40" />
            </div>
          )}
        </div>

        {/* Right — validation / coverage */}
        <div className="lg-glass min-h-0 rounded-card">
          {ws ? (
            <ValidationPanel counts={ws.hierarchy_counts} issues={coverage?.validation_summary.issues ?? []} />
          ) : (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-white/40" />
              ))}
            </div>
          )}
        </div>
      </div>
      </div>
    </>
  );
}

function TreeSkeleton() {
  return (
    <div className="space-y-1.5 px-3 py-2">
      {Array.from({ length: 9 }).map((_, i) => (
        <div key={i} className="h-7 animate-pulse rounded-lg bg-white/40" style={{ marginLeft: (i % 3) * 12 }} />
      ))}
    </div>
  );
}

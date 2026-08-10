'use client';

/**
 * Hints & Visual Cues — v3 page 12.
 *
 * The misconception is the parent filter. A hint or cue is visible only while
 * its misconception is selected; changing the parent replaces the child list
 * and auto-selects that parent's first child (guide §9.2). Nothing here sorts
 * or picks a default on its own — order comes from sequence_order and the
 * opening selection comes from default_selection.
 */
import { useEffect, useMemo, useState } from 'react';
import { Lightbulb, Plus, Image as ImageIcon, Link2, Users } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Toggle, Meta } from '@/components/nablix/SectionHeader';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type {
  HintsVisualCuesData,
  MisconceptionGroup,
  SupportChild,
  SupportType,
} from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

const childId = (c: SupportChild) => c.hint_id ?? c.visual_cue_id ?? '';

/** The children of a group for the active tab — the parent/child filter itself. */
function childrenFor(group: MisconceptionGroup | undefined, tab: SupportType): SupportChild[] {
  if (!group) return [];
  return tab === 'HINT' ? group.hints : group.visual_cues;
}

export default function HintsCuesPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<HintsVisualCuesData | null>(null);
  const [parentId, setParentId] = useState<string | null>(null);
  const [tab, setTab] = useState<SupportType>('HINT');
  const [childSelected, setChildSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getSupportAssets(topicId).then((d) => {
      setData(d);
      setParentId(d.default_selection.misconception_id);
      setTab(d.default_selection.support_type);
      setChildSelected(d.default_selection.support_id);
    });
  }, [topicId]);

  const groups = data?.hierarchy.misconception_groups ?? [];
  const parent = useMemo(
    () => groups.find((g) => g.misconception_id === parentId),
    [groups, parentId],
  );
  const children = childrenFor(parent, tab);

  /** Parent or tab changed: keep the parent, reset to its first child. */
  function selectParent(id: string) {
    setParentId(id);
    const next = childrenFor(groups.find((g) => g.misconception_id === id), tab);
    setChildSelected(next.length ? childId(next[0]) : null);
  }

  function selectTab(next: SupportType) {
    setTab(next);
    const list = childrenFor(parent, next);
    setChildSelected(list.length ? childId(list[0]) : null);
  }

  if (!data) return <SectionLoading />;

  const selectedChild = children.find((c) => childId(c) === childSelected) ?? null;
  /** The API's detail payload is only valid for the selection it was built for. */
  const detail =
    data.selected_item.parent_context.selected_misconception.misconception_id === parentId &&
    data.selected_item.entity_type === tab &&
    (data.selected_item.hint_id ?? data.selected_item.visual_cue_id) === childSelected
      ? data.selected_item
      : null;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Hints & Visual Cues"
        icon={<Lightbulb className="h-3.5 w-3.5" />}
        title="Hints & Visual Cues"
        description="Support content lives under the misconception it repairs. Select a misconception to see only its support."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add {tab === 'HINT' ? 'Hint' : 'Visual Cue'}
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        {/* Parent: misconceptions */}
        <section className="sheet overflow-hidden self-start">
          <CardHeader icon={<Link2 className="h-4 w-4" />} title={`Misconceptions · ${groups.length}`} />
          <ul>
            {groups.map((g) => {
              const active = g.misconception_id === parentId;
              return (
                <li key={g.misconception_id}>
                  <button
                    onClick={() => selectParent(g.misconception_id)}
                    className={cn(
                      'flex w-full items-start gap-2 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                      active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className={cn('block text-sm font-semibold', active ? 'text-white' : 'text-focus-navy')}>
                        {g.label}
                      </span>
                      <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                        {g.hints.length} hints · {g.visual_cues.length} cues
                      </span>
                    </span>
                    <HealthBadge health={g.content_health} />
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="min-w-0 space-y-4">
          {/* Tabs + child list, filtered by the selected parent */}
          <section className="sheet overflow-hidden">
            <div className="flex items-center gap-1 border-b border-muted-gray/70 px-3 pt-3">
              {data.tabs.map((t) => (
                <button
                  key={t.tab_id}
                  onClick={() => selectTab(t.tab_id as SupportType)}
                  className={cn(
                    'rounded-t-lg px-3 py-2 text-sm font-semibold',
                    tab === t.tab_id
                      ? 'bg-white text-focus-navy shadow-[inset_0_-2px_0_0_var(--lime)]'
                      : 'text-slate-blue hover:text-ink',
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {children.length === 0 ? (
              /* Deliberate authoring state — never fall back to another parent */
              <div className="px-5 py-8 text-center">
                <p className="text-sm font-semibold text-action-orange">
                  No {tab === 'HINT' ? 'hints have' : 'visual cues have'} been created for this misconception.
                </p>
                <button className="btn btn-secondary mt-3">
                  <Plus className="h-4 w-4" /> Add {tab === 'HINT' ? 'Hint' : 'Visual Cue'}
                </button>
              </div>
            ) : (
              <ol>
                {children.map((c) => {
                  const id = childId(c);
                  const active = id === childSelected;
                  return (
                    <li key={id}>
                      <button
                        onClick={() => setChildSelected(id)}
                        className={cn(
                          'flex w-full items-center gap-3 border-b border-muted-gray/50 px-5 py-3 text-left last:border-0',
                          active ? 'bg-reading-surface' : 'hover:bg-reading-surface/60',
                        )}
                      >
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-focus-navy font-mono text-2xs font-bold text-white">
                          {c.sequence_order}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-ink">{c.preview || c.label}</span>
                          <span className="mt-0.5 block font-mono text-2xs text-slate-blue">{id}</span>
                        </span>
                        {(c.shared_by_misconception_count ?? 0) > 1 && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-learning-blue/12 px-1.5 py-0.5 text-2xs font-bold text-learning-blue">
                            <Users className="h-3 w-3" /> {c.shared_by_misconception_count}
                          </span>
                        )}
                        <HealthBadge health={c.content_health} />
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {/* Detail + impact context for the selected child */}
          {selectedChild && (
            <section className="sheet overflow-hidden">
              <CardHeader
                icon={tab === 'HINT' ? <Lightbulb className="h-4 w-4" /> : <ImageIcon className="h-4 w-4" />}
                title={selectedChild.label}
                action={<Toggle on={selectedChild.active} />}
              />
              <div className="space-y-3 px-5 py-4">
                <p className="text-sm text-ink">{detail?.content ?? selectedChild.preview}</p>

                <HealthIssues health={selectedChild.content_health} />

                {(selectedChild.shared_by_misconception_count ?? 0) > 1 && (
                  <div className="flex items-start gap-2 rounded-lg bg-learning-blue/10 px-3 py-2 text-xs text-learning-blue">
                    <Users className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>
                      Used by {selectedChild.shared_by_misconception_count} misconceptions — editing this
                      changes the support shown for all of them.
                    </span>
                  </div>
                )}

                {detail && (
                  <div className="grid gap-x-6 sm:grid-cols-2">
                    <Meta
                      label="Micro-skills"
                      value={detail.impact_context.related_micro_skills.map((s) => s.skill_name).join(', ') || '—'}
                    />
                    <Meta
                      label="Linked errors"
                      value={detail.impact_context.linked_errors.map((e) => e.error_name).join(', ') || '—'}
                    />
                    <Meta
                      label="Affected questions"
                      value={detail.impact_context.affected_questions.length || '—'}
                    />
                    <Meta label="Order under parent" value={detail.parent_context.sequence_order} />
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

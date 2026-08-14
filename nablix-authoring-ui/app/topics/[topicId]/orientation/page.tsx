'use client';

/**
 * Orientation — v3 page 06. Video → Scenes and Support Cards are sibling
 * branches: selecting a card must not leave a scene editor open (guide §7.1).
 * Scenes render in scene_no order exactly as sent.
 */
import { useEffect, useState } from 'react';
import { PlayCircle, Plus, LayoutGrid, Clock } from 'lucide-react';
import { useParams } from 'next/navigation';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, Meta } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { HealthBadge, HealthIssues } from '@/components/nablix/HealthBadge';
import { apiV3 } from '@/lib/api/v3Adapter';
import type { OrientationData } from '@/lib/api/v3-contracts';
import { cn } from '@/lib/utils';

type Branch = 'SCENES' | 'CARDS';

export default function OrientationPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const [data, setData] = useState<OrientationData | null>(null);
  const [branch, setBranch] = useState<Branch>('SCENES');
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiV3.getOrientation(topicId).then((d) => {
      setData(d);
      const isCard = d.default_selection.node_type.toUpperCase().includes('CARD');
      setBranch(isCard ? 'CARDS' : 'SCENES');
      setSelected(d.default_selection.node_id);
    });
  }, [topicId]);

  if (!data) return <SectionLoading />;

  const { video, support_cards } = data.hierarchy;
  const scenes = video.children.scenes;

  /** Switching branch clears the other branch's selection entirely. */
  function selectBranch(next: Branch) {
    setBranch(next);
    setSelected(next === 'SCENES' ? (scenes[0]?.scene_id ?? null) : (support_cards[0]?.support_card_id ?? null));
  }

  const scene = branch === 'SCENES' ? scenes.find((s) => s.scene_id === selected) ?? null : null;
  const card = branch === 'CARDS' ? support_cards.find((c) => c.support_card_id === selected) ?? null : null;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Orientation"
        icon={<PlayCircle className="h-3.5 w-3.5" />}
        title="Orientation"
        description="The orientation video's scenes and the support cards that sit beside it."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add {branch === 'SCENES' ? 'Scene' : 'Support Card'}
          </button>
        }
      />

      <HealthIssues health={video.content_health} />

      <div className="flex flex-wrap items-center gap-1 border-b border-muted-gray/70">
        {(
          [
            ['SCENES', `${video.label} · ${scenes.length} scenes`],
            ['CARDS', `Support Cards · ${support_cards.length}`],
          ] as [Branch, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => selectBranch(id)}
            className={cn(
              'rounded-t-lg px-3 py-2 text-sm font-semibold',
              branch === id ? 'bg-white text-focus-navy shadow-[inset_0_-2px_0_0_var(--lime)]' : 'text-slate-blue hover:text-ink',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        <section className="sheet overflow-hidden self-start">
          <CardHeader
            icon={branch === 'SCENES' ? <PlayCircle className="h-4 w-4" /> : <LayoutGrid className="h-4 w-4" />}
            title={branch === 'SCENES' ? 'Scenes' : 'Support Cards'}
            action={branch === 'SCENES' ? <HealthBadge health={video.content_health} /> : undefined}
          />
          <ol>
            {branch === 'SCENES'
              ? scenes.map((s) => {
                  const active = s.scene_id === selected;
                  return (
                    <li key={s.scene_id}>
                      <button
                        onClick={() => setSelected(s.scene_id)}
                        className={cn(
                          'flex w-full items-center gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                          active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                        )}
                      >
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/15 font-mono text-2xs font-bold">
                          <span className={active ? 'text-white' : 'text-focus-navy'}>{s.scene_no}</span>
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={cn('block truncate text-sm', active ? 'text-white' : 'text-ink')}>
                            {s.scene_title}
                          </span>
                          <span className={cn('mt-0.5 block text-2xs', active ? 'text-white/70' : 'text-slate-blue')}>
                            {s.duration_sec}s
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })
              : support_cards.map((c) => {
                  const active = c.support_card_id === selected;
                  return (
                    <li key={c.support_card_id}>
                      <button
                        onClick={() => setSelected(c.support_card_id)}
                        className={cn(
                          'flex w-full items-center gap-3 border-b border-muted-gray/50 px-4 py-3 text-left last:border-0',
                          active ? 'bg-focus-navy text-white' : 'hover:bg-reading-surface',
                        )}
                      >
                        <span className={cn('min-w-0 flex-1 truncate text-sm', active ? 'text-white' : 'text-ink')}>
                          {c.card_title}
                        </span>
                      </button>
                    </li>
                  );
                })}
            {branch === 'CARDS' && support_cards.length === 0 && (
              <li className="px-5 py-6 text-center text-sm text-slate-blue">No support cards.</li>
            )}
          </ol>
        </section>

        <div className="min-w-0 space-y-4">
          {scene && (
            <section className="sheet overflow-hidden">
              <CardHeader
                icon={<PlayCircle className="h-4 w-4" />}
                title={`Scene ${scene.scene_no} · ${scene.scene_title}`}
                action={
                  <span className="flex items-center gap-2">
                    <span className="flex items-center gap-1 text-2xs text-slate-blue">
                      <Clock className="h-3 w-3" /> {scene.duration_sec}s
                    </span>
                    <StatusPill status={scene.status} />
                  </span>
                }
              />
              <div className="px-5 py-4">
                <Meta label="Narration" value={scene.narration_text} />
                <Meta label="Visual action" value={scene.visual_action} />
                {scene.on_screen_text && <Meta label="On-screen text" value={scene.on_screen_text} />}
                {scene.direction && <Meta label="Direction" value={scene.direction} />}
              </div>
            </section>
          )}

          {card && (
            <section className="sheet overflow-hidden">
              <CardHeader
                icon={<LayoutGrid className="h-4 w-4" />}
                title={card.card_title}
                action={<StatusPill status={card.status} />}
              />
              <div className="px-5 py-4">
                <Meta label="Visual" value={card.visual_content} />
                <Meta label="Narration / text" value={card.narration_or_text} />
                <Meta label="Restriction" value={card.restriction || '—'} />
                <Meta label="Version" value={card.version} />
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

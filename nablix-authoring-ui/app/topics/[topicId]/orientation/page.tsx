'use client';

import { useEffect, useState } from 'react';
import { PlayCircle, Plus, Clock, Layers, AlertTriangle } from 'lucide-react';
import { useContent } from '@/lib/workspace-context';
import { CardHeader } from '@/components/nablix/GlassCard';
import { SectionHeader, SectionLoading, MoveControls } from '@/components/nablix/SectionHeader';
import { StatusPill } from '@/components/nablix/StatusPill';
import { moveItem } from '@/lib/utils';
import type { OrientationScene } from '@/lib/api/contracts';

function secs(n: number) {
  const m = Math.floor(n / 60);
  const s = n % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function OrientationPage() {
  const c = useContent();
  const [scenes, setScenes] = useState<OrientationScene[]>([]);
  useEffect(() => {
    if (c) setScenes(c.orientation_video.scenes);
  }, [c]);
  if (!c) return <SectionLoading />;
  const v = c.orientation_video;
  const sceneTotal = scenes.reduce((a, s) => a + s.duration_sec, 0);
  const mismatch = Math.abs(sceneTotal - v.duration_sec) > 3;

  return (
    <div className="lg-anim-rise space-y-4 p-5">
      <SectionHeader
        eyebrow="Topic · Orientation"
        icon={<PlayCircle className="h-3.5 w-3.5" />}
        title="Orientation Content"
        description="The Phase 1 video that introduces the idea, its scenes, and any support cards."
        action={
          <button className="btn btn-primary">
            <Plus className="h-4 w-4" /> Add Scene
          </button>
        }
      />

      {/* Video */}
      <section className="sheet">
        <CardHeader
          icon={<PlayCircle className="h-4 w-4" />}
          title="Orientation Video"
          action={<StatusPill status={v.status} />}
        />
        <div className="flex flex-wrap items-center gap-4 px-5 py-3">
          <div className="flex h-16 w-28 items-center justify-center rounded-lg bg-focus-navy/90 text-white/80">
            <PlayCircle className="h-7 w-7" />
          </div>
          <div>
            <div className="font-display text-base font-bold text-focus-navy">{v.video_title}</div>
            <div className="mt-1 flex items-center gap-3 text-2xs font-semibold text-slate-blue">
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" /> {secs(v.duration_sec)} total
              </span>
              <span className="font-mono uppercase">PHASE_1_ORIENTATION</span>
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-2xs font-semibold uppercase tracking-wide text-slate-blue">Scenes total</div>
            <div className={`font-mono text-sm font-bold ${mismatch ? 'text-action-orange' : 'text-focus-navy'}`}>
              {secs(sceneTotal)} / {secs(v.duration_sec)}
            </div>
          </div>
        </div>
        {mismatch && (
          <div className="mx-5 mb-3 flex items-center gap-2 rounded-lg bg-highlight-amber/12 px-3 py-2 text-xs font-semibold text-action-orange">
            <AlertTriangle className="h-4 w-4" /> Scene durations differ from the video length.
          </div>
        )}
      </section>

      {/* Scenes */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Layers className="h-4 w-4" />} title={`Scenes · ${scenes.length}`} />
        <ol>
          {scenes.map((s, i) => (
            <li key={s.scene_no} className="flex gap-3 border-b border-muted-gray/50 px-4 py-3 last:border-0">
              <div className="flex flex-col items-center gap-1 pt-0.5">
                <MoveControls
                  onUp={() => setScenes((x) => moveItem(x, i, -1))}
                  onDown={() => setScenes((x) => moveItem(x, i, 1))}
                  canUp={i > 0}
                  canDown={i < scenes.length - 1}
                />
                <span className="font-mono text-2xs font-bold text-slate-blue">{i + 1}</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h4 className="font-semibold text-focus-navy">{s.scene_title}</h4>
                  <span className="font-mono text-2xs text-slate-blue">{secs(s.duration_sec)}</span>
                </div>
                <dl className="mt-1.5 grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  <div>
                    <dt className="text-2xs font-bold uppercase tracking-wide text-slate-blue/80">Visual</dt>
                    <dd className="text-xs text-ink/85">{s.visual_action}</dd>
                  </div>
                  <div>
                    <dt className="text-2xs font-bold uppercase tracking-wide text-slate-blue/80">Narration</dt>
                    <dd className="text-xs text-ink/85">{s.narration_text}</dd>
                  </div>
                </dl>
                {s.on_screen_text && (
                  <div className="mt-1.5 inline-block rounded-md bg-focus-navy/90 px-2 py-1 font-mono text-2xs text-white">
                    {s.on_screen_text}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Support cards */}
      <section className="sheet overflow-hidden">
        <CardHeader icon={<Layers className="h-4 w-4" />} title={`Support Cards · ${c.support_cards.length}`} />
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          {c.support_cards.map((card) => (
            <div key={card.support_card_id} className="rounded-lg border border-muted-gray/70 bg-reading-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-focus-navy">{card.card_title}</h4>
                <StatusPill status={card.status} />
              </div>
              <div className="mt-2 rounded-md bg-white px-3 py-2 text-center font-mono text-sm text-focus-navy ring-1 ring-inset ring-muted-gray/70">
                {card.visual_content}
              </div>
              <p className="mt-2 text-xs text-slate-blue">{card.narration_or_text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

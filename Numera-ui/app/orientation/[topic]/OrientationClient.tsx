'use client';

/**
 * Concept Orientation — a short piece of content that opens a topic before the
 * workbook. The tutor can open with one of three modes (Manjusha's ask):
 *   video → poster + simulated playback
 *   image → a single concept picture with a caption
 *   micro → a "micro-content" card of illustrated key points
 * plus the shared UI states:
 *   loading → skeleton shimmer while metadata loads
 *   empty   → topic has no orientation content yet
 *   error   → load failed, with retry  (force via ?fail=1)
 * Finishing marks the orientation phase complete and continues to the workbook.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ChevronLeft, Compass, Play, Pause, RotateCw, ArrowRight, Check, Film,
  Image as ImageIcon, Sparkles, AlertTriangle,
} from 'lucide-react';
import { getTopic } from '@/lib/curriculum';
import { useFlowNav } from '@/lib/useFlowNav';
import { orientationFor, type OrientationMedia } from '@/lib/demoContent';
import { Skeleton } from '@/components/PageShell';
import ConceptArt from '@/components/ConceptArt';

type Status = 'loading' | 'ready' | 'empty' | 'error';

/** Mock metadata fetch — resolves to the topic's media, or fails on ?fail=1. */
function fetchOrientation(topicId: string): Promise<OrientationMedia | null> {
  return new Promise((resolve, reject) => {
    const fail = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('fail');
    setTimeout(() => {
      if (fail) reject(new Error('network'));
      else resolve(orientationFor(topicId));
    }, 1100);
  });
}

const KIND_LABEL: Record<OrientationMedia['kind'], { icon: typeof Film; text: string }> = {
  video: { icon: Film, text: 'Concept video' },
  image: { icon: ImageIcon, text: 'Concept picture' },
  micro: { icon: Sparkles, text: 'Key points' },
};

export default function OrientationClient({ topicId }: { topicId: string }) {
  const { goStage } = useFlowNav();
  const topic = getTopic(topicId);

  const [status, setStatus] = useState<Status>('loading');
  const [media, setMedia] = useState<OrientationMedia | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0); // 0–100, simulated video playback
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  if (!topic) notFound();

  const load = useCallback(() => {
    setStatus('loading');
    setPlaying(false);
    setProgress(0);
    fetchOrientation(topicId)
      .then((m) => {
        setMedia(m);
        setStatus(m ? 'ready' : 'empty');
      })
      .catch(() => setStatus('error'));
  }, [topicId]);

  useEffect(() => { load(); }, [load]);

  // Simulated playback — only for the video mode.
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setProgress((p) => {
        if (p >= 100) { setPlaying(false); return 100; }
        return p + 2;
      });
    }, 120);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [playing]);

  // Orientation done → into the live Guided Learning lesson for this topic.
  const finish = () => goStage('guided', topicId);

  return (
    <main className="flex-1 min-w-0 flex flex-col bg-white" aria-label="Concept orientation">
      <header className="flex items-center justify-between gap-4 px-8 py-6 border-b border-muted-gray flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-lg bg-focus-navy text-white flex items-center justify-center">
            <Compass size={17} strokeWidth={1.8} />
          </span>
          <div>
            <div className="text-[10px] tracking-widest uppercase text-slate-blue">
              Orientation{media ? ` · ${KIND_LABEL[media.kind].text.toLowerCase()}` : ''}
            </div>
            <h1 className="text-[16px] font-semibold text-ink leading-tight">{topic.title}</h1>
          </div>
        </div>
        <Link href={`/workbook/${topic.id}`} className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors">
          <ChevronLeft size={15} strokeWidth={1.8} /> Topic
        </Link>
      </header>

      <div className="flex-1 overflow-y-auto flex items-center justify-center p-8">
        <div className="w-[640px] max-w-full">
          {/* ── Loading: skeleton shimmer ─────────────────────────────── */}
          {status === 'loading' && (
            <div aria-busy="true">
              <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-muted-gray">
                <Skeleton className="absolute inset-0 rounded-none" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <Skeleton className="w-14 h-14 rounded-full bg-muted-gray" />
                </div>
              </div>
              <Skeleton className="w-3/4 h-4 mt-5" />
              <Skeleton className="w-2/3 h-4 mt-2.5" />
            </div>
          )}

          {/* ── Ready: render by media kind ───────────────────────────── */}
          {status === 'ready' && media && (
            <div>
              {media.kind === 'video' && (
                <VideoPlayer media={media} playing={playing} progress={progress} onToggle={() => setPlaying((p) => !p)} />
              )}
              {media.kind === 'image' && <ImageCard media={media} />}
              {media.kind === 'micro' && <MicroCard media={media} />}

              <p className="text-[13.5px] text-[#5a5a5a] leading-relaxed mt-5">{media.summary}</p>

              {media.kind === 'video' && progress >= 100 && (
                <div className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-semibold text-ink">
                  <Check size={14} strokeWidth={2.4} /> Watched
                </div>
              )}
            </div>
          )}

          {/* ── Empty: no content for this topic yet ──────────────────── */}
          {status === 'empty' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-muted-gray bg-reading-surface aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-white text-slate-blue flex items-center justify-center mb-3">
                <Film size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Orientation coming soon</h3>
              <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">
                We haven&apos;t prepared the concept intro for {topic.title} yet — you can head straight into the guided lesson.
              </p>
            </div>
          )}

          {/* ── Error: load failed ────────────────────────────────────── */}
          {status === 'error' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-muted-gray bg-white aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-reading-surface text-slate-blue flex items-center justify-center mb-3">
                <AlertTriangle size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Couldn&apos;t load the content</h3>
              <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">
                Something went wrong reaching the lesson server. Check your connection and try again.
              </p>
              <button
                onClick={load}
                className="mt-5 inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
              >
                <RotateCw size={14} strokeWidth={1.9} /> Try again
              </button>
            </div>
          )}

          {/* ── Footer actions (hidden while loading) ─────────────────── */}
          {status !== 'loading' && (
            <div className="flex items-center justify-between mt-7">
              <button
                onClick={finish}
                className="text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors"
              >
                Skip
              </button>
              <button
                onClick={finish}
                disabled={status === 'error'}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 disabled:opacity-30 transition-opacity"
              >
                Continue to guided lesson <ArrowRight size={16} strokeWidth={2} />
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/** Video mode — poster + simulated playback (no real file wired yet). */
function VideoPlayer({
  media, playing, progress, onToggle,
}: { media: Extract<OrientationMedia, { kind: 'video' }>; playing: boolean; progress: number; onToggle: () => void }) {
  return (
    <div
      className="relative aspect-video w-full overflow-hidden rounded-xl border border-focus-navy bg-focus-navy"
      style={{ backgroundImage: 'radial-gradient(circle at 30% 25%, #1B2A4A, #0F1830 70%)' }}
    >
      <div
        className="absolute inset-0 opacity-[0.12]"
        style={{
          backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
          backgroundSize: '34px 34px',
        }}
      />
      <div className="absolute top-4 left-4 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[10px] tracking-widest uppercase text-white/80">
        <Film size={12} strokeWidth={1.8} /> Concept video
      </div>
      <div className="absolute top-4 right-4 rounded-full bg-white/10 px-2.5 py-1 text-[11px] text-white/80">{media.duration}</div>
      <button onClick={onToggle} aria-label={playing ? 'Pause' : 'Play'} className="absolute inset-0 flex items-center justify-center group">
        <span className="w-16 h-16 rounded-full bg-white text-ink flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
          {playing ? <Pause size={26} strokeWidth={2} /> : <Play size={26} strokeWidth={2} className="ml-1" />}
        </span>
      </button>
      <div className="absolute bottom-0 inset-x-0 px-4 pb-3.5 pt-8 bg-gradient-to-t from-black/70 to-transparent">
        <div className="text-[14px] font-semibold text-white mb-2">{media.title}</div>
        <div className="h-1 w-full rounded-full bg-white/20 overflow-hidden">
          <div className="h-full rounded-full bg-white transition-[width] duration-150" style={{ width: `${progress}%` }} />
        </div>
      </div>
    </div>
  );
}

/** Image mode — a single concept picture with a caption. */
function ImageCard({ media }: { media: Extract<OrientationMedia, { kind: 'image' }> }) {
  return (
    <figure>
      <div className="relative rounded-xl border border-muted-gray bg-reading-surface flex items-center justify-center p-8 aspect-video">
        <div className="absolute top-4 left-4 inline-flex items-center gap-1.5 rounded-full bg-white border border-muted-gray px-2.5 py-1 text-[10px] tracking-widest uppercase text-slate-blue">
          <ImageIcon size={12} strokeWidth={1.8} /> Concept picture
        </div>
        <ConceptArt name={media.art} className="w-full max-w-[440px] h-auto" />
      </div>
      <figcaption className="text-[13px] font-medium text-ink mt-3">{media.caption}</figcaption>
    </figure>
  );
}

/** Micro-content mode — illustration + a few key points. */
function MicroCard({ media }: { media: Extract<OrientationMedia, { kind: 'micro' }> }) {
  return (
    <div className="rounded-xl border border-focus-navy/20 bg-reading-surface overflow-hidden">
      <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-muted-gray bg-white text-[10px] tracking-widest uppercase text-slate-blue">
        <Sparkles size={12} strokeWidth={1.8} /> Key points · {media.title}
      </div>
      <div className="flex flex-col sm:flex-row gap-6 p-6">
        <div className="sm:w-44 flex-shrink-0 rounded-lg bg-white border border-muted-gray p-3 flex items-center">
          <ConceptArt name={media.art} className="w-full h-auto" />
        </div>
        <ul className="flex-1 flex flex-col gap-3 justify-center">
          {media.points.map((pt, i) => (
            <li key={i} className="flex items-start gap-3 text-[13.5px] text-ink leading-snug">
              <span className="mt-0.5 flex-shrink-0 w-5 h-5 rounded-full bg-focus-navy text-white text-[11px] font-semibold flex items-center justify-center">
                {i + 1}
              </span>
              {pt}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

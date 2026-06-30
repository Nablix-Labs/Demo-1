'use client';

/**
 * Concept Orientation — a single short concept VIDEO that opens a topic before
 * the workbook. The real video stream is backend-served; here the player is a
 * placeholder driving the full set of UI states:
 *   loading → skeleton shimmer while metadata loads
 *   ready   → poster + simulated playback (no real file wired yet)
 *   empty   → topic has no orientation video yet
 *   error   → load failed, with retry  (force via ?fail=1)
 * Finishing marks the orientation phase complete and continues to the workbook.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ChevronLeft, Compass, Play, Pause, RotateCw, ArrowRight, Check, Film, AlertTriangle,
} from 'lucide-react';
import { getTopic } from '@/lib/curriculum';
import { useFlowNav } from '@/lib/useFlowNav';
import { Skeleton } from '@/components/PageShell';
import { cn } from '@/lib/cn';

interface VideoMeta { title: string; duration: string; summary: string }

// Per-topic orientation video. `statistics` is intentionally missing → empty.
const VIDEOS: Record<string, VideoMeta> = {
  algebra: { title: 'Solving linear equations', duration: '4:12', summary: 'Keep the equation balanced and undo each operation one step at a time to find x.' },
  number: { title: 'Working with fractions', duration: '3:48', summary: 'Fractions are parts of a whole — match the denominators before you add or subtract.' },
  geometry: { title: 'Angle rules', duration: '4:30', summary: 'Angles measure turn; the rules on lines and in shapes let you find the missing one.' },
};

type Status = 'loading' | 'ready' | 'empty' | 'error';

/** Mock metadata fetch — resolves to the topic's video, or fails on ?fail=1. */
function fetchOrientationVideo(topicId: string): Promise<VideoMeta | null> {
  return new Promise((resolve, reject) => {
    const fail = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('fail');
    setTimeout(() => {
      if (fail) reject(new Error('network'));
      else resolve(VIDEOS[topicId] ?? null);
    }, 1100);
  });
}

export default function OrientationClient({ topicId }: { topicId: string }) {
  const { goStage } = useFlowNav();
  const topic = getTopic(topicId);

  const [status, setStatus] = useState<Status>('loading');
  const [video, setVideo] = useState<VideoMeta | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0); // 0–100, simulated playback
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  if (!topic) notFound();

  const load = useCallback(() => {
    setStatus('loading');
    setPlaying(false);
    setProgress(0);
    fetchOrientationVideo(topicId)
      .then((meta) => {
        setVideo(meta);
        setStatus(meta ? 'ready' : 'empty');
      })
      .catch(() => setStatus('error'));
  }, [topicId]);

  useEffect(() => { load(); }, [load]);

  // Simulated playback — advance the bar while "playing".
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

  const watched = progress >= 100;

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
            <div className="text-[10px] tracking-widest uppercase text-slate-blue">Orientation · concept video</div>
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
              <Skeleton className="w-1/3 h-4 mt-2.5" />
            </div>
          )}

          {/* ── Ready: video poster + simulated playback ──────────────── */}
          {status === 'ready' && video && (
            <div>
              <div
                className="relative aspect-video w-full overflow-hidden rounded-xl border border-focus-navy bg-focus-navy"
                style={{
                  backgroundImage: 'radial-gradient(circle at 30% 25%, #1B2A4A, #0F1830 70%)',
                }}
              >
                {/* faux frame grid */}
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
                <div className="absolute top-4 right-4 rounded-full bg-white/10 px-2.5 py-1 text-[11px] text-white/80">
                  {video.duration}
                </div>

                {/* play / pause */}
                <button
                  onClick={() => setPlaying((p) => !p)}
                  aria-label={playing ? 'Pause' : 'Play'}
                  className="absolute inset-0 flex items-center justify-center group"
                >
                  <span className="w-16 h-16 rounded-full bg-white text-ink flex items-center justify-center shadow-lg group-hover:scale-105 transition-transform">
                    {playing ? <Pause size={26} strokeWidth={2} /> : <Play size={26} strokeWidth={2} className="ml-1" />}
                  </span>
                </button>

                {/* title + progress */}
                <div className="absolute bottom-0 inset-x-0 px-4 pb-3.5 pt-8 bg-gradient-to-t from-black/70 to-transparent">
                  <div className="text-[14px] font-semibold text-white mb-2">{video.title}</div>
                  <div className="h-1 w-full rounded-full bg-white/20 overflow-hidden">
                    <div className="h-full rounded-full bg-white transition-[width] duration-150" style={{ width: `${progress}%` }} />
                  </div>
                </div>
              </div>

              <p className="text-[13.5px] text-[#5a5a5a] leading-relaxed mt-5">{video.summary}</p>

              {watched && (
                <div className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-semibold text-ink">
                  <Check size={14} strokeWidth={2.4} /> Watched
                </div>
              )}
            </div>
          )}

          {/* ── Empty: no video for this topic yet ────────────────────── */}
          {status === 'empty' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-muted-gray bg-reading-surface aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-white text-slate-blue flex items-center justify-center mb-3">
                <Film size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Orientation video coming soon</h3>
              <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">
                We haven&apos;t recorded the concept video for {topic.title} yet — you can head straight into the guided lesson.
              </p>
            </div>
          )}

          {/* ── Error: load failed ────────────────────────────────────── */}
          {status === 'error' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-muted-gray bg-white aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-reading-surface text-slate-blue flex items-center justify-center mb-3">
                <AlertTriangle size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Couldn&apos;t load the video</h3>
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
                Skip video
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

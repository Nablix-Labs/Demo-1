'use client';

/**
 * Concept Orientation — a short piece of content that opens a topic before the
 * workbook. The tutor can open with one of three modes (Manjusha's ask):
 *   video → the real MP4 when the topic has one, else poster + simulated playback
 *   image → a single concept picture with a caption
 *   micro → a "micro-content" card of illustrated key points
 * plus the shared UI states:
 *   loading → skeleton shimmer while metadata loads
 *   empty   → topic has no orientation content yet
 *   error   → load failed, with retry  (force via ?fail=1)
 *
 * The phase has TWO steps (Manjusha, 2026-07-26). Once the content is finished —
 * for a video, the moment playback ends — the tutor poses one concept question
 * and works it through on the canvas, still inside Phase 1. **Only the tutor
 * writes here**: the student watches, then explains it back in Teacher Mode
 * next. (Phase 2 lets both write; Phase 3 is the student alone.)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { notFound } from 'next/navigation';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import {
  ChevronLeft, Compass, Play, Pause, RotateCw, ArrowRight, Check, Film,
  Image as ImageIcon, Sparkles, AlertTriangle, PenLine,
} from 'lucide-react';
import { getTopic } from '@/lib/curriculum';
import { useFlowNav } from '@/lib/useFlowNav';
import {
  orientationFor,
  orientationCheckFor,
  orientationVideoForTopicCode,
  type OrientationMedia,
} from '@/lib/demoContent';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import {
  completeOrientation,
  orientationSequence,
  sessionTopicCode,
  startOrientation,
  studentId,
  type SchemaOrientationItem,
  type SchemaWorkedExample,
} from '@/lib/api';
import { Skeleton } from '@/components/PageShell';
import ConceptArt from '@/components/ConceptArt';

// react-konva is client-only (no SSR), same as everywhere else the canvas mounts.
const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

type Status = 'loading' | 'ready' | 'empty' | 'error';
/** Phase 1 runs content → concept check (tutor writes) → on to Teacher Mode. */
type Step = 'content' | 'check';

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

const apiEnabled = Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

/**
 * With a live session the Student Model owns this phase — it says what to play
 * and in what order. Without one (mock mode, or the session hasn't started)
 * fall back to the local demo content so the flow still runs standalone.
 */
export default function OrientationClient({ topicId }: { topicId: string }) {
  const sessionId = useNumeraStore((s) => s.sessionId);
  return apiEnabled && sessionId
    ? <BackendOrientation topicId={topicId} sessionId={sessionId} />
    : <MockOrientation topicId={topicId} />;
}

function MockOrientation({ topicId }: { topicId: string }) {
  const { goStage } = useFlowNav();
  const topic = getTopic(topicId);

  const [status, setStatus] = useState<Status>('loading');
  const [media, setMedia] = useState<OrientationMedia | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0); // 0–100, simulated video playback
  const [step, setStep] = useState<Step>('content');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  // The concept check that follows the content, and the tutor-layer actions that
  // put the tutor's working on its canvas.
  const check = orientationCheckFor(topicId);
  const applyCanvasDraw = useNumeraStore((s) => s.applyCanvasDraw);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  if (!topic) notFound();

  const load = useCallback(() => {
    setStatus('loading');
    setPlaying(false);
    setProgress(0);
    setStep('content');
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

  // "Once the video is over we display the canvas in the same phase" — as soon as
  // playback ends, move to the concept check rather than waiting for a tap.
  useEffect(() => {
    if (media?.kind === 'video' && progress >= 100 && check) setStep('check');
  }, [media, progress, check]);

  // Entering the check: hand the tutor's working to the shared tutor layer, which
  // reveals it stroke by stroke. Cleared on the way out — the tutor layer is
  // global, so Phase 1's marks must not follow the student into guided practice.
  //
  // Held back by a beat so the question and the blank sheet settle first: writing
  // that starts mid-transition reads as a page glitch rather than someone picking
  // up a pen.
  useEffect(() => {
    if (step !== 'check' || !check) return;
    const start = setTimeout(() => {
      applyCanvasDraw({
        author: 'tutor',
        mode: 'replace',
        actionId: `orientation-${topicId}`,
        elements: check.elements,
      });
    }, 550);
    return () => { clearTimeout(start); clearTutorMarks(); };
  }, [step, check, topicId, applyCanvasDraw, clearTutorMarks]);

  // Orientation done → Teacher Mode (teach the concept back) for this topic.
  const finish = () => goStage('teach', topicId);

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
        <div className={step === 'check' ? 'w-[900px] max-w-full' : 'w-[640px] max-w-full'}>
          {/* ── Step 2: concept check — the tutor writes, the student watches ── */}
          {step === 'check' && check && (
            <div className="lg-anim-rise">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 w-8 h-8 rounded-lg bg-focus-navy text-white flex items-center justify-center flex-shrink-0">
                  <PenLine size={16} strokeWidth={1.8} />
                </span>
                <div>
                  <div className="text-[10px] tracking-widest uppercase text-slate-blue">
                    Concept check · Numera is writing
                  </div>
                  <p className="text-[16px] font-semibold text-ink leading-snug mt-0.5 max-w-[64ch]">
                    {check.question}
                  </p>
                </div>
              </div>

              {/* Tutor's canvas. tutorOnly: only the tutor writes in this phase,
                  and the student's ink from other phases stays off it — they
                  explain it back in Teacher Mode next. */}
              <div
                className="relative mt-5 h-[420px] rounded-xl border border-muted-gray bg-white overflow-hidden"
                style={{
                  backgroundImage:
                    'linear-gradient(#EEF0F3 1px, transparent 1px), linear-gradient(90deg, #EEF0F3 1px, transparent 1px)',
                  backgroundSize: '28px 28px',
                }}
              >
                <DrawingCanvas tutorOnly />
              </div>

              <p className="text-[12px] text-slate-blue mt-3">
                Watch how Numera sets it up — you&apos;ll explain it back in your own words next.
              </p>
            </div>
          )}

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

          {/* ── Step 1 · Ready: render by media kind ──────────────────── */}
          {step === 'content' && status === 'ready' && media && (
            <div>
              {media.kind === 'video' && (
                media.src
                  ? <VideoFile media={media} onEnded={() => setProgress(100)} />
                  : <VideoPlayer media={media} playing={playing} progress={progress} onToggle={() => setPlaying((p) => !p)} />
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
                We haven&apos;t prepared the concept intro for {topic.title} yet — you can head straight into teaching it back.
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

          {/* ── Footer actions (hidden while loading) ─────────────────────
              On the content step, a topic that has a concept check moves to it
              rather than leaving the phase. A video jumps there by itself when it
              ends; this button covers the picture / key-points modes and anyone
              who doesn't watch to the end. */}
          {status !== 'loading' && (
            <div className="flex items-center justify-between mt-7">
              <button
                onClick={finish}
                className="text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors"
              >
                Skip
              </button>
              {step === 'content' && status === 'ready' && check ? (
                <button
                  onClick={() => setStep('check')}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity"
                >
                  Continue <ArrowRight size={16} strokeWidth={2} />
                </button>
              ) : (
                <button
                  onClick={finish}
                  disabled={status === 'error'}
                  className="inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 disabled:opacity-30 transition-opacity"
                >
                  Now teach it back <ArrowRight size={16} strokeWidth={2} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/**
 * Real MP4 playback. Native controls rather than a custom transport: the file is
 * ~160 MB and streamed over range requests, so the browser's own buffering and
 * scrub UI behave far better than anything reimplemented here.
 *
 * `onEnded` is what advances the phase — it drives the same `progress === 100`
 * the simulated player used, so the concept-check step is reached identically
 * whether the video is real or mocked.
 *
 * No crossOrigin attribute: the blob container sends no CORS headers, and
 * setting it would turn a working load into a failed one.
 */
function VideoFile({
  media, onEnded,
}: { media: Extract<OrientationMedia, { kind: 'video' }>; onEnded: () => void }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="flex flex-col items-center justify-center text-center rounded-xl border border-muted-gray bg-reading-surface aspect-video w-full">
        <span className="w-12 h-12 rounded-xl border border-muted-gray bg-white text-slate-blue flex items-center justify-center mb-3">
          <Film size={20} strokeWidth={1.8} />
        </span>
        <h3 className="text-[15px] font-semibold text-ink">Couldn&apos;t play the video</h3>
        <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">
          The lesson video didn&apos;t load. You can carry on without it — Numera will still
          walk you through the idea.
        </p>
      </div>
    );
  }

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-focus-navy bg-black">
      <video
        src={media.src}
        controls
        playsInline
        preload="metadata"
        onEnded={onEnded}
        onError={() => setFailed(true)}
        className="w-full h-full"
      />
    </div>
  );
}

/** Poster + simulated playback, for a video topic with no file yet. */
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

// ─── Backend-driven orientation ──────────────────────────────────────────────

/**
 * Phase 1 as the Student Model defines it: an ordered delivery sequence of
 * concept videos and worked examples, followed by completing the phase.
 *
 * Completing matters. /orientation/complete is what moves the journey on to
 * Guided Practice — leaving the screen without it means the Student Model still
 * has the student in PHASE_1_ORIENTATION, and they land back here next session.
 */
function BackendOrientation({ topicId, sessionId }: { topicId: string; sessionId: string }) {
  const topic = getTopic(topicId);
  const backendSession = useNumeraStore((s) => s.backendSession);
  const setBackendSession = useNumeraStore((s) => s.setBackendSession);
  const setCurrentPhase = useNumeraStore((s) => s.setCurrentPhase);

  const [status, setStatus] = useState<Status>('loading');
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guards React 18's double-invoke from opening orientation twice.
  const requested = useRef(false);

  const items = orientationSequence(backendSession);
  const topicCode = sessionTopicCode(backendSession);

  // `/orientation` is a FOCUS_ROUTE too, so AuthGate never mounts here and
  // nothing else rehydrates the auth store — see the matching note in
  // DiagnosticClient. Without this a direct load sends the anonymous bearer.
  useEffect(() => { void useAuthStore.persist.rehydrate(); }, []);

  const load = useCallback(async () => {
    if (requested.current) return;
    requested.current = true;
    setStatus('loading');
    setError(null);
    try {
      const rec = await startOrientation(sessionId, studentId());
      setBackendSession(rec);
      setStatus(orientationSequence(rec).length > 0 ? 'ready' : 'empty');
    } catch {
      setError("Couldn't load this topic's orientation.");
      setStatus('error');
      // NOT cleared here on purpose — an auto-retry on failure is how the
      // diagnostic screen once fired thousands of requests. Only the retry
      // button below clears it.
    }
  }, [sessionId, setBackendSession]);

  // Always call /orientation/start once per session — even though
  // /diagnostic/complete already returned an orientation_bundle.
  //
  // That bundle is only the content preview. `start` is what moves the Student
  // Model's phase_1_orientation to IN_PROGRESS, and /orientation/complete
  // rejects with 409 ("Orientation must be started before it can be completed")
  // without it. Skipping the call because the content was already on hand left
  // the student stuck on this screen with no way forward.
  //
  // Keyed on the session only: re-running on `items` would re-request every
  // time the record updates. `requested` guards the double-invoke.
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const finish = async () => {
    setFinishing(true);
    setError(null);
    try {
      const rec = await completeOrientation(sessionId, studentId());
      setBackendSession(rec);
      // usePhaseRouting follows this to the next phase's screen.
      useNumeraStore.setState({
        activeQuestionId: rec.question_id,
        questionText: rec.current_question?.trim() ?? '',
      });
      setCurrentPhase(rec.current_phase);
    } catch {
      setError("Couldn't mark this as done. Please try again.");
      setFinishing(false);
    }
  };

  if (!topic) notFound();

  return (
    <main className="flex-1 min-w-0 flex flex-col bg-white" aria-label="Concept orientation">
      <header className="flex items-center justify-between gap-4 px-8 py-6 border-b border-muted-gray flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-lg bg-focus-navy text-white flex items-center justify-center">
            <Compass size={17} strokeWidth={1.8} />
          </span>
          <div>
            <div className="text-[10px] tracking-widest uppercase text-slate-blue">Orientation</div>
            <h1 className="text-[16px] font-semibold text-ink leading-tight">{topic.title}</h1>
          </div>
        </div>
        <Link href={`/workbook/${topic.id}`} className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors">
          <ChevronLeft size={15} strokeWidth={1.8} /> Topic
        </Link>
      </header>

      <div className="flex-1 overflow-y-auto flex justify-center p-8">
        <div className="w-[760px] max-w-full">
          {status === 'loading' && (
            <div aria-busy="true">
              <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-muted-gray">
                <Skeleton className="absolute inset-0 rounded-none" />
              </div>
              <Skeleton className="w-3/4 h-4 mt-5" />
              <Skeleton className="w-2/3 h-4 mt-2.5" />
            </div>
          )}

          {status === 'error' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-muted-gray bg-white aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-reading-surface text-slate-blue flex items-center justify-center mb-3">
                <AlertTriangle size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Couldn&apos;t load the content</h3>
              <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">{error}</p>
              <button
                onClick={() => { requested.current = false; void load(); }}
                className="mt-5 inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
              >
                <RotateCw size={14} strokeWidth={1.9} /> Try again
              </button>
            </div>
          )}

          {status === 'empty' && (
            <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-muted-gray bg-reading-surface aspect-video w-full">
              <span className="w-12 h-12 rounded-xl border border-muted-gray bg-white text-slate-blue flex items-center justify-center mb-3">
                <Film size={20} strokeWidth={1.8} />
              </span>
              <h3 className="text-[15px] font-semibold text-ink">Orientation coming soon</h3>
              <p className="text-[12.5px] text-slate-blue mt-1.5 max-w-sm leading-relaxed">
                There&apos;s no concept intro prepared for {topic.title} yet — you can head straight
                into teaching it back.
              </p>
            </div>
          )}

          {status === 'ready' && (
            <div className="flex flex-col gap-8">
              {items.map((item) => (
                <OrientationItem key={`${item.content_type}-${item.sequence_no}`} item={item} topicCode={topicCode} />
              ))}
            </div>
          )}

          {status !== 'loading' && (
            <div className="flex items-center justify-end gap-4 mt-8">
              {error && status !== 'error' && (
                <span className="text-[12.5px] text-action-orange mr-auto">{error}</span>
              )}
              <button
                onClick={() => void finish()}
                disabled={finishing}
                className="inline-flex items-center justify-center gap-2 rounded-md bg-focus-navy text-white px-5 py-2.5 text-[13px] font-semibold hover:opacity-80 disabled:opacity-40 transition-opacity"
              >
                {finishing ? 'Saving…' : 'Now teach it back'} <ArrowRight size={16} strokeWidth={2} />
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

/** One entry in the Student Model's delivery sequence. */
function OrientationItem({
  item, topicCode,
}: { item: SchemaOrientationItem; topicCode: string | null }) {
  if (item.content_type === 'ORIENTATION_VIDEO' && item.video) {
    // The Student Model carries the video record but leaves asset_url null, so
    // the topic code resolves the uploaded file (see orientationVideoForTopicCode).
    const src = item.video.asset_url ?? orientationVideoForTopicCode(topicCode);
    return (
      <section>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2 inline-flex items-center gap-1.5">
          <Film size={12} strokeWidth={1.8} /> Concept video
        </div>
        <h2 className="text-[17px] font-semibold text-ink mb-3">{item.video.title}</h2>
        {src ? (
          <VideoFile media={{ kind: 'video', title: item.video.title, duration: '', summary: '', src }} onEnded={() => {}} />
        ) : (
          <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-muted-gray bg-reading-surface aspect-video w-full">
            <p className="text-[12.5px] text-slate-blue max-w-sm leading-relaxed">
              This video hasn&apos;t been uploaded yet. Read through the worked example below —
              it covers the same ground.
            </p>
          </div>
        )}
      </section>
    );
  }

  if (item.content_type === 'WORKED_EXAMPLE' && item.worked_example) {
    return <WorkedExampleCard example={item.worked_example} />;
  }
  return null;
}

/**
 * The tutor's worked example, step by step. `screen_content` is what goes on
 * screen and `narration_text` is what the tutor says about it — both are shown,
 * because a student reading alone still needs the explanation.
 */
function WorkedExampleCard({ example }: { example: SchemaWorkedExample }) {
  return (
    <section>
      <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2 inline-flex items-center gap-1.5">
        <PenLine size={12} strokeWidth={1.8} /> Worked example
      </div>
      <h2 className="text-[17px] font-semibold text-ink mb-4">{example.title}</h2>
      <ol className="flex flex-col gap-3">
        {[...example.steps].sort((a, b) => a.sequence_no - b.sequence_no).map((step) => (
          <li key={step.step_id} className="flex items-start gap-3 rounded-lg border border-muted-gray bg-reading-surface p-4">
            <span className="mt-0.5 flex-shrink-0 w-6 h-6 rounded-full bg-focus-navy text-white text-[11px] font-semibold flex items-center justify-center">
              {step.sequence_no}
            </span>
            <div className="min-w-0">
              {step.screen_content && (
                <div className="text-[16px] text-ink font-[Cambria_Math,Georgia,serif] leading-snug">
                  {step.screen_content}
                </div>
              )}
              {step.narration_text && (
                <p className="text-[13px] text-slate-blue leading-relaxed mt-1.5">{step.narration_text}</p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

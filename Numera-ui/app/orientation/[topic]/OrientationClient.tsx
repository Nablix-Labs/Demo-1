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

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';
import { beginSession, sessionStartError } from '@/hooks/useDemoTutor';
import { useAuthStore } from '@/store/useAuthStore';
import {
  completeOrientation,
  orientationSequence,
  requiredOrientationContent,
  type OrientationMessages,
  sessionTopicCode,
  startOrientation,
  studentId,
  type SchemaOrientationItem,
  type SchemaWorkedExample,
  type SchemaWorkedExampleStep,
} from '@/lib/api';
import { speakTutor, stopTutorSpeech } from '@/lib/tts';
import { cn } from '@/lib/cn';
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
 * The Student Model owns this phase — it says what to play and in what order.
 *
 * The demo content is ONLY for a build with no backend. This used to also fall
 * back to it whenever there was no local session, which is the state a returning
 * student is in on every fresh page load: the tutoring session lives in the
 * backend's memory and its id is not persisted. So a student routed here by
 * their journey was shown the hardcoded "x + 4 = 9" concept check — silently,
 * with no narration, and with no way to reach the real lesson (Manjusha,
 * 2026-07-28). Showing invented content in place of a failure is worse than
 * showing the failure.
 */
export default function OrientationClient({ topicId }: { topicId: string }) {
  if (!apiEnabled) return <MockOrientation topicId={topicId} />;
  return <BackendOrientation topicId={topicId} />;
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
        {/* Matches the backend branch below — the video and canvas are the
            content, so they get the width. */}
        <div className="w-[min(1180px,98vh)] max-w-full">
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
                  ? <VideoFile media={media} spoken={null} onEnded={() => setProgress(100)} />
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
  media, spoken, onEnded,
}: {
  media: Extract<OrientationMedia, { kind: 'video' }>;
  /** Backend-authored line for this stage; spoken and shown, never invented here. */
  spoken: string | null;
  onEnded: () => void;
}) {
  const [failed, setFailed] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Say the tutor's line before the video starts. Stopped on the way out so it
  // can't talk over the video or follow the student to the next screen.
  useEffect(() => {
    if (spoken) speakTutor(spoken);
    return () => stopTutorSpeech();
  }, [spoken]);

  // Try to start on arrival. Browsers block autoplay WITH SOUND unless the page
  // has user activation, and a lesson video muted is pointless — so when the
  // attempt is refused we simply leave the poster and controls up and let the
  // student press play. Never force it muted just to make autoplay succeed.
  useEffect(() => {
    videoRef.current?.play().catch(() => {/* blocked — the controls are there */});
  }, []);

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
    <>
      {spoken && <p className="text-[13.5px] text-ink leading-relaxed mb-3">{spoken}</p>}
    <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-focus-navy bg-black">
      <video
        ref={videoRef}
        src={media.src}
        controls
        playsInline
        preload="metadata"
        onEnded={onEnded}
        onError={() => setFailed(true)}
        className="w-full h-full"
      />
    </div>
    </>
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
function BackendOrientation({ topicId }: { topicId: string }) {
  const topic = getTopic(topicId);
  const sessionId = useNumeraStore((s) => s.sessionId);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const backendSession = useNumeraStore((s) => s.backendSession);
  const setBackendSession = useNumeraStore((s) => s.setBackendSession);
  const applyBackendPhase = useNumeraStore((s) => s.applyBackendPhase);

  const [status, setStatus] = useState<Status>('loading');
  // Position in the delivery sequence — the video, then the worked example.
  const [itemIndex, setItemIndex] = useState(0);
  // Ids of content the student has actually finished. Collected as each piece
  // completes rather than assumed from the bundle: /orientation/complete 409s on
  // anything missing and 422s on anything unknown, so guessing would fail.
  /**
   * The tutor's line for the current hand-off, shown and spoken.
   *
   * The backend authors all six of these (configs/phase1_tutor.yaml) and we were
   * only using two, so moving between the diagnostic, the video and the worked
   * example happened in silence — "there are no transition messages between the
   * phases" (Manjusha, 2026-07-28).
   */
  const [stageMessage, setStageMessage] = useState<string | null>(null);
  const [doneVideoIds, setDoneVideoIds] = useState<string[]>([]);
  const [doneExampleIds, setDoneExampleIds] = useState<string[]>([]);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guards React 18's double-invoke from opening orientation twice.
  const requested = useRef(false);

  const items = orientationSequence(backendSession);
  const topicCode = sessionTopicCode(backendSession);
  const required = requiredOrientationContent(backendSession);
  const messages = backendSession?.orientation_messages ?? null;
  // Continue stays disabled until every served video and worked example is done.
  const allComplete =
    required.videoIds.every((id) => doneVideoIds.includes(id)) &&
    required.workedExampleIds.every((id) => doneExampleIds.includes(id));

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
      // No local session — a returning student on a fresh load. Open one; the
      // backend always starts it in DIAGNOSTIC, and usePhaseRouting then moves
      // them to the phase it actually reports. (A true mid-journey resume needs
      // the backend change tracked as ask #3.)
      const active = sessionId ?? (await beginSession(activeConceptId, 'TEXT'))?.session_id;
      if (!active) {
        setError(sessionStartError() ?? "Couldn't reach the tutor to load this topic.");
        setStatus('error');
        return;
      }
      const rec = await startOrientation(active, studentId());
      setBackendSession(rec);
      setStatus(orientationSequence(rec).length > 0 ? 'ready' : 'empty');
    } catch {
      setError("Couldn't load this topic's orientation.");
      setStatus('error');
      // NOT cleared here on purpose — an auto-retry on failure is how the
      // diagnostic screen once fired thousands of requests. Only the retry
      // button below clears it.
    }
  }, [sessionId, activeConceptId, setBackendSession]);

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

  // Arriving from the diagnostic: greet before anything plays. Guarded so it
  // speaks once, not on every re-render of a ready screen.
  const greeted = useRef(false);
  useEffect(() => {
    if (status !== 'ready' || greeted.current) return;
    const arrival = messages?.transition_to_orientation_message;
    if (!arrival) return;
    greeted.current = true;
    setStageMessage(arrival);
    speakTutor(arrival);
  }, [status, messages]);

  // Every served video and worked example is done — move on by itself rather
  // than parking the student on a button (Manjusha, 2026-07-28). The ref makes
  // it fire once; `finishing` alone would let a re-render start a second call.
  const advanced = useRef(false);
  useEffect(() => {
    if (!allComplete || advanced.current || status !== 'ready' || !sessionId) return;
    advanced.current = true;
    void finish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allComplete, status, sessionId]);

  const finish = async () => {
    if (!sessionId) return;   // load() opens one first; nothing to complete yet
    setFinishing(true);
    setError(null);
    try {
      const rec = await completeOrientation(sessionId, studentId(), {
        videoIds: doneVideoIds,
        workedExampleIds: doneExampleIds,
      });
      setBackendSession(rec);
      // usePhaseRouting follows this to the next phase's screen.
      //
      // Through applyBackendPhase rather than a raw setState: it swaps the
      // question text, type and options together, so the phase being left
      // cannot leave its choices sitting under the next phase's question
      // (Manjusha, 8 Aug — diagnostic options under a Phase 2 question).
      applyBackendPhase({
        phase: rec.current_phase,
        questionId: rec.question_id,
        questionText: rec.current_question ?? null,
      });
      // The record's own line introduces the phase being entered. Dropping it
      // dumped the student straight onto a Phase 2 question with no word from
      // the tutor about what changed (Manjusha, 8 Aug) — the lesson page only
      // speaks an opening line when IT starts the session, and by here one is
      // already open. Seeding the transcript is what puts the line on screen
      // when the next screen mounts.
      if (rec.message?.trim()) {
        useNumeraStore.getState().addTranscriptMessage({ role: 'ai', text: rec.message.trim() });
      }
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

      {/* The video and the worked-example canvas are the content here, not
          illustrations beside it — at 760px they sat in a third of a laptop
          screen with the rest empty. Both are width-driven (16:9 video, the
          canvas matches), so widening the column is what makes them bigger. */}
      <div className="flex-1 overflow-y-auto flex justify-center p-8">
        <div className="w-[min(1180px,98vh)] max-w-full">
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

          {status === 'ready' && stageMessage && (
            <p className="text-[14px] leading-relaxed text-ink mb-5" aria-live="polite">
              {stageMessage}
            </p>
          )}

          {status === 'ready' && items[itemIndex] && (
            /* One item at a time, in the Student Model's delivery order: the
               video plays first and the worked example only begins once it has
               finished. Rendering the whole sequence at once had the tutor
               writing out the example while the video sat unplayed behind it
               (Manjusha, 2026-07-28). */
            <OrientationItem
              key={`${items[itemIndex].content_type}-${items[itemIndex].sequence_no}`}
              item={items[itemIndex]}
              topicCode={topicCode}
              messages={messages}
              onFinished={(completed) => {
                // Bridge into whatever comes next, in the backend's words.
                const next = items[itemIndex + 1];
                const bridge = !next
                  ? null
                  : next.content_type === 'WORKED_EXAMPLE'
                    ? messages?.video_to_worked_example_message
                    : messages?.between_videos_message;
                if (bridge) { setStageMessage(bridge); speakTutor(bridge); }
                if (completed?.videoId) {
                  setDoneVideoIds((ids) => (ids.includes(completed.videoId!) ? ids : [...ids, completed.videoId!]));
                }
                if (completed?.workedExampleId) {
                  setDoneExampleIds((ids) =>
                    ids.includes(completed.workedExampleId!) ? ids : [...ids, completed.workedExampleId!]);
                }
                setItemIndex((n) => Math.min(n + 1, items.length - 1));
              }}
              isLast={itemIndex === items.length - 1}
            />
          )}

          {status !== 'loading' && (
            <div className="flex items-center justify-end gap-4 mt-8">
              {error && status !== 'error' && (
                <span className="text-[12.5px] text-action-orange mr-auto">{error}</span>
              )}
              <button
                onClick={() => void finish()}
                disabled={finishing || !allComplete}
                title={allComplete ? undefined : 'Finish the video and the worked example first'}
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
/** What a finished item reports back, so its id can be sent on completion. */
interface CompletedContent {
  videoId?: string;
  workedExampleId?: string;
}

function OrientationItem({
  item, topicCode, messages, onFinished, isLast,
}: {
  item: SchemaOrientationItem;
  topicCode: string | null;
  messages: OrientationMessages | null;
  onFinished: (completed?: CompletedContent) => void;
  isLast: boolean;
}) {
  // Bumped to remount the player, which is how "Watch again" restarts it.
  const [replayKey, setReplayKey] = useState(0);

  if (item.content_type === 'ORIENTATION_VIDEO' && item.video) {
    // Back on Azure blob (2026-08-10): everything orientation serves now comes
    // from the one storage account, so a backend asset_url and our own fallback
    // point at the same place and there is no hosting preference left to encode.
    //
    // The blob MP4s are ~163 MB each and stream unadaptively, which is what made
    // the app sluggish while one was on screen in July. Re-encoding them (see
    // the Addendum 1 note: H.264 CRF 23 with `-movflags +faststart`) is what
    // fixes that now, not a second host.
    const src = item.video.asset_url ?? orientationVideoForTopicCode(topicCode);
    return (
      <section>
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-2 inline-flex items-center gap-1.5">
          <Film size={12} strokeWidth={1.8} /> Concept video
        </div>
        <h2 className="text-[17px] font-semibold text-ink mb-3">{item.video.title}</h2>
        {src ? (
          <>
            <VideoFile
              key={replayKey}
              media={{ kind: 'video', title: item.video.title, duration: '', summary: '', src }}
              spoken={messages?.before_video_message ?? null}
              onEnded={() => onFinished({ videoId: item.video!.video_id })}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {/* Remounting is the replay: VideoFile starts playback on mount,
                  so a fresh instance restarts it without reaching into its ref. */}
              <button
                onClick={() => setReplayKey((k) => k + 1)}
                className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12.5px] font-semibold text-ink transition-colors hover:border-focus-navy"
              >
                <RotateCw size={14} strokeWidth={2} /> Watch again
              </button>
              {!isLast && (
                <button
                  onClick={() => onFinished({ videoId: item.video!.video_id })}
                  className="ml-auto text-[12px] font-semibold text-slate-blue transition-colors hover:text-ink"
                >
                  Skip the video
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-muted-gray bg-reading-surface aspect-video w-full">
            <p className="text-[12.5px] text-slate-blue max-w-sm leading-relaxed">
              This video hasn&apos;t been uploaded yet — the worked example covers the same ground.
            </p>
            {!isLast && (
              <button
                onClick={() => onFinished({ videoId: item.video!.video_id })}
                className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-focus-navy text-white px-4 py-2 text-[12.5px] font-semibold hover:opacity-80 transition-opacity"
              >
                Continue <ArrowRight size={15} strokeWidth={2} />
              </button>
            )}
          </div>
        )}
      </section>
    );
  }

  if (item.content_type === 'WORKED_EXAMPLE' && item.worked_example) {
    return (
      <WorkedExampleCanvas
        example={item.worked_example}
        closingMessage={messages?.worked_example_to_guided_message ?? null}
        onFinished={() => onFinished({ workedExampleId: item.worked_example!.worked_example_id })}
      />
    );
  }
  return null;
}

/**
 * The tutor's worked example, written onto the canvas one step at a time in
 * time with the tutor's voice (Manjusha, 2026-07-28).
 *
 * It used to render all eight steps at once as a list of cards, which read as a
 * document to skim rather than a lesson to follow. Now each step's
 * `screen_content` is written onto the shared tutor canvas as the matching
 * `narration_text` is spoken, and the next step only starts once the voice for
 * the current one has finished — so the writing and the talking stay together.
 *
 * Only the tutor writes here; the student watches and explains it back in
 * Teacher Mode next, so the canvas is mounted `tutorOnly`.
 */
function WorkedExampleCanvas({
  example, closingMessage, onFinished,
}: {
  example: SchemaWorkedExample;
  /** Backend-authored hand-off line, spoken once the last step lands. */
  closingMessage: string | null;
  onFinished: () => void;
}) {
  const applyCanvasDraw = useNumeraStore((s) => s.applyCanvasDraw);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  const steps = useMemo(
    () => [...example.steps].sort((a, b) => a.sequence_no - b.sequence_no),
    [example.steps],
  );

  // -1 = nothing written yet; steps.length = finished.
  const [index, setIndex] = useState(-1);
  const advance = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Paused means "don't advance by yourself" — the student still moves with the
   * step buttons. The walkthrough used to run start to finish with no way to
   * hold it, go back over a step, or replay it (Manjusha, 2026-07-28), which is
   * exactly what a student needs when a step goes past too fast.
   *
   * Mirrored into a ref because the advance callback is created inside the step
   * effect and would otherwise close over a stale value.
   */
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);

  /**
   * Set the ref FIRST, then the state.
   *
   * Mirroring the ref during render left a window where a narration finishing
   * between the click and the re-render still saw `paused === false` and
   * scheduled the next step — pressing Pause visibly advanced anyway. The ref
   * is what the advance callback reads, so it has to change synchronously.
   */
  const setPausedNow = (next: boolean) => {
    pausedRef.current = next;
    if (next && advance.current) clearTimeout(advance.current);
    setPaused(next);
  };

  // Start on a clean sheet, and never let this phase's marks follow the student
  // into the next one — the tutor layer is global.
  useEffect(() => {
    clearTutorMarks();
    const kick = setTimeout(() => setIndex(0), 500);
    return () => {
      clearTimeout(kick);
      if (advance.current) clearTimeout(advance.current);
      stopTutorSpeech();
      clearTutorMarks();
    };
  }, [clearTutorMarks, example.worked_example_id]);

  useEffect(() => {
    if (index < 0 || index >= steps.length) return;
    const step = steps[index];

    // `replace`, not `append`: the canvas shows ONE step at a time. Stacking
    // every step turned the sheet back into the list of eight this was meant to
    // get away from (Manjusha, 2026-07-28) — by the end the student is reading a
    // wall of working instead of watching one idea being written.
    applyCanvasDraw({
      author: 'tutor',
      mode: 'replace',
      actionId: `${example.worked_example_id}-${step.step_id}`,
      elements: stepElements(step, index, steps.length),
    });

    // Move on when the narration finishes. `done` is latched because speakTutor
    // fires onEnd immediately for empty text and the browser-speech fallback can
    // fire it more than once; the timeout is the safety net for a provider that
    // never calls back at all, so a silent failure can't strand the lesson.
    let done = false;
    const next = () => {
      if (done) return;
      done = true;
      if (pausedRef.current) return;   // held — the student advances manually
      // Re-check on fire: Pause pressed inside this 450ms window would
      // otherwise still land one more step, so the button looked ignored.
      advance.current = setTimeout(() => {
        if (pausedRef.current) return;
        setIndex((n) => n + 1);
      }, 450);
    };
    speakTutor(step.narration_text ?? '', next);
    const failsafe = setTimeout(next, 15_000);
    return () => clearTimeout(failsafe);
  }, [index, steps, applyCanvasDraw, example.worked_example_id]);

  /** Jump to a step: stops any narration and any pending auto-advance first. */
  const goTo = (n: number) => {
    if (advance.current) clearTimeout(advance.current);
    stopTutorSpeech();
    setIndex(Math.max(0, Math.min(n, steps.length - 1)));
  };

  // Stepping by hand means the student is driving; don't yank them along.
  const stepBy = (delta: number) => {
    setPausedNow(true);
    goTo(index + delta);
  };

  const current = index >= 0 && index < steps.length ? steps[index] : null;
  const finished = index >= steps.length;

  // Report completion once the last step lands, and say the backend's hand-off
  // line. Guarded by a ref because `finished` stays true on every later render.
  const reported = useRef(false);
  useEffect(() => {
    if (!finished || reported.current) return;
    reported.current = true;
    if (closingMessage) speakTutor(closingMessage);
    onFinished();
  }, [finished, closingMessage, onFinished]);

  return (
    <section>
      <div className="flex items-end justify-between gap-4 mb-2">
        <div>
          <div className="text-[10px] tracking-widest uppercase text-slate-blue inline-flex items-center gap-1.5">
            <PenLine size={12} strokeWidth={1.8} /> Worked example · Numera is writing
          </div>
          <h2 className="text-[17px] font-semibold text-ink mt-0.5">{example.title}</h2>
        </div>
        <div className="text-[11.5px] text-slate-blue flex-shrink-0" aria-live="polite">
          {finished ? 'Done' : `Step ${Math.max(index, 0) + 1} of ${steps.length}`}
        </div>
      </div>

      {/* Progress across the steps, so the student can see how far in they are. */}
      <div className="flex items-center gap-1 mb-3" aria-hidden="true">
        {steps.map((s, i) => (
          <span
            key={s.step_id}
            className={cn('h-1 flex-1 rounded-full transition-colors',
              i <= index ? 'bg-focus-navy' : 'bg-reading-surface')}
          />
        ))}
      </div>

      <div
        className="relative h-[460px] rounded-xl border border-muted-gray bg-white overflow-hidden"
        style={{
          backgroundImage:
            'linear-gradient(#EEF0F3 1px, transparent 1px), linear-gradient(90deg, #EEF0F3 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      >
        <DrawingCanvas tutorOnly />
      </div>

      {/* What the tutor is saying, in text — the lesson must still work with the
          sound off, and it is what a student re-reads after listening. */}
      <p className="text-[13.5px] text-ink leading-relaxed mt-3 min-h-[3rem]" aria-live="polite">
        {current?.narration_text ?? (finished ? closingMessage ?? '' : '')}
      </p>

      {/* Controls. Named for what they do to the lesson, not to the player. */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={() => stepBy(-1)}
          disabled={index <= 0}
          className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12.5px] font-semibold text-ink transition-colors hover:border-focus-navy disabled:opacity-30"
        >
          <ChevronLeft size={14} strokeWidth={2} /> Previous step
        </button>

        {!finished && (
          <button
            onClick={() => setPausedNow(!paused)}
            className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12.5px] font-semibold text-ink transition-colors hover:border-focus-navy"
          >
            {paused ? <><Play size={14} strokeWidth={2} /> Continue</> : <><Pause size={14} strokeWidth={2} /> Pause</>}
          </button>
        )}

        <button
          onClick={() => stepBy(1)}
          disabled={finished || index >= steps.length - 1}
          className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12.5px] font-semibold text-ink transition-colors hover:border-focus-navy disabled:opacity-30"
        >
          Next step <ArrowRight size={14} strokeWidth={2} />
        </button>

        <button
          onClick={() => { clearTutorMarks(); reported.current = false; goTo(0); }}
          className="inline-flex items-center gap-1.5 rounded-md border border-muted-gray px-3 py-2 text-[12.5px] font-semibold text-ink transition-colors hover:border-focus-navy"
        >
          <RotateCw size={14} strokeWidth={2} /> Start again
        </button>

        {!finished && (
          <button
            onClick={() => { stopTutorSpeech(); setIndex(steps.length); }}
            className="ml-auto text-[12px] font-semibold text-slate-blue transition-colors hover:text-ink"
          >
            Skip the walkthrough
          </button>
        )}
      </div>
    </section>
  );
}

/**
 * One step's line of working, alone on the sheet.
 *
 * Only the current step is drawn, so it sits large and centred rather than being
 * squeezed into a stack — the point is to watch one idea being written, not to
 * end up rereading eight lines.
 *
 * `screen_content` is plain unicode maths ("a × a = a²"), not LaTeX, so it is a
 * `text` element rather than `math` — handing it to KaTeX would render the
 * source, not the maths. Geometry is normalised 0–1 and text is anchored at its
 * LEFT edge (TUTOR-CANVAS-WRITE-SPEC §3.3).
 */
function stepElements(
  step: SchemaWorkedExampleStep,
  index: number,
  total: number,
): Array<Omit<TutorElement, 'id'>> {
  if (!step.screen_content) return [];
  return [
    {
      kind: 'text',
      x: 0.08,
      y: 0.34,
      text: `Step ${index + 1} of ${total}`,
      size: 15,
      color: '#5A6478',
    },
    {
      kind: 'text',
      x: 0.08,
      y: 0.48,
      text: step.screen_content,
      size: 34,
      color: '#1B2A4A',
    },
  ];
}


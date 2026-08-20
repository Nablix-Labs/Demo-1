'use client';

/**
 * Tutor Live Review (§8.4, Centre) — "the largest area of the page".
 *
 * Numera writes the correct working while explaining it. The writing engine is
 * the one already used for the Phase 1 walkthrough: `useWorkedExamplePlayer`
 * paces the steps against the narration, `TutorLayer` reveals each mark as an
 * ink wipe, and `TutorHandOverlay` rides the nib. §8.6 asks for no avatar —
 * "the tutor is represented by voice + live writing" — which is exactly what
 * that stack already is.
 *
 * The steps are mapped onto the walkthrough player's step shape rather than the
 * player being made generic. The mapping is lossless and the meanings line up
 * one-to-one (`tutor_write` is what goes on screen, `narration` is what is
 * said), so a type parameter would buy nothing and would mean editing the hook
 * that the orientation lesson depends on.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  Play, Pause, RotateCcw, ChevronLeft, ChevronRight, Maximize2, Minimize2,
} from 'lucide-react';
import { Chip } from '@/components/PageShell';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useWorkedExamplePlayer } from '@/hooks/useWorkedExamplePlayer';
import { setTutorSpeechRate } from '@/lib/tts';
import { boardDraw } from '@/lib/phase4Board';
import { fetchWorkArtifactPdfUrl } from '@/lib/workArtifactPdf';
import { openingPageNo } from '@/lib/phase4Review';
import { cn } from '@/lib/cn';
import type { Phase4Replay, SchemaWorkedExampleStep } from '@/lib/api';

// react-konva is client-only, and the tutor board is the same surface the
// student writes on elsewhere — mounted `tutorOnly` so only the tutor's ink is
// on it and nothing the student drew in an earlier phase follows them here.
const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

/** §8.5 speed control. 1× first, because that is what the tutor is tuned for. */
const SPEEDS = [1, 1.25, 1.5, 0.75];

export default function TutorStage({
  replay,
  progressLabel,
  onPrevReplay,
  onNextReplay,
  hasPrevReplay,
  nextLabel,
}: {
  replay: Phase4Replay;
  progressLabel: string | null;
  onPrevReplay: () => void;
  onNextReplay: () => void;
  hasPrevReplay: boolean;
  /** What the forward control does next — the last replay leads to the summary. */
  nextLabel: string;
}) {
  const applyCanvasDraw = useNumeraStore((s) => s.applyCanvasDraw);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  const [pageNo, setPageNo] = useState(() => openingPageNo(replay));
  const [speed, setSpeed] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);

  // Opening on the page the first error is on (§7.5). Re-run per replay: the
  // student moving to the next correction should land on its page, not stay on
  // whichever page the previous one happened to end on.
  useEffect(() => { setPageNo(openingPageNo(replay)); }, [replay]);

  /**
   * Memoised on the replay, NOT rebuilt per render.
   *
   * The player sorts this array inside a useMemo keyed on the array itself and
   * the step effect depends on the result, so a fresh array every render would
   * restart the narration on every render — the tutor stuck repeating step one
   * for as long as anything else on the page changed.
   */
  const playerSteps = useMemo<SchemaWorkedExampleStep[]>(
    () => replay.replay_steps.map((step) => ({
      step_id: `${replay.review_item_id}-${step.sequence_no}`,
      sequence_no: step.sequence_no,
      screen_content: step.tutor_write,
      narration_text: step.narration,
    })),
    [replay],
  );

  // What the board currently holds, so a forward step can append one line while
  // any other move rebuilds. Reset per replay — a new replay starts from blank.
  const drawnIndex = useRef(-1);
  useEffect(() => { drawnIndex.current = -1; }, [replay]);

  const draw = useCallback(
    (_step: SchemaWorkedExampleStep, index: number) => {
      const { mode, elements } = boardDraw(drawnIndex.current, index, replay.replay_steps);
      drawnIndex.current = index;
      if (!elements.length) return;
      applyCanvasDraw({
        author: 'tutor',
        mode,
        actionId: `${replay.review_item_id}-${mode}-${index}`,
        elements,
      });
    },
    [applyCanvasDraw, replay],
  );

  const { index, steps, finished, paused, setPaused, stepBy, restart } = useWorkedExamplePlayer({
    exampleId: replay.review_item_id,
    steps: playerSteps,
    draw,
    onClear: clearTutorMarks,
  });

  const changeSpeed = useCallback(() => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    setSpeed(next);
    setTutorSpeechRate(next);
  }, [speed]);

  // Leave the tutor at its natural pace for whoever comes next: the rate is a
  // module-level playback setting, so a student who slowed this replay down
  // would otherwise find the next phase's tutor slowed down too.
  useEffect(() => () => setTutorSpeechRate(1), []);

  const { pdf_url: pdfUrl, page_count: pageCount } = replay.work_artifact;
  const stepPosition = Math.min(Math.max(index, 0) + 1, steps.length);

  // Keyed on pdfUrl, not pageNo: the page selector only moves the #page=N
  // fragment on an already-loaded blob (see the iframe below) — refetching per
  // page would thrash the blob and leak object URLs.
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [pdfLoadFailed, setPdfLoadFailed] = useState(false);

  useEffect(() => {
    if (!pdfUrl) {
      setPdfBlobUrl(null);
      setPdfLoadFailed(false);
      return;
    }
    let cancelled = false;
    setPdfLoadFailed(false);
    fetchWorkArtifactPdfUrl(pdfUrl)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        setPdfBlobUrl(url);
      })
      .catch(() => {
        if (!cancelled) setPdfLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [pdfUrl]);

  // Revoke whenever the blob is replaced or this stage unmounts — never held
  // past the render that uses it.
  useEffect(() => () => {
    if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
  }, [pdfBlobUrl]);

  return (
    <section
      aria-label="Tutor live review"
      className={cn(
        'flex flex-col min-w-0 flex-1 rounded-lg border border-muted-gray bg-white overflow-hidden',
        fullscreen && 'fixed inset-3 z-50',
      )}
      style={fullscreen ? { boxShadow: '0 10px 34px rgba(11,16,32,0.28)' } : undefined}
    >
      {/* Header — what is being reviewed, and how far through */}
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-muted-gray bg-reading-surface">
        <Chip tone="solid">Tutor live review</Chip>
        <span className="text-[12px] text-slate-blue truncate flex-1 min-w-0">
          {progressLabel ?? 'Review'} · Step {stepPosition} of {steps.length}
        </span>
        <button
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? 'Exit fullscreen' : 'Fullscreen tutor review'}
          aria-label={fullscreen ? 'Exit fullscreen' : 'Fullscreen tutor review'}
          className="flex-shrink-0 text-slate-blue hover:text-ink transition-colors"
        >
          {fullscreen ? <Minimize2 size={16} strokeWidth={1.8} /> : <Maximize2 size={16} strokeWidth={1.8} />}
        </button>
      </header>

      {/* The question under review, above the board it is being worked on. */}
      <div className="px-4 py-3 border-b border-muted-gray">
        <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-1">Question</div>
        <p className="text-[15px] text-ink font-[Cambria_Math,Georgia,serif] leading-snug">
          {replay.question_text}
        </p>
      </div>

      {/* Board + the student's own work beside it */}
      <div className="flex-1 min-h-0 flex">
        {/* The tutor writes here. Dominant by design (§8.4). */}
        <div className="flex-1 min-w-0 relative bg-white">
          <DrawingCanvas tutorOnly />
        </div>

        {/* §8.4 "student's original submitted work" + "page selector when the
            student work had multiple pages". Locked: this is a record of what
            was submitted, and Phase 3 has already closed. */}
        <div className="w-[210px] flex-shrink-0 border-l border-muted-gray bg-reading-surface flex flex-col">
          <div className="px-3 py-2.5 flex items-baseline justify-between gap-2 border-b border-muted-gray">
            <span className="text-[10px] tracking-widest uppercase text-slate-blue">Your work</span>
            {/* Named as locked because it is: Phase 3 has closed and this is the
                record of what was submitted, not something to revise now. */}
            <span className="text-[10px] text-slate-blue/70">Locked</span>
          </div>
          <div className="flex-1 min-h-0 p-2.5">
            {/* The work is stored as one combined PDF, not as page images
                (WorkArtifactPersistResponse — Chiru PR #156), so the page
                selector moves the PDF viewer rather than swapping a src. The
                fragment is how every browser's built-in viewer takes a page;
                `toolbar=0` hides its chrome, which would otherwise put a second
                set of page controls inside a 210px column. */}
            {!pdfUrl ? (
              <p className="text-[11.5px] text-slate-blue leading-relaxed">
                Your original work is not available for this question.
              </p>
            ) : pdfLoadFailed ? (
              <p className="text-[11.5px] text-slate-blue leading-relaxed">
                Your original work could not be loaded.
              </p>
            ) : pdfBlobUrl ? (
              <iframe
                key={pageNo}
                src={`${pdfBlobUrl}#page=${pageNo}&view=FitH&toolbar=0&navpanes=0`}
                title={`Your submitted work, page ${pageNo} of ${pageCount}`}
                className="w-full h-full rounded border border-muted-gray bg-white"
              />
            ) : null}
          </div>
          {/* Only when there is more than one page — a selector over a single
              page is a control that cannot do anything. */}
          {pageCount > 1 && (
            <div className="flex items-center justify-center gap-1 p-2 border-t border-muted-gray">
              {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  onClick={() => setPageNo(n)}
                  aria-current={n === pageNo ? 'true' : undefined}
                  className={cn(
                    'w-6 h-6 rounded text-[11px] font-semibold transition-colors',
                    n === pageNo
                      ? 'bg-focus-navy text-white'
                      : 'text-slate-blue hover:bg-white',
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* §8.5 player controls */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-t border-muted-gray bg-reading-surface">
        <button
          onClick={() => setPaused(!paused)}
          aria-label={paused ? 'Play' : 'Pause'}
          className="w-9 h-9 rounded-full bg-focus-navy text-white flex items-center justify-center hover:opacity-80 transition-opacity"
        >
          {paused ? <Play size={15} strokeWidth={2.2} /> : <Pause size={15} strokeWidth={2.2} />}
        </button>
        <button onClick={restart} title="Replay this explanation" aria-label="Replay this explanation" className={ctrl}>
          <RotateCcw size={15} strokeWidth={1.9} />
        </button>
        <button onClick={() => stepBy(-1)} disabled={index <= 0} title="Previous step" aria-label="Previous step" className={ctrl}>
          <ChevronLeft size={16} strokeWidth={1.9} />
        </button>
        <button onClick={() => stepBy(1)} disabled={finished || index >= steps.length - 1} title="Next step" aria-label="Next step" className={ctrl}>
          <ChevronRight size={16} strokeWidth={1.9} />
        </button>

        <button
          onClick={changeSpeed}
          title="Playback speed"
          className="ml-1 rounded-md border border-muted-gray px-2.5 py-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors"
        >
          {speed}×
        </button>

        <div className="ml-auto flex items-center gap-2">
          <button onClick={onPrevReplay} disabled={!hasPrevReplay} className={navBtn}>
            <ChevronLeft size={14} strokeWidth={1.9} /> Previous
          </button>
          <button
            onClick={onNextReplay}
            className="inline-flex items-center gap-1.5 rounded-md bg-focus-navy px-4 py-2 text-[12.5px] font-semibold text-white hover:opacity-80 transition-opacity"
          >
            {nextLabel} <ChevronRight size={14} strokeWidth={1.9} />
          </button>
        </div>
      </div>
    </section>
  );
}

const ctrl =
  'w-9 h-9 rounded-full border border-muted-gray text-slate-blue flex items-center justify-center ' +
  'hover:text-ink hover:border-slate-blue disabled:opacity-30 disabled:hover:border-muted-gray transition-colors';

const navBtn =
  'inline-flex items-center gap-1 text-[12.5px] font-semibold text-slate-blue hover:text-ink ' +
  'disabled:opacity-30 disabled:hover:text-slate-blue transition-colors';

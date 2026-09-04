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
  Play, Pause, RotateCcw, RotateCw, Maximize2, Minimize2,
  Volume2, VolumeX, Captions, Radio, Check, Lock,
} from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useWorkedExamplePlayer } from '@/hooks/useWorkedExamplePlayer';
import { setTutorSpeechRate, stopTutorSpeech } from '@/lib/tts';
import { boardDraw } from '@/lib/phase4Board';
import { loadWorkArtifactPdf, type PdfOutcome } from '@/lib/workArtifactPdf';
import { openingPageNo } from '@/lib/phase4Review';
import { stagesFrom, totalDurationMs, elapsedMsAt, clock } from '@/lib/phase4Stages';
import { usesBoards } from '@/lib/phase4BoardLayout';
import ReplayBoard from './ReplayBoard';
import { cn } from '@/lib/cn';
import type { Phase4Replay, SchemaWorkedExampleStep } from '@/lib/api';

// react-konva is client-only, and the tutor board is the same surface the
// student writes on elsewhere — mounted `tutorOnly` so only the tutor's ink is
// on it and nothing the student drew in an earlier phase follows them here.
const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

/** §8.5 speed control. 1× first, because that is what the tutor is tuned for. */
const SPEEDS = [1, 1.25, 1.5, 0.75];

/**
 * What each non-ready state says. Written for the person reading it: each one
 * names what happened and, where there is one, what to do about it. None of
 * them apologise, and none say "error".
 */
const PDF_MESSAGE: Record<Exclude<PdfOutcome, { kind: 'ready' }>['kind'] | 'loading', string> = {
  loading: 'Loading your original work\u2026',
  unauthorized: 'You do not have permission to view this work. Sign in again, or ask your teacher.',
  unavailable: 'This work is no longer stored. The review below still applies.',
  invalid: 'The stored file could not be opened as a document. Please report this question.',
  error: 'Your original work could not be loaded just now.',
};

export default function TutorStage({
  replay,
  progressLabel,
}: {
  replay: Phase4Replay;
  progressLabel: string | null;
}) {
  const applyCanvasDraw = useNumeraStore((s) => s.applyCanvasDraw);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);

  const [pageNo, setPageNo] = useState(() => openingPageNo(replay));
  const [speed, setSpeed] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [muted, setMuted] = useState(false);
  const [captions, setCaptions] = useState(false);

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

  /**
   * Structured board, or the handwriting canvas?
   *
   * Decided once per REPLAY, never per step. Switching surfaces partway through
   * one explanation would swap the whole centre panel mid-sentence; a step
   * inside a boarded replay that carries no board of its own shows its
   * `tutor_write` as a heading on the same surface instead.
   *
   * When no step has a board this is false and NOTHING below changes — the
   * canvas, the draw effect and the ink reveal all run exactly as they did
   * before PR #257, which is the fallback Sanya asked us to preserve.
   */
  const boarded = useMemo(() => usesBoards(replay.replay_steps), [replay]);
  // What the board currently holds, so a forward step can append one line while
  // any other move rebuilds. Reset per replay — a new replay starts from blank.
  const drawnIndex = useRef(-1);
  useEffect(() => { drawnIndex.current = -1; }, [replay]);

  const draw = useCallback(
    (_step: SchemaWorkedExampleStep, index: number) => {
      // A boarded replay has no canvas mounted, so drawing to it would put ink
      // on a surface nobody is looking at — and leave it in the store for
      // whatever mounts the tutor layer next.
      if (boarded) return;
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
    [applyCanvasDraw, replay, boarded],
  );

  const { index, steps, finished, paused, setPaused, stepBy } = useWorkedExamplePlayer({
    exampleId: replay.review_item_id,
    steps: playerSteps,
    draw,
    onClear: clearTutorMarks,
  });

  /**
   * The stage strip, and the timeline behind the scrubber.
   *
   * Both are null-tolerant by design: `stagesFrom` falls back to numbered steps
   * when the backend has authored no stage labels, and `totalDurationMs`
   * returns null unless EVERY step is timed — a partially timed replay would
   * produce a clock that runs out while the tutor is still talking, which is
   * worse than showing no clock at all.
   */
  const stages = useMemo(
    () => stagesFrom(replay.replay_steps, index),
    [replay, index],
  );
  const totalMs = useMemo(() => totalDurationMs(replay.replay_steps), [replay]);
  const elapsedMs = useMemo(
    () => (totalMs === null ? null : elapsedMsAt(replay.replay_steps, index)),
    [replay, index, totalMs],
  );
  /** Fraction played. Falls back to step position when the replay is untimed. */
  const played = totalMs !== null && elapsedMs !== null
    ? elapsedMs / totalMs
    : steps.length > 1 ? Math.max(0, index) / (steps.length - 1) : 0;

  const currentStep = replay.replay_steps[Math.max(0, Math.min(index, replay.replay_steps.length - 1))];

  const changeSpeed = useCallback(() => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    setSpeed(next);
    setTutorSpeechRate(next);
  }, [speed]);

  // Leave the tutor at its natural pace for whoever comes next: the rate is a
  // module-level playback setting, so a student who slowed this replay down
  // would otherwise find the next phase's tutor slowed down too.
  useEffect(() => () => setTutorSpeechRate(1), []);

  // Muting stops the voice outright rather than turning its volume down: the
  // tutor speaks through TTS, which has no volume of its own, and a "muted"
  // control that still talked would be the worst of both.
  useEffect(() => {
    if (muted) stopTutorSpeech();
  }, [muted, index]);

  const {
    pdf_url: pdfUrl,
    page_count: pageCount,
    snapshot_image_url: snapshotUrl,
    error_regions: errorRegions,
  } = replay.work_artifact;
  /**
   * The flat image is preferred for this panel, the PDF is the record.
   *
   * A PDF in a 210px column renders as an unreadable page of an embedded
   * viewer; the snapshot is the student's own answer at a size they can
   * actually see, which is what the panel is for. The PDF path stays for every
   * session where no snapshot was captured.
   */
  const useSnapshot = Boolean(snapshotUrl?.trim());

  // Five named states, not one boolean: an approver has to be able to tell "you
  // may not read this" from "there is nothing here" from "what came back was not
  // a document". See PdfOutcome.
  //
  // Keyed on pdfUrl, not pageNo: the page selector only moves the #page=N
  // fragment on an already-loaded blob (see the iframe below) — refetching per
  // page would thrash the blob and leak object URLs.
  const [pdf, setPdf] = useState<PdfOutcome | { kind: 'loading' }>({ kind: 'loading' });
  const pdfBlobUrl = pdf.kind === 'ready' ? pdf.url : null;

  useEffect(() => {
    if (!pdfUrl) {
      setPdf({ kind: 'loading' });
      return;
    }
    let cancelled = false;
    setPdf({ kind: 'loading' });
    void loadWorkArtifactPdf(pdfUrl).then((outcome) => {
      if (cancelled) {
        // The load finished after this stage moved on. Revoke here or the URL
        // outlives every reference to it.
        if (outcome.kind === 'ready') URL.revokeObjectURL(outcome.url);
        return;
      }
      setPdf(outcome);
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
      <header className="flex items-center gap-3 px-4 py-2.5 border-b border-muted-gray bg-white">
        <h2 className="text-[14px] font-semibold text-ink flex-shrink-0">Tutor live review</h2>
        {/* "Live" describes the tutor writing and speaking as you watch, which
            is what this stage does — the steps are authored, but the
            explanation is performed here rather than played back as video.
            Whether it should ever mean STREAMED from the backend is an open
            question with Chirudeva; nothing here claims a socket. */}
        <span className="flex-shrink-0 rounded-full bg-focus-navy px-2.5 py-1 text-[11px] font-semibold text-white">
          Live
        </span>
        <span className="text-[12px] text-slate-blue truncate flex-1 min-w-0">
          {paused ? 'Paused' : 'Tutor is explaining in real time'}
          {progressLabel ? ` · ${progressLabel}` : ''}
        </span>
        <Radio
          size={16}
          strokeWidth={1.9}
          aria-hidden
          className={cn('flex-shrink-0', paused ? 'text-muted-gray' : 'text-focus-navy animate-pulse')}
        />
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
        {/* The tutor works here. Dominant by design (§8.4). */}
        <div className="flex-1 min-w-0 relative bg-white flex flex-col">
          {boarded ? (
            <ReplayBoard
              // Remount per step so the board is rebuilt rather than diffed
              // element-by-element into the previous step's shape.
              key={currentStep?.sequence_no ?? index}
              elements={currentStep?.board?.elements ?? []}
              fallbackText={currentStep?.tutor_write}
            />
          ) : (
            <DrawingCanvas tutorOnly />
          )}
        </div>

        {/* §8.4 "student's original submitted work" + "page selector when the
            student work had multiple pages". Locked: this is a record of what
            was submitted, and Phase 3 has already closed. */}
        <div className="w-[228px] flex-shrink-0 border-l border-muted-gray bg-reading-surface flex flex-col">
          <div className="px-3 py-2.5 flex items-center justify-between gap-2 border-b border-muted-gray">
            <span className="text-[12.5px] font-semibold text-ink">Your work</span>
            {/* Named as locked because it is: Phase 3 has closed and this is the
                record of what was submitted, not something to revise now. */}
            <span className="inline-flex items-center gap-1 text-[10.5px] text-slate-blue/80">
              <Lock size={11} strokeWidth={2} aria-hidden />
              Locked
            </span>
          </div>
          <div className="flex-1 min-h-0 p-2.5">
            {/* The work is stored as one combined PDF, not as page images
                (WorkArtifactPersistResponse — Chiru PR #156), so the page
                selector moves the PDF viewer rather than swapping a src. The
                fragment is how every browser's built-in viewer takes a page;
                `toolbar=0` hides its chrome, which would otherwise put a second
                set of page controls inside a 210px column. */}
            {useSnapshot ? (
              /* The snapshot, with the error ringed where the backend located
                 it. The regions are 0–1 fractions of this box, so the ring
                 tracks the image at whatever size the column renders it —
                 pixel coordinates would drift the moment the panel resized. */
              <div className="relative w-full h-full rounded-lg border border-muted-gray bg-white overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={snapshotUrl as string}
                  alt="A snapshot of the answer you submitted for this question"
                  className="w-full h-full object-contain"
                />
                {(errorRegions ?? []).map((region, i) => (
                  <span
                    key={i}
                    aria-hidden
                    className={cn(
                      'absolute rounded-[50%] border-2 pointer-events-none',
                      region.tone === 'note' ? 'border-sky-500/80' : 'border-red-500/80',
                    )}
                    style={{
                      left: `${region.x * 100}%`,
                      top: `${region.y * 100}%`,
                      width: `${region.w * 100}%`,
                      height: `${region.h * 100}%`,
                    }}
                  />
                ))}
              </div>
            ) : !pdfUrl ? (
              <p className="text-[11.5px] text-slate-blue leading-relaxed">
                Your original work is not available for this question.
              </p>
            ) : pdf.kind === 'ready' ? (
              <iframe
                key={pageNo}
                src={`${pdf.url}#page=${pageNo}&view=FitH&toolbar=0&navpanes=0`}
                title={`Your submitted work, page ${pageNo} of ${pageCount}`}
                className="w-full h-full rounded border border-muted-gray bg-white"
              />
            ) : (
              <p role="status" className="text-[11.5px] text-slate-blue leading-relaxed">
                {PDF_MESSAGE[pdf.kind]}
              </p>
            )}
          </div>
          {/* Only when there is more than one page — a selector over a single
              page is a control that cannot do anything. */}
          <p className="px-3 pb-3 text-[11px] text-slate-blue leading-relaxed">
            This is a snapshot of your original answer. It will remain locked.
          </p>
          {/* Only when there is more than one page AND the pages are what is
              being shown — the snapshot is a single image, so a page selector
              over it would move nothing. */}
          {!useSnapshot && pageCount > 1 && (
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
      <div className="flex items-center gap-2 px-3 py-2.5 border-t border-muted-gray bg-white">
        <button
          onClick={() => setPaused(!paused)}
          aria-label={paused ? 'Play' : 'Pause'}
          className="w-10 h-10 rounded-full bg-focus-navy text-white flex items-center justify-center hover:opacity-85 transition-opacity"
        >
          {paused ? <Play size={16} strokeWidth={2.2} /> : <Pause size={16} strokeWidth={2.2} />}
        </button>

        {/* Back and forward move a STEP, and say so.
            The design shows -10s/+10s, which needs a real audio timeline to be
            honest — seeking ten seconds into a step-paced narration would land
            between two steps with nothing to show. When every step carries a
            duration these become time seeks; until then they move one step and
            are labelled that way. */}
        <button onClick={() => stepBy(-1)} disabled={index <= 0} title="Previous step" aria-label="Previous step" className={ctrl}>
          <RotateCcw size={15} strokeWidth={1.9} />
        </button>
        <button onClick={() => stepBy(1)} disabled={finished || index >= steps.length - 1} title="Next step" aria-label="Next step" className={ctrl}>
          <RotateCw size={15} strokeWidth={1.9} />
        </button>

        {/* The clock only appears when the backend timed the steps. Counting a
            made-up one would run out while the tutor was still talking. */}
        {totalMs !== null && elapsedMs !== null && (
          <span className="ml-1 flex-shrink-0 text-[11.5px] tabular-nums text-slate-blue">
            {clock(elapsedMs)} / {clock(totalMs)}
          </span>
        )}

        {/* Progress, not a scrubber: it reports where the explanation has got
            to and is not draggable, because dragging implies a seek this
            player cannot perform without per-step timings. Stepping is how you
            move, and those controls are right there. */}
        <div
          role="progressbar"
          aria-label="Explanation progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(played * 100)}
          className="flex-1 min-w-[60px] h-1.5 rounded-full bg-muted-gray overflow-hidden"
        >
          <div
            className="h-full rounded-full bg-focus-navy transition-[width] duration-300"
            style={{ width: `${Math.min(100, Math.max(0, played * 100))}%` }}
          />
        </div>

        <button
          onClick={changeSpeed}
          title="Playback speed"
          className="flex-shrink-0 rounded-md border border-muted-gray px-2.5 py-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink transition-colors"
        >
          {speed}×
        </button>
        <button
          onClick={() => setMuted((v) => !v)}
          title={muted ? 'Unmute the tutor' : 'Mute the tutor'}
          aria-label={muted ? 'Unmute the tutor' : 'Mute the tutor'}
          aria-pressed={muted}
          className={ctrl}
        >
          {muted ? <VolumeX size={15} strokeWidth={1.9} /> : <Volume2 size={15} strokeWidth={1.9} />}
        </button>
        {/* Captions show the narration as text. Not a media track — the tutor
            speaks from `narration`, so the caption IS that string, which is
            also why it is always available rather than depending on a backend
            cue list. */}
        <button
          onClick={() => setCaptions((v) => !v)}
          title={captions ? 'Hide captions' : 'Show captions'}
          aria-label={captions ? 'Hide captions' : 'Show captions'}
          aria-pressed={captions}
          className={cn(ctrl, captions && 'border-focus-navy text-focus-navy')}
        >
          <Captions size={15} strokeWidth={1.9} />
        </button>
        <button
          onClick={() => setFullscreen((v) => !v)}
          title={fullscreen ? 'Exit fullscreen' : 'Fullscreen tutor review'}
          aria-label={fullscreen ? 'Exit fullscreen' : 'Fullscreen tutor review'}
          className={ctrl}
        >
          {fullscreen ? <Minimize2 size={15} strokeWidth={1.8} /> : <Maximize2 size={15} strokeWidth={1.8} />}
        </button>
      </div>

      {/* The narration in writing, for anyone who cannot hear it or would
          rather read along. Sits above the stage strip so it is next to the
          board it describes. */}
      {captions && (
        <p
          aria-live="polite"
          className="px-4 py-2.5 border-t border-muted-gray bg-ink/[0.03] text-[12.5px] text-ink leading-relaxed"
        >
          {steps[Math.max(0, Math.min(index, steps.length - 1))]?.narration_text ?? ''}
        </p>
      )}

      {/* The stage strip. Named stages when the backend authored them,
          numbered steps otherwise — never five invented names over a replay
          that does not have five stages (see lib/phase4Stages). */}
      {stages.length > 1 && (
        <ol className="flex items-center gap-1 px-3 py-2.5 border-t border-muted-gray bg-reading-surface overflow-x-auto">
          {stages.map((stage, i) => (
            <li key={`${stage.label}-${stage.startIndex}`} className="flex items-center gap-1 flex-shrink-0">
              {i > 0 && <span aria-hidden className="w-6 border-t border-dotted border-muted-gray" />}
              <span
                aria-current={stage.current ? 'step' : undefined}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-[11.5px] transition-colors',
                  stage.current
                    ? 'bg-focus-navy/10 font-semibold text-focus-navy'
                    : stage.done
                      ? 'text-emerald-600'
                      : 'text-slate-blue',
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    'w-5 h-5 rounded-full flex items-center justify-center text-[10.5px] font-semibold',
                    stage.current
                      ? 'bg-focus-navy text-white'
                      : stage.done
                        ? 'bg-emerald-500 text-white'
                        : 'bg-muted-gray text-slate-blue',
                  )}
                >
                  {stage.done ? <Check size={11} strokeWidth={2.6} /> : i + 1}
                </span>
                {stage.label}
              </span>
            </li>
          ))}
        </ol>
      )}

    </section>
  );
}

const ctrl =
  'w-9 h-9 rounded-full border border-muted-gray text-slate-blue flex items-center justify-center ' +
  'hover:text-ink hover:border-slate-blue disabled:opacity-30 disabled:hover:border-muted-gray transition-colors';


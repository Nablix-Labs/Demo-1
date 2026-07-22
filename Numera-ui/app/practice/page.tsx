'use client';

/**
 * Independent practice — the student solves alone. The AI is a silent observer
 * by default: it surfaces a hint after a pause or on request, and goes quiet if
 * the student signals distress. (Hint timing/distress detection is backend in
 * production; mocked here with timers + a manual "I'm stuck" control.)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Eye, EyeOff, Lightbulb, Check, ArrowRight } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useFlowNav } from '@/lib/useFlowNav';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { DEMO_CONCEPT_ID, DEMO_PHASE } from '@/lib/api';
import { demoFor } from '@/lib/demoContent';
import PhaseGate from '@/components/PhaseGate';
import Toolbar from '@/components/Canvas/Toolbar';
import { cn } from '@/lib/cn';

const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

type AIMode = 'observing' | 'hint' | 'quiet';

export default function PracticePage() {
  const items = useNumeraStore((s) => s.items);
  const setCanvasExporter = useNumeraStore((s) => s.setCanvasExporter);
  const practiceCompleted = useNumeraStore((s) => s.practiceCompleted);
  const setPracticeDone = useNumeraStore((s) => s.setPracticeDone);
  const completePhase = useNumeraStore((s) => s.completePhase);
  const currentTopicId = useNumeraStore((s) => s.currentTopicId);
  const questionText = useNumeraStore((s) => s.questionText);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);
  const { goStage } = useFlowNav();
  const tutor = useDemoTutor();

  // "Review with tutor": end the backend session first, save its summary, then
  // move to /review. Disabled while in flight; on failure the student stays here.
  const [ending, setEnding] = useState(false);
  const [endError, setEndError] = useState<string | null>(null);
  const reviewWithTutor = useCallback(async () => {
    setEndError(null);
    // No live backend session (mock mode) — just go to the review page.
    if (!tutor.apiEnabled || !tutor.sessionId) { goStage('review'); return; }
    setEnding(true);
    try {
      // end() saves the summary + clears sessionId on success, or throws.
      await tutor.end();
      goStage('review');
    } catch {
      setEndError("We couldn't finish your session. Please try again.");
    } finally {
      setEnding(false);
    }
  }, [tutor, goStage]);

  // Practice problem + hints for the placed topic.
  const demo = demoFor(currentTopicId);
  const HINTS = demo.practiceHints;

  // The question comes from the backend session (kept in sync by useDemoTutor
  // from /session/start and every /interaction response); the demo table is the
  // mock-mode fallback. Empty while the session is still loading.
  const QUESTION = tutor.apiEnabled ? questionText : demo.practiceQuestion;

  // Backend context — fixed demo identifiers, matching the API documentation.
  const PHASE = DEMO_PHASE;
  const QUESTION_ID = activeQuestionId;

  // Hands-free voice: on turn-end, fire the transcript + canvas to the backend.
  const { submitVoiceTurn } = tutor;
  const onTurnEnd = useCallback(
    (transcript: string, confidence?: number) => {
      void submitVoiceTurn(
        transcript,
        { concept_id: DEMO_CONCEPT_ID, question_id: QUESTION_ID, current_phase: PHASE, hint_count: 0 },
        confidence
      );
    },
    [submitVoiceTurn, QUESTION_ID, PHASE]
  );
  const voice = useVoiceTurn({ onTurnEnd });

  const [mode, setMode] = useState<AIMode>('observing');
  const [hintIndex, setHintIndex] = useState(0);
  const [hintText, setHintText] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  // Voice support is browser-only; gate render on mount to avoid SSR mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleExportReady = useCallback((fn: () => string | null) => {
    setCanvasExporter(fn);
  }, [setCanvasExporter]);

  // Start a backend session once on entry (no-op unless an API base URL is set).
  useEffect(() => {
    if (tutor.apiEnabled && !tutor.sessionId) {
      void tutor.start(DEMO_CONCEPT_ID, 'TEXT');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // After a pause in activity, the observer offers a hint (unless gone quiet)
  useEffect(() => {
    if (mode === 'quiet') return;
    if (idleTimer.current) clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => setMode('hint'), 15000);
    return () => { if (idleTimer.current) clearTimeout(idleTimer.current); };
  }, [items.length, mode]);

  const requestHint = async () => {
    setMode('hint');
    // Mock mode: walk the demo table. With a backend the hint must come from it,
    // otherwise the card would contradict the backend's question.
    if (!tutor.apiEnabled) {
      setHintText(HINTS[hintIndex]);
      setHintIndex((i) => Math.min(i + 1, HINTS.length - 1));
      return;
    }
    setHintText(null);
    const res = await tutor.hint({
      concept_id: DEMO_CONCEPT_ID,
      question_id: QUESTION_ID,
      current_phase: PHASE,
      current_hint_count: hintIndex,
    });
    // tutor.hint() swallows failures (it reports them into the transcript, which
    // this screen doesn't render) — so say so here instead of showing nothing.
    setHintText(res ? res.hint : "Sorry — I couldn't fetch a hint right now. Please try again in a moment.");
    if (res) setHintIndex((i) => i + 1);
  };

  // The idle observer flips to 'hint' without fetching, so in mock mode the card
  // falls back to the demo table; with a backend it stays closed until the
  // student asks and a real hint arrives.
  const hintBody = hintText ?? (tutor.apiEnabled ? null : HINTS[hintIndex]);

  const finish = () => {
    // Submit the canvas for live OCR + tutor feedback (best-effort).
    void tutor.submitCanvasWork();
    setDone(true);
    setPracticeDone();
    completePhase('practice');
  };

  return (
    <PhaseGate phase="practice">
    <div className="flex-1 min-w-0 flex flex-col bg-white" aria-label="Independent practice">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-3.5 border-b border-muted-gray flex-shrink-0">
        <div>
          <div className="text-[10px] tracking-widest uppercase text-slate-blue">Independent practice</div>
          <div className="text-[16px] font-semibold text-ink font-[Cambria_Math,Georgia,serif]">
            {QUESTION ? `Solve ${QUESTION}` : 'Loading question…'}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {/* AI mode indicator */}
          <span
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px]',
              mode === 'quiet' ? 'border-muted-gray text-slate-blue' : 'border-muted-gray text-ink'
            )}
          >
            {mode === 'quiet' ? <EyeOff size={14} strokeWidth={1.8} /> : <Eye size={14} strokeWidth={1.8} />}
            {mode === 'quiet' ? 'AI resting' : mode === 'hint' ? 'Hint ready' : 'AI observing'}
          </span>
          <button
            onClick={() => setMode(mode === 'quiet' ? 'observing' : 'quiet')}
            className="rounded-full border border-muted-gray px-3 py-1.5 text-[12px] font-semibold text-slate-blue hover:text-ink hover:border-muted-gray transition-colors"
          >
            {mode === 'quiet' ? 'Resume AI' : "I'm stuck — give me space"}
          </button>
        </div>
      </header>

      {/* Canvas */}
      <main
        className="flex-1 relative min-w-0 bg-white overflow-hidden"
        style={{
          backgroundImage: 'linear-gradient(#E0E2E5 1px, transparent 1px), linear-gradient(90deg, #E0E2E5 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      >
        <div className="absolute inset-0 z-[1]">
          <DrawingCanvas onExportReady={handleExportReady} />
        </div>

        {/* Hint card — only when the observer offers one */}
        {mode === 'hint' && !done && hintBody && (
          <div className="absolute top-5 left-6 z-20 max-w-sm flex items-start gap-3 bg-white border border-muted-gray rounded-xl px-4 py-3" style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}>
            <Lightbulb size={16} strokeWidth={1.8} className="flex-shrink-0 mt-0.5 text-ink" />
            <div>
              <div className="text-[10px] tracking-widest uppercase text-slate-blue mb-0.5">Gentle hint</div>
              <p className="text-[12.5px] text-ink leading-snug">{hintBody}</p>
            </div>
          </div>
        )}

        {/* Quiet/distress reassurance */}
        {mode === 'quiet' && (
          <div className="absolute top-5 left-6 z-20 max-w-sm text-[12.5px] text-slate-blue italic">
            Take your time. I&apos;m here quietly when you&apos;re ready.
          </div>
        )}

        {/* Done confirmation → continue to Review & Feedback */}
        {done && (
          <div className="absolute top-5 left-6 z-20 flex items-center gap-2">
            <span className="flex items-center gap-2 bg-focus-navy text-white rounded-full px-4 py-2 text-[12px]">
              <Check size={14} strokeWidth={2} /> Practice saved — nice work.
            </span>
            <button
              onClick={() => void reviewWithTutor()}
              disabled={ending}
              aria-busy={ending}
              className="flex items-center gap-1.5 rounded-full border border-focus-navy bg-white px-4 py-2 text-[12px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-ink"
            >
              {ending ? 'Ending session…' : <>Review with tutor <ArrowRight size={13} strokeWidth={2} /></>}
            </button>
            {endError && (
              <span role="alert" className="text-[12px] text-action-orange bg-action-orange/10 border border-action-orange/25 rounded-full px-3 py-1.5">
                {endError}
              </span>
            )}
          </div>
        )}

        <Toolbar onCheckWork={finish} />

        {/* Actions */}
        <div className="absolute bottom-5 right-6 z-20 flex items-center gap-2">
          {mounted && voice.supported && (
            <button
              onClick={() => (voice.active ? voice.stop() : voice.start())}
              className={cn(
                'rounded-full border px-4 py-2 text-[12px] font-semibold transition-colors',
                voice.active
                  ? 'border-focus-navy bg-focus-navy text-white'
                  : 'border-muted-gray bg-white text-ink hover:bg-reading-surface'
              )}
              style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
            >
              {voice.active
                ? voice.speaking
                  ? 'Listening…'
                  : 'Voice on — tap to stop'
                : 'Hands-free voice'}
            </button>
          )}
          {mode !== 'quiet' && (
            <button
              onClick={() => void requestHint()}
              className="rounded-full border border-muted-gray bg-white px-4 py-2 text-[12px] font-semibold text-ink hover:bg-reading-surface transition-colors"
              style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
            >
              Need a hint?
            </button>
          )}
          <button
            onClick={finish}
            className="rounded-full bg-focus-navy text-white px-4 py-2 text-[12px] font-semibold hover:opacity-80 transition-opacity"
          >
            I&apos;m done
          </button>
        </div>
      </main>

      {practiceCompleted && !done && (
        <div className="flex-shrink-0 border-t border-muted-gray px-6 py-2.5 text-[11.5px] text-slate-blue">
          You&apos;ve completed practice before — group chat is unlocked.
        </div>
      )}
    </div>
    </PhaseGate>
  );
}

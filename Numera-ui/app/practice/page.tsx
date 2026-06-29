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
import { StreamingTutorResponse, useStreamingVoiceTurn } from '@/hooks/useStreamingVoiceTurn';
import { DEMO_CONCEPT_ID, DEMO_QUESTION_ID, DEMO_PHASE } from '@/lib/api';
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
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const addTrailEntry = useNumeraStore((s) => s.addTrailEntry);
  const { goStage } = useFlowNav();
  const tutor = useDemoTutor();

  // Practice problem + hints for the placed topic.
  const demo = demoFor(currentTopicId);
  const QUESTION = demo.practiceQuestion;
  const HINTS = demo.practiceHints;

  // Backend context — fixed demo identifiers, matching the API documentation.
  const PHASE = DEMO_PHASE;
  const QUESTION_ID = DEMO_QUESTION_ID;

  const onStudentTranscript = useCallback(
    (transcript: string, confidence?: number) => {
      if (!transcript.trim()) return;
      addTranscriptMessage({ role: 'student', text: transcript });
      addTrailEntry({
        kind: 'answer',
        text: transcript,
        meta: confidence == null ? undefined : `STT ${(confidence * 100).toFixed(0)}%`,
      });
    },
    [addTranscriptMessage, addTrailEntry]
  );

  const onTutorResponse = useCallback(
    (response: StreamingTutorResponse) => {
      addTranscriptMessage({ role: 'ai', text: response.text });
      addTrailEntry({ kind: 'tutor', text: response.text });
    },
    [addTranscriptMessage, addTrailEntry]
  );

  const onVoiceError = useCallback(
    (message: string) => addTrailEntry({ kind: 'tutor', text: message }),
    [addTrailEntry]
  );

  const voice = useStreamingVoiceTurn({
    sessionId: tutor.sessionId,
    onStudentTranscript,
    onTutorResponse,
    onError: onVoiceError,
  });

  const [mode, setMode] = useState<AIMode>('observing');
  const [hintIndex, setHintIndex] = useState(0);
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
      void tutor.start(currentTopicId, 'VOICE', PHASE);
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

  const requestHint = () => {
    setMode('hint');
    void tutor.hint({
      concept_id: DEMO_CONCEPT_ID,
      question_id: QUESTION_ID,
      current_phase: PHASE,
      current_hint_count: hintIndex,
    });
    setHintIndex((i) => Math.min(i + 1, HINTS.length - 1));
  };

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
      <header className="flex items-center gap-4 px-6 py-3.5 border-b border-[#c8c8c8] flex-shrink-0">
        <div>
          <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a]">Independent practice</div>
          <div className="text-[16px] font-semibold text-[#1a1a1a] font-[Cambria_Math,Georgia,serif]">Solve {QUESTION}</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {/* AI mode indicator */}
          <span
            className={cn(
              'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px]',
              mode === 'quiet' ? 'border-[#c8c8c8] text-[#9a9a9a]' : 'border-[#9a9a9a] text-[#1a1a1a]'
            )}
          >
            {mode === 'quiet' ? <EyeOff size={14} strokeWidth={1.8} /> : <Eye size={14} strokeWidth={1.8} />}
            {mode === 'quiet' ? 'AI resting' : mode === 'hint' ? 'Hint ready' : 'AI observing'}
          </span>
          <button
            onClick={() => setMode(mode === 'quiet' ? 'observing' : 'quiet')}
            className="rounded-full border border-[#c8c8c8] px-3 py-1.5 text-[12px] font-semibold text-[#7a7a7a] hover:text-[#1a1a1a] hover:border-[#9a9a9a] transition-colors"
          >
            {mode === 'quiet' ? 'Resume AI' : "I'm stuck — give me space"}
          </button>
        </div>
      </header>

      {/* Canvas */}
      <main
        className="flex-1 relative min-w-0 bg-white overflow-hidden"
        style={{
          backgroundImage: 'linear-gradient(#eaeaea 1px, transparent 1px), linear-gradient(90deg, #eaeaea 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      >
        <div className="absolute inset-0 z-[1]">
          <DrawingCanvas onExportReady={handleExportReady} />
        </div>

        {/* Hint card — only when the observer offers one */}
        {mode === 'hint' && !done && (
          <div className="absolute top-5 left-6 z-20 max-w-sm flex items-start gap-3 bg-white border border-[#9a9a9a] rounded-xl px-4 py-3" style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}>
            <Lightbulb size={16} strokeWidth={1.8} className="flex-shrink-0 mt-0.5 text-[#1a1a1a]" />
            <div>
              <div className="text-[10px] tracking-widest uppercase text-[#9a9a9a] mb-0.5">Gentle hint</div>
              <p className="text-[12.5px] text-[#1a1a1a] leading-snug">{HINTS[hintIndex]}</p>
            </div>
          </div>
        )}

        {/* Quiet/distress reassurance */}
        {mode === 'quiet' && (
          <div className="absolute top-5 left-6 z-20 max-w-sm text-[12.5px] text-[#7a7a7a] italic">
            Take your time. I&apos;m here quietly when you&apos;re ready.
          </div>
        )}

        {/* Done confirmation → continue to Review & Feedback */}
        {done && (
          <div className="absolute top-5 left-6 z-20 flex items-center gap-2">
            <span className="flex items-center gap-2 bg-[#1a1a1a] text-white rounded-full px-4 py-2 text-[12px]">
              <Check size={14} strokeWidth={2} /> Practice saved — nice work.
            </span>
            <button
              onClick={() => goStage('review')}
              className="flex items-center gap-1.5 rounded-full border border-[#1a1a1a] bg-white px-4 py-2 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#1a1a1a] hover:text-white transition-colors"
            >
              Review with tutor <ArrowRight size={13} strokeWidth={2} />
            </button>
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
                  ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
                  : 'border-[#9a9a9a] bg-white text-[#1a1a1a] hover:bg-[#f4f4f4]'
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
              onClick={requestHint}
              className="rounded-full border border-[#9a9a9a] bg-white px-4 py-2 text-[12px] font-semibold text-[#1a1a1a] hover:bg-[#f4f4f4] transition-colors"
              style={{ boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }}
            >
              Need a hint?
            </button>
          )}
          <button
            onClick={finish}
            className="rounded-full bg-[#1a1a1a] text-white px-4 py-2 text-[12px] font-semibold hover:opacity-80 transition-opacity"
          >
            I&apos;m done
          </button>
        </div>
      </main>

      {practiceCompleted && !done && (
        <div className="flex-shrink-0 border-t border-[#eaeaea] px-6 py-2.5 text-[11.5px] text-[#9a9a9a]">
          You&apos;ve completed practice before — group chat is unlocked.
        </div>
      )}
    </div>
    </PhaseGate>
  );
}

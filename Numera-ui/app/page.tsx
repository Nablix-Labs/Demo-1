'use client';

/**
 * Numera — Lesson (the live tutoring session).
 *
 * The tool rail + media panel live in the root layout (persistent across
 * routes). This page contributes the lesson-specific surfaces: the slide
 * navigation strip and the drawing canvas.
 */

import { useCallback, useEffect, useState } from 'react';
import SlideDots from '@/components/SlideDots';
import CanvasStage from '@/components/Canvas';
import ContinuityCheck from '@/components/ContinuityCheck';
import FloatingMicButton from '@/components/FloatingMicButton';
import VisualCue from '@/components/VisualCue';
import { useFlowNav } from '@/lib/useFlowNav';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { useVoiceStream } from '@/hooks/useVoiceStream';
import { useWebSocket } from '@/hooks/useWebSocket';
import { demoFor } from '@/lib/demoContent';

// Voice turn transport. 'rest' (default): browser STT (useVoiceTurn) → REST +
// browser TTS. 'server': stream mic audio to the :8004 voice server, which does
// STT (Deepgram) + tutor + streamed TTS, all over the WS (see useVoiceStream /
// useWebSocket). Flip to 'server' once the voice server is validated end to end.
const VOICE_TRANSPORT = process.env.NEXT_PUBLIC_VOICE_TRANSPORT === 'server' ? 'server' : 'rest';
if (typeof window !== 'undefined' && !process.env.NEXT_PUBLIC_VOICE_TRANSPORT) {
  console.warn(
    "[voice] NEXT_PUBLIC_VOICE_TRANSPORT is unset — falling back to 'rest' (browser STT). Set it to 'server' for the streaming pipeline."
  );
}

export default function LessonPage() {
  const { goStage, currentTopicId } = useFlowNav();
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const setQuestionNumber = useNumeraStore((s) => s.setQuestionNumber);
  const setTranscript = useNumeraStore((s) => s.setTranscript);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);
  const micMuted = useNumeraStore((s) => s.micMuted);
  const setMicMuted = useNumeraStore((s) => s.setMicMuted);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const activeQuestionId = useNumeraStore((s) => s.activeQuestionId);
  const currentPhase = useNumeraStore((s) => s.currentPhase);

  // ── Live backend wiring (no-op unless NEXT_PUBLIC_API_BASE_URL is set) ──
  const tutor = useDemoTutor();
  const { submitVoiceTurn, start: startSession, apiEnabled, sessionId } = tutor;

  // Real-time channel for tutor canvas_draw (+ transcript/state/streamed audio).
  // No-ops unless NEXT_PUBLIC_WS_URL is set, so it's safe to mount before the WS
  // backend exists.
  const { sendAudioChunk, sendControl } = useWebSocket(sessionId ?? null);

  // Wait for the persisted store to rehydrate before writing lesson content —
  // writing earlier would persist default state over the saved placement.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (useNumeraStore.persist.hasHydrated()) setHydrated(true);
    return useNumeraStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  // Mock-mode content: load the placed topic's demo lesson. With a real backend
  // the session response drives the question/transcript instead (see below).
  useEffect(() => {
    if (!hydrated || apiEnabled) return;
    const demo = demoFor(currentTopicId);
    setQuestionText(demo.lessonQuestion);
    setQuestionNumber(demo.questionNumber);
    setTranscript(demo.transcript);
    clearTutorMarks(); // a new question starts with a clean tutor layer
  }, [hydrated, apiEnabled, currentTopicId, setQuestionText, setQuestionNumber, setTranscript, clearTutorMarks]);

  const onTurnEnd = useCallback(
    (transcript: string, confidence?: number) => {
      void submitVoiceTurn(
        transcript,
        {
          concept_id: activeConceptId,
          question_id: activeQuestionId,
          current_phase: currentPhase,
          hint_count: 0,
        },
        confidence
      );
    },
    [submitVoiceTurn, activeConceptId, activeQuestionId, currentPhase]
  );
  const voice = useVoiceTurn({ onTurnEnd });
  // Server transport: stream raw mic audio to the voice server instead of doing
  // browser STT + REST. The server drives transcript/tutor_response/audio over WS.
  const voiceStream = useVoiceStream({ onAudio: sendAudioChunk });

  // Start a backend session on lesson entry and let it drive the displayed
  // question/number/opening message. Mic starts muted so capture is opt-in.
  useEffect(() => {
    if (!hydrated || !apiEnabled || sessionId) return;
    setMicMuted(true);
    void startSession(activeConceptId, 'VOICE').then((rec) => {
      if (!rec) return;
      // CanvasStage renders the "Solve for x:" prefix itself, so strip it.
      setQuestionText(rec.current_question.replace(/^solve for\s*x\s*:?\s*/i, '').trim());
      setQuestionNumber(rec.question_number);
      setTranscript([{ role: 'ai', text: rec.message }]);
      clearTutorMarks();
      // Backend decides whether a supporting picture should be shown.
      useNumeraStore.getState().setVisualCueVisible(rec.show_visual_cue);
    });
  }, [hydrated, apiEnabled, sessionId, activeConceptId, startSession, setMicMuted, setQuestionText, setQuestionNumber, setTranscript, clearTutorMarks]);

  // Mic button drives real voice capture: unmuted → listen; muted → stop. In
  // 'rest' transport the browser detects turns + fires REST; in 'server' transport
  // we stream mic audio to the voice server and it drives the turn over the WS.
  // The voice server auto-connects to Deepgram on first audio and auto-responds
  // when it detects 1.5s silence (UtteranceEnd) -- no start/stop needed.
  const capture = VOICE_TRANSPORT === 'server' ? voiceStream : voice;
  useEffect(() => {
    if (!apiEnabled || !sessionId || !capture.supported) return;
    if (!micMuted) void capture.start();
    else capture.stop();
  }, [apiEnabled, sessionId, micMuted, capture]);

  return (
    <>
      <SlideDots />
      <CanvasStage />
      <ContinuityCheck />
      <FloatingMicButton />
      <VisualCue />
      {/* Guided lesson → independent practice. Top-right, to the left of the
          "Explain it back" chrome; the visual-cue card sits below (top-[84px]).
          A CSS glass pill — not the WebGL liquid-glass component, whose oversized
          region blocked the canvas and the cue card. */}
      <button
        onClick={() => goStage('practice', currentTopicId)}
        className="lg-glass fixed top-4 right-44 z-40 rounded-full px-5 py-2.5 text-ink text-[12px] font-semibold whitespace-nowrap cursor-pointer hover:brightness-[1.03] transition"
      >
        Finish lesson → Practice
      </button>
    </>
  );
}

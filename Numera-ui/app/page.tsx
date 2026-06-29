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
import { useFlowNav } from '@/lib/useFlowNav';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { demoFor } from '@/lib/demoContent';

export default function LessonPage() {
  const { goStage, currentTopicId } = useFlowNav();
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const setQuestionNumber = useNumeraStore((s) => s.setQuestionNumber);
  const setTranscript = useNumeraStore((s) => s.setTranscript);
  const micMuted = useNumeraStore((s) => s.micMuted);
  const setMicMuted = useNumeraStore((s) => s.setMicMuted);

  // Wait for the persisted store to rehydrate before writing lesson content —
  // writing earlier would persist default state over the saved placement.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (useNumeraStore.persist.hasHydrated()) setHydrated(true);
    return useNumeraStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  // Load the placed topic's lesson content into the live session.
  useEffect(() => {
    if (!hydrated) return;
    const demo = demoFor(currentTopicId);
    setQuestionText(demo.lessonQuestion);
    setQuestionNumber(demo.questionNumber);
    setTranscript(demo.transcript);
  }, [hydrated, currentTopicId, setQuestionText, setQuestionNumber, setTranscript]);

  // ── Live backend wiring (no-op unless NEXT_PUBLIC_API_BASE_URL is set) ──
  const tutor = useDemoTutor();
  const { submitVoiceTurn, start: startSession, apiEnabled, sessionId } = tutor;
  const onTurnEnd = useCallback(
    (transcript: string, confidence?: number) => {
      void submitVoiceTurn(
        transcript,
        {
          concept_id: currentTopicId,
          question_id: `${currentTopicId}_LESSON`,
          current_phase: 'GUIDED_PRACTICE',
          hint_count: 0,
        },
        confidence
      );
    },
    [submitVoiceTurn, currentTopicId]
  );
  const voice = useVoiceTurn({ onTurnEnd });

  // Start a backend session on lesson entry; mic starts muted so capture is
  // opt-in (tap the mic to talk — no surprise permission prompt on load).
  useEffect(() => {
    if (!hydrated || !apiEnabled || sessionId) return;
    setMicMuted(true);
    void startSession(currentTopicId, 'VOICE', 'GUIDED_PRACTICE');
  }, [hydrated, apiEnabled, sessionId, currentTopicId, startSession, setMicMuted]);

  // Mic button drives real voice capture: unmuted → listen + fire turns on
  // silence; muted → stop.
  useEffect(() => {
    if (!apiEnabled || !sessionId || !voice.supported) return;
    if (!micMuted) void voice.start();
    else voice.stop();
  }, [apiEnabled, sessionId, micMuted, voice]);

  return (
    <>
      <SlideDots />
      <CanvasStage />
      <ContinuityCheck />
      {/* Guided lesson → independent practice for this topic */}
      <button
        onClick={() => goStage('practice', currentTopicId)}
        className="fixed top-4 right-4 z-40 rounded-md bg-[#1a1a1a] text-white px-4 py-2 text-[12px] font-semibold hover:opacity-80 transition-opacity"
      >
        Finish lesson → Practice
      </button>
    </>
  );
}

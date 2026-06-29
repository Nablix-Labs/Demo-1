'use client';

/**
 * Numera — Lesson (the live tutoring session).
 *
 * The tool rail + media panel live in the root layout (persistent across
 * routes). This page contributes the lesson-specific surfaces: the slide
 * navigation strip and the drawing canvas.
 */

import { useEffect, useState } from 'react';
import SlideDots from '@/components/SlideDots';
import CanvasStage from '@/components/Canvas';
import ContinuityCheck from '@/components/ContinuityCheck';
import { useFlowNav } from '@/lib/useFlowNav';
import { useDemoTutor } from '@/hooks/useDemoTutor';
import { useNumeraStore } from '@/store/useNumeraStore';
import { demoFor } from '@/lib/demoContent';

export default function LessonPage() {
  const { goStage, currentTopicId } = useFlowNav();
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const setQuestionNumber = useNumeraStore((s) => s.setQuestionNumber);
  const setTranscript = useNumeraStore((s) => s.setTranscript);
  const { apiEnabled, sessionId, start } = useDemoTutor();

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

  useEffect(() => {
    if (!hydrated || !apiEnabled || sessionId) return;
    void start(currentTopicId, 'TEXT', 'GUIDED_PRACTICE');
  }, [apiEnabled, currentTopicId, hydrated, sessionId, start]);

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

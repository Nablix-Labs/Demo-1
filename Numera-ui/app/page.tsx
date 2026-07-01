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
import { StreamingTutorResponse, useStreamingVoiceTurn } from '@/hooks/useStreamingVoiceTurn';
import { playTutorAudio } from '@/lib/playTutorAudio';
import { DEMO_CONCEPT_ID, DEMO_PHASE } from '@/lib/api';
import { demoFor } from '@/lib/demoContent';

export default function LessonPage() {
  const { goStage, currentTopicId } = useFlowNav();
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const setQuestionNumber = useNumeraStore((s) => s.setQuestionNumber);
  const setTranscript = useNumeraStore((s) => s.setTranscript);
  const micMuted = useNumeraStore((s) => s.micMuted);
  const setMicMuted = useNumeraStore((s) => s.setMicMuted);
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const addTrailEntry = useNumeraStore((s) => s.addTrailEntry);

  // ── Live backend wiring (no-op unless NEXT_PUBLIC_API_BASE_URL is set) ──
  const tutor = useDemoTutor();
  const { start: startSession, apiEnabled, sessionId } = tutor;

  // Wait for the persisted store to rehydrate before writing lesson content —
  // writing earlier would persist default state over the saved placement.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    if (useNumeraStore.persist.hasHydrated()) setHydrated(true);
    return useNumeraStore.persist.onFinishHydration(() => setHydrated(true));
  }, []);

  // Mock-mode content: load the placed topic's demo lesson. With a real backend
  // the session response drives the question/transcript instead.
  useEffect(() => {
    if (!hydrated || apiEnabled) return;
    const demo = demoFor(currentTopicId);
    setQuestionText(demo.lessonQuestion);
    setQuestionNumber(demo.questionNumber);
    setTranscript(demo.transcript);
  }, [hydrated, apiEnabled, currentTopicId, setQuestionText, setQuestionNumber, setTranscript]);

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
      playTutorAudio(response.audio_base64, response.voice_text || response.text);
    },
    [addTranscriptMessage, addTrailEntry]
  );

  const onVoiceError = useCallback(
    (message: string) => addTrailEntry({ kind: 'tutor', text: message }),
    [addTrailEntry]
  );

  const voice = useStreamingVoiceTurn({
    sessionId,
    onStudentTranscript,
    onTutorResponse,
    onError: onVoiceError,
  });

  // Start a backend session on lesson entry and let it drive the displayed
  // question/number/opening message. Mic starts muted so capture is opt-in.
  useEffect(() => {
    if (!hydrated || !apiEnabled || sessionId) return;
    setMicMuted(true);
    void startSession(DEMO_CONCEPT_ID, 'VOICE', DEMO_PHASE).then((rec) => {
      if (!rec) return;
      // CanvasStage renders the "Solve for x:" prefix itself, so strip it.
      setQuestionText(rec.current_question.replace(/^solve for\s*x\s*:?\s*/i, '').trim());
      setQuestionNumber(rec.question_number);
      setTranscript([{ role: 'ai', text: rec.message }]);
    });
  }, [
    hydrated,
    apiEnabled,
    sessionId,
    startSession,
    setMicMuted,
    setQuestionText,
    setQuestionNumber,
    setTranscript,
  ]);

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

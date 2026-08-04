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
import { useRouter } from 'next/navigation';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import { useMicLevel } from '@/store/useMicLevel';
import { useDemoTutor, resetSessionStart, sessionStartError } from '@/hooks/useDemoTutor';
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
  const router = useRouter();
  const { currentTopicId } = useFlowNav();
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const setQuestionNumber = useNumeraStore((s) => s.setQuestionNumber);
  const setTranscript = useNumeraStore((s) => s.setTranscript);
  const clearTutorMarks = useNumeraStore((s) => s.clearTutorMarks);
  const micMuted = useNumeraStore((s) => s.micMuted);
  const setMicMuted = useNumeraStore((s) => s.setMicMuted);
  const activeConceptId = useNumeraStore((s) => s.activeConceptId);
  const currentPhase = useNumeraStore((s) => s.currentPhase);
  const updatePartialTranscript = useNumeraStore((s) => s.updatePartialTranscript);
  const voiceStatus = useNumeraStore((s) => s.voiceStatus);
  const beginListeningTurn = useNumeraStore((s) => s.beginListeningTurn);
  // True while tutor audio is genuinely playing — the echo gate below.
  const tutorSpeaking = useMicLevel((s) => s.aiSpeaking);

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
  const [startError, setStartError] = useState<string | null>(null);
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
          current_phase: currentPhase,
          hint_count: 0,
        },
        confidence
      );
    },
    [submitVoiceTurn, activeConceptId, currentPhase]
  );
  // Mirror live words into one evolving student bubble; submitVoiceTurn finalizes
  // it in place (commitPartialTranscript) so partial → final never jumps surfaces.
  const voice = useVoiceTurn({ onTurnEnd, onInterim: updatePartialTranscript });
  // Server transport: stream raw mic audio to the voice server instead of doing
  // browser STT + REST. The server drives transcript/tutor_response/audio over WS.
  const voiceStream = useVoiceStream({ onAudio: sendAudioChunk });

  // Start a backend session on lesson entry and let it drive the displayed
  // question/number/opening message. Mic starts muted so capture is opt-in.
  useEffect(() => {
    if (!hydrated || !apiEnabled || sessionId) return;
    setMicMuted(true);
    void startSession(activeConceptId, 'VOICE').then((rec) => {
      if (!rec) {
        // The lesson used to swallow this entirely, leaving the student on a
        // blank canvas with no question, no message and no way to retry — which
        // is what a failed session start actually looked like to a tester
        // (2026-07-28). Say what happened and offer a way out.
        setStartError(sessionStartError() ?? "We couldn't start your lesson just now.");
        return;
      }
      setStartError(null);
      // CanvasStage renders the "Solve for x:" prefix itself, so strip it.
      // Null when the session opened on a phase with no question of its own.
      setQuestionText((rec.current_question ?? '').replace(/^solve for\s*x\s*:?\s*/i, '').trim());
      setQuestionNumber(rec.question_number);
      setTranscript([{ role: 'ai', text: rec.message }]);
      clearTutorMarks();
      // Backend decides whether a supporting picture should be shown.
      useNumeraStore.getState().setVisualCueVisible(rec.show_visual_cue);
      // Open the student's first LISTENING turn (mints turn_id). Mic stays muted
      // until the student opts in; half-duplex gating does the rest.
      beginListeningTurn();
    });
  }, [hydrated, apiEnabled, sessionId, activeConceptId, startSession, setMicMuted, setQuestionText, setQuestionNumber, setTranscript, clearTutorMarks, beginListeningTurn]);

  // Mic capture is half-duplex (voice contract §12): it runs ONLY during the
  // student's LISTENING turn and while unmuted. During PROCESSING (request in
  // flight) and SPEAKING (tutor audio playing) the mic is closed, so the tutor's
  // own voice can never be captured and resubmitted as student speech (§13, test
  // 17/19). In 'server' transport the voice server owns turn detection, so gate
  // only on mute there.
  const capture = VOICE_TRANSPORT === 'server' ? voiceStream : voice;
  // Half-duplex applies to BOTH transports. It used to gate the server
  // transport on mute alone, on the reasoning that the voice server owns turn
  // detection — but turn detection is not echo suppression. The mic stayed open
  // through the tutor's reply, so the tutor's own audio went out of the speakers,
  // back in through the microphone, and Deepgram transcribed it as student
  // speech. UtteranceEnd then fired on the tutor's own words and produced
  // another answer, which produced another, and the replies piled up on top of
  // each other. That is what "long sentences are broken to many and answers are
  // generated individually, finally overlapping" is (Manjusha, 4 Aug).
  //
  // `aiSpeaking` is driven by the audio element actually advancing (see
  // startMouth in lib/tts.ts), so it clears on a stall as well as on a clean
  // end — the mic cannot be held shut by a reply that silently died.
  // Both signals clear inside the same funnel (TutorAudioStream.finish), so
  // they can never disagree — and gating on both means neither one being missed
  // can leave the tutor listening to itself.
  const listening = !micMuted && voiceStatus === 'listening' && !tutorSpeaking;

  // Depend on the individual callbacks, not on `capture`. The hooks return a
  // fresh object every render, so depending on it re-ran this effect on EVERY
  // render — a constant start/stop churn against an async getUserMedia, which
  // is what made it possible for the mic to end up live while muted.
  // start/stop are useCallback-stable, so this now runs only when the
  // listening decision actually changes.
  const { supported: captureSupported, start: startCapture, stop: stopCapture } = capture;
  useEffect(() => {
    if (!apiEnabled || !sessionId || !captureSupported) return;
    if (listening) void startCapture();
    else stopCapture();
  }, [apiEnabled, sessionId, listening, captureSupported, startCapture, stopCapture]);

  // Whatever happens, the mic must not outlive this screen.
  useEffect(() => stopCapture, [stopCapture]);

  // Navigation off this page is backend-phase-driven (usePhaseRouting follows
  // the session's current_phase), so the lesson chrome carries no manual
  // stage buttons.
  if (startError) {
    // An auth failure can't be fixed by retrying — the token is expired or
    // rejected. Send the student to log in (and clear the stale login so the
    // AuthGate doesn't bounce them straight back here). Screenshot report,
    // 31 Jul: "why is it opening this instead of login".
    const needsLogin = startError.includes('signed in');
    return (
      <main className="flex-1 min-w-0 flex items-center justify-center bg-white p-8" aria-label="Lesson unavailable">
        <div className="w-[420px] max-w-full text-center">
          <h1 className="text-[18px] font-semibold text-ink">Couldn&apos;t start your lesson</h1>
          <p className="text-[13px] text-slate-blue mt-2 leading-relaxed">{startError}</p>
          <button
            onClick={() => {
              resetSessionStart();
              setStartError(null);
              useNumeraStore.getState().clearSessionId();
              if (needsLogin) {
                useAuthStore.getState().logout();
                router.replace('/login'); // Next router applies the /app basePath
              }
            }}
            className="mt-5 inline-flex items-center gap-1.5 rounded-md border border-focus-navy px-4 py-2.5 text-[12.5px] font-semibold text-ink hover:bg-focus-navy hover:text-white transition-colors"
          >
            {needsLogin ? 'Log in' : 'Try again'}
          </button>
        </div>
      </main>
    );
  }

  return (
    <>
      <SlideDots />
      <CanvasStage />
      <ContinuityCheck />
      <FloatingMicButton />
      <VisualCue />
    </>
  );
}

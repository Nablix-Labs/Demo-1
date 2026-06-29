'use client';

/**
 * useDemoTutor — the integration layer between the REST client (lib/api.ts) and
 * the UI store. It drives the demo happy path against the live backend:
 *
 *   start → submit canvas (live OCR) → tutor reply → hint → end
 *
 * Every step is recorded into the in-memory interaction trail so the History
 * view can show the full session, even though the backend stores no transcript.
 *
 * Backend calls are gated on NEXT_PUBLIC_API_BASE_URL: when it's unset (local
 * UI-only runs) the hook is a no-op so the mock UX keeps working untouched.
 */
import { useCallback } from 'react';
import {
  startSession,
  submitCanvas,
  sendInteraction,
  requestHint,
  endSession,
  STUDENT_ID,
  type SessionRecord,
  type CanvasSubmissionResult,
  type InteractionResponse,
  type HintResponse,
} from '@/lib/api';
import { useNumeraStore } from '@/store/useNumeraStore';

const apiEnabled = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

/** Speak the tutor's reply (TTS output only — never used to decide content). */
function speak(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

/** Pull a human-readable message out of a normalised API error, if present. */
function errorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: { message?: string } } }).response?.data;
    if (data?.message) return data.message;
  }
  return err instanceof Error ? err.message : fallback;
}

export function useDemoTutor() {
  const sessionId = useNumeraStore((s) => s.sessionId);
  const setSessionId = useNumeraStore((s) => s.setSessionId);
  const setQuestionText = useNumeraStore((s) => s.setQuestionText);
  const canvasExporter = useNumeraStore((s) => s.canvasExporter);
  const addTranscriptMessage = useNumeraStore((s) => s.addTranscriptMessage);
  const addTrailEntry = useNumeraStore((s) => s.addTrailEntry);
  const clearTrail = useNumeraStore((s) => s.clearTrail);

  /** Begin a tutoring session for a concept. Returns the record, or null. */
  const start = useCallback(
    async (
      conceptId: string,
      mode: 'VOICE' | 'TEXT',
      initialPhase: string | null
    ): Promise<SessionRecord | null> => {
      if (!apiEnabled()) return null;
      const payload = {
        student_id: STUDENT_ID,
        concept_id: conceptId,
        interaction_mode: mode,
        ...(initialPhase === null ? {} : { initial_phase: initialPhase }),
      };
      try {
        const rec = await startSession(payload);
        clearTrail();
        setSessionId(rec.session_id);
        setQuestionText(rec.current_question);
        addTrailEntry({ kind: 'question', text: rec.current_question });
        return rec;
      } catch (err) {
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not start session.') });
        return null;
      }
    },
    [setSessionId, setQuestionText, addTrailEntry, clearTrail]
  );

  /** Send a typed student answer through the tutor pipeline. */
  const answer = useCallback(
    async (
      text: string,
      ctx: { concept_id: string; question_id: string; current_phase: string; hint_count: number }
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId) return null;
      addTrailEntry({ kind: 'answer', text });
      try {
        const res = await sendInteraction({
          session_id: sessionId,
          student_id: STUDENT_ID,
          interaction_type: 'ANSWER_SUBMISSION',
          input_source: 'TEXT',
          text_input: text,
          current_phase: ctx.current_phase,
          concept_id: ctx.concept_id,
          question_id: ctx.question_id,
          hint_count: ctx.hint_count,
        });
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        return res;
      } catch (err) {
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Tutor unavailable.') });
        return null;
      }
    },
    [sessionId, addTranscriptMessage, addTrailEntry]
  );

  /** Export the current canvas and submit it for live OCR + tutor feedback. */
  const submitCanvasWork = useCallback(async (): Promise<CanvasSubmissionResult | null> => {
    if (!apiEnabled() || !sessionId) return null;
    const png = canvasExporter?.();
    if (!png) {
      addTrailEntry({ kind: 'tutor', text: 'Nothing on the canvas to submit yet.' });
      return null;
    }
    try {
      const res = await submitCanvas(sessionId, png);
      addTrailEntry({
        kind: 'canvas',
        text: res.ocr.raw_ocr_text || res.ocr.detected_equation || 'Canvas submitted.',
        meta: `OCR ${(res.ocr.confidence * 100).toFixed(0)}%${
          res.ocr.needs_clarification ? ' · needs clarification' : ''
        }`,
      });
      addTranscriptMessage({ role: 'ai', text: res.tutor.tutor_message });
      addTrailEntry({
        kind: 'tutor',
        text: res.tutor.tutor_message,
        meta: res.tutor.evaluation,
      });
      return res;
    } catch (err) {
      addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Could not read the canvas.') });
      return null;
    }
  }, [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]);

  /** Ask for the next hint. */
  const hint = useCallback(
    async (
      ctx: { concept_id: string; question_id: string; current_phase: string; current_hint_count: number }
    ): Promise<HintResponse | null> => {
      if (!apiEnabled() || !sessionId) return null;
      try {
        const res = await requestHint({
          session_id: sessionId,
          student_id: STUDENT_ID,
          current_phase: ctx.current_phase,
          current_hint_count: ctx.current_hint_count,
          concept_id: ctx.concept_id,
          question_id: ctx.question_id,
        });
        addTranscriptMessage({ role: 'ai', text: res.hint });
        addTrailEntry({ kind: 'hint', text: res.hint, meta: `Hint ${res.hint_level}` });
        return res;
      } catch (err) {
        addTrailEntry({ kind: 'hint', text: errorMessage(err, 'No hint available.') });
        return null;
      }
    },
    [sessionId, addTranscriptMessage, addTrailEntry]
  );

  /**
   * Fire one completed voice turn to the backend: snapshot the canvas, then send
   * the transcript + canvas reference through /interaction, and speak the reply.
   * This is the function the turn-end detector calls when the student stops.
   */
  const submitVoiceTurn = useCallback(
    async (
      transcript: string,
      ctx: { concept_id: string; question_id: string; current_phase: string; hint_count: number },
      confidence?: number
    ): Promise<InteractionResponse | null> => {
      if (!apiEnabled() || !sessionId || !transcript.trim()) return null;
      addTrailEntry({ kind: 'answer', text: transcript });

      // Snapshot the canvas alongside the spoken turn (best-effort).
      let canvasSnapshotId: string | undefined;
      const png = canvasExporter?.();
      if (png) {
        try {
          const canvasRes = await submitCanvas(sessionId, png);
          canvasSnapshotId = canvasRes.submission_id;
          addTrailEntry({
            kind: 'canvas',
            text: canvasRes.ocr.raw_ocr_text || canvasRes.ocr.detected_equation || 'Canvas submitted.',
            meta: `OCR ${(canvasRes.ocr.confidence * 100).toFixed(0)}%`,
          });
        } catch {
          /* canvas is optional for a voice turn */
        }
      }

      try {
        const res = await sendInteraction({
          session_id: sessionId,
          student_id: STUDENT_ID,
          interaction_type: 'ANSWER_SUBMISSION',
          input_source: 'VOICE',
          voice_transcript: transcript,
          transcript_confidence: confidence,
          canvas_snapshot_id: canvasSnapshotId,
          current_phase: ctx.current_phase,
          concept_id: ctx.concept_id,
          question_id: ctx.question_id,
          hint_count: ctx.hint_count,
        });
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        speak(res.message_voice || res.message);
        return res;
      } catch (err) {
        addTrailEntry({ kind: 'tutor', text: errorMessage(err, 'Tutor unavailable.') });
        return null;
      }
    },
    [sessionId, canvasExporter, addTranscriptMessage, addTrailEntry]
  );

  /** End the session (best-effort). */
  const end = useCallback(async (): Promise<void> => {
    if (!apiEnabled() || !sessionId) return;
    try {
      await endSession(sessionId);
    } catch {
      /* session end is best-effort for the demo */
    }
  }, [sessionId]);

  return {
    apiEnabled: apiEnabled(),
    sessionId,
    start,
    answer,
    submitCanvasWork,
    submitVoiceTurn,
    hint,
    end,
  };
}

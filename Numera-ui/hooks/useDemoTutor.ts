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
  synthesizeTutorAudio,
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
import { useMicLevel } from '@/store/useMicLevel';
import { playTutorAudio } from '@/lib/playTutorAudio';

const apiEnabled = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

/**
 * True only when the student has actually drawn something. Guards against
 * sending blank canvas snapshots to the backend (and the live OCR provider) when
 * there's no activity. Read at call time so it doesn't re-subscribe the hook.
 */
function hasCanvasActivity(): boolean {
  return useNumeraStore.getState().items.length > 0;
}

/** Speak the tutor's reply (TTS output only — never used to decide content).
 *  Drives the 3D avatar's mouth via useMicLevel: onstart/onboundary open it in
 *  sync with the spoken words, onend/onerror close it. */
function speak(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) return;
  const mic = useMicLevel.getState();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onstart = () => useMicLevel.getState().setAiSpeaking(true);
  utterance.onboundary = () => useMicLevel.getState().markBoundary();
  utterance.onend = () => useMicLevel.getState().setAiSpeaking(false);
  utterance.onerror = () => useMicLevel.getState().setAiSpeaking(false);
  window.speechSynthesis.cancel();
  mic.setAiSpeaking(false); // reset before the new utterance starts
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

function logCanvasGeometryTrace(res: CanvasSubmissionResult): void {
  if (process.env.NODE_ENV === 'production') return;

  const regions = res.ocr.detected_regions.map((region) => ({
    step_id: region.step_id ?? '',
    text: region.text,
    x: region.x,
    y: region.y,
    w: region.w,
    h: region.h,
    center_x: region.x + region.w / 2,
    center_y: region.y + region.h / 2,
    confidence: region.confidence,
  }));
  const drawElements = (res.canvas_draw ?? []).flatMap((payload) =>
    payload.elements.map((element) => ({
      actionId: payload.actionId ?? '',
      kind: element.kind,
      id: element.id ?? '',
      x: element.x ?? '',
      y: element.y ?? '',
      w: element.w ?? '',
      h: element.h ?? '',
      from: element.from?.join(',') ?? '',
      to: element.to?.join(',') ?? '',
      text: element.text ?? element.tex ?? '',
    }))
  );

  console.groupCollapsed('[canvas-geometry] OCR regions -> canvas_draw');
  console.log({
    submission_id: res.submission_id,
    provider: res.ocr.provider,
    confidence_source: res.ocr.confidence_source,
  });
  console.table(regions);
  console.table(drawElements);
  console.log({ ocr: res.ocr, canvas_draw: res.canvas_draw ?? [] });
  console.groupEnd();
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
      mode: 'VOICE' | 'TEXT' = 'TEXT',
      initialPhase: string | null = null
    ): Promise<SessionRecord | null> => {
      if (!apiEnabled()) return null;
      try {
        const rec = await startSession({
          student_id: STUDENT_ID,
          concept_id: conceptId,
          interaction_mode: mode,
          ...(initialPhase === null ? {} : { initial_phase: initialPhase }),
        });
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
    const png = hasCanvasActivity() ? canvasExporter?.() : null;
    if (!png) {
      addTrailEntry({ kind: 'tutor', text: 'Nothing on the canvas to submit yet.' });
      return null;
    }
    try {
      const res = await submitCanvas(sessionId, png);
      logCanvasGeometryTrace(res);
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
      // Render tutor marks from the Check path, same as the voice path does.
      useNumeraStore.getState().clearTutorMarks();
      for (const payload of res.canvas_draw ?? []) {
        useNumeraStore.getState().applyCanvasDraw(payload);
      }
      const voiceText = res.tutor.tutor_message_voice || res.tutor.tutor_message;
      playTutorAudio(await synthesizeTutorAudio(voiceText), voiceText);
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

      // Console trace for backend integration debugging — shows the exact
      // payloads/responses the frontend exchanges on a voice turn.
      console.groupCollapsed(`%c[voice→backend] turn fired`, 'color:#7a5cc8;font-weight:bold');
      console.log('captured transcript:', transcript, confidence != null ? `(confidence ${confidence})` : '');

      // Snapshot the canvas alongside the spoken turn — only if the student
      // actually drew something (don't send blank canvases to the backend/OCR).
      let canvasSnapshotId: string | undefined;
      const png = hasCanvasActivity() ? canvasExporter?.() : null;
      if (png) {
        try {
          console.log('→ POST /canvas/submit', { session_id: sessionId, student_id: STUDENT_ID, snapshot_bytes: png.length });
          const canvasRes = await submitCanvas(sessionId, png);
          canvasSnapshotId = canvasRes.submission_id;
          logCanvasGeometryTrace(canvasRes);
          console.log('← /canvas/submit', { submission_id: canvasRes.submission_id, ocr: canvasRes.ocr, tutor: canvasRes.tutor });
          addTrailEntry({
            kind: 'canvas',
            text: canvasRes.ocr.raw_ocr_text || canvasRes.ocr.detected_equation || 'Canvas submitted.',
            meta: `OCR ${(canvasRes.ocr.confidence * 100).toFixed(0)}%`,
          });
          useNumeraStore.getState().clearTutorMarks();
          for (const payload of canvasRes.canvas_draw ?? []) {
            useNumeraStore.getState().applyCanvasDraw(payload);
          }
        } catch (err) {
          console.warn('✗ /canvas/submit failed:', err);
          /* canvas is optional for a voice turn */
        }
      } else {
        console.log('(no canvas content this turn)');
      }

      try {
        const interactionReq = {
          session_id: sessionId,
          student_id: STUDENT_ID,
          interaction_type: 'ANSWER_SUBMISSION' as const,
          input_source: 'VOICE' as const,
          voice_transcript: transcript,
          transcript_confidence: confidence,
          canvas_snapshot_id: canvasSnapshotId,
          current_phase: ctx.current_phase,
          concept_id: ctx.concept_id,
          question_id: ctx.question_id,
          hint_count: ctx.hint_count,
        };
        console.log('→ POST /interaction', interactionReq);
        const res = await sendInteraction(interactionReq);
        console.log('← /interaction', res);
        console.groupEnd();
        addTranscriptMessage({ role: 'ai', text: res.message });
        addTrailEntry({ kind: 'tutor', text: res.message });
        speak(res.message_voice || res.message);
        return res;
      } catch (err) {
        console.warn('✗ /interaction failed:', err);
        console.groupEnd();
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

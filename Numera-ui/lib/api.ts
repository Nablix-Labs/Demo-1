/**
 * Numera — Axios REST client
 *
 * Speaks the backend contract documented in `api-endpoint-readiness.docx`
 * (Owner: Chirudeva). Field names are snake_case to match the API exactly.
 * Frontend only calls these; it never owns tutoring logic.
 *
 * Demo notes from the contract:
 *  - No auth header required yet.
 *  - No student provisioning yet — use the fixed STUDENT_ID below.
 *  - Session state is in-memory on the backend and resets on reload; capture
 *    `session_id` from /session/start and reuse it for the whole run.
 */
import axios from 'axios';
import type { CanvasDrawPayload } from '@/store/useNumeraStore';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

/**
 * Fixed demo identifiers — must match the backend's documented test values
 * ("Fixed values used across all test cases"). The session_id itself is NOT
 * fixed here; it's minted by POST /session/start and read from the response.
 */
export const STUDENT_ID = 'ST001';
export const DEMO_CONCEPT_ID = 'ALG_LINEAR_ONE_STEP';
export const DEMO_QUESTION_ID = 'ALG_EQ_DIAG_001';
export const DEMO_PHASE = 'GUIDED_PRACTICE';

export const api = axios.create({
  baseURL: BASE,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Error shape ───────────────────────────────────────────────────────────────
// Every backend error returns this shape (never a raw stack trace).
export interface ApiError {
  error_code:
    | 'MISSING_FIELD'
    | 'INVALID_FORMAT'
    | 'INVALID_VALUE'
    | 'INPUT_TOO_LONG'
    | 'INVALID_JSON'
    | 'HTTP_ERROR'
    | 'INTERNAL_ERROR';
  message: string;
  field?: string;
  timestamp: string;
  request_id: string;
}

// ── Shared enums ──────────────────────────────────────────────────────────────
export type InteractionMode = 'VOICE' | 'TEXT';
export type InputSource = 'TEXT' | 'VOICE';
export type InteractionType =
  | 'ANSWER_SUBMISSION'
  | 'HINT_REQUEST'
  | 'CANVAS_SUBMISSION'
  | 'SESSION_START'
  | 'SESSION_END';

// ── Session record (returned by /session/start and GET /session/{id}) ─────────
export interface VoiceState {
  stream_active: boolean;
  current_turn: string;
  last_transcript_confidence: number | null;
  fallback_active: boolean;
}

export interface CanvasState {
  canvas_active: boolean;
  snapshot_id: string | null;
  ocr_result: OcrResult | null;
}

export interface SessionRecord {
  session_id: string;
  student_id: string;
  concept_id: string;
  interaction_mode: InteractionMode;
  current_phase: string;
  current_question: string;
  question_id: string;
  question_number: number;
  voice_state: VoiceState;
  canvas_state: CanvasState;
  ui_state: string;
  message: string;
  // UI flags on the session record (start / read). Stash them client-side after
  // /session/start. Note: the backend also echoes show_visual_cue / visual_cue on
  // /interaction responses (see InteractionResponse), so those update per turn.
  show_canvas: boolean;
  show_hint_button: boolean;
  show_visual_cue: boolean;
  show_scaffold_panel: boolean;
  scaffold_steps: unknown[];
  allow_text_input: boolean;
  allow_voice_input: boolean;
  hint_count: number;
  status: string;
  mode: string;
  canvas_submissions: CanvasSubmissionResult[];
}

// ── /session/start ────────────────────────────────────────────────────────────
export interface StartSessionPayload {
  student_id: string;
  concept_id: string;
  interaction_mode: InteractionMode;
}

/** POST /session/start */
export async function startSession(payload: StartSessionPayload) {
  const res = await api.post<SessionRecord>('/session/start', payload);
  return res.data;
}

// ── GET /session/{session_id} ─────────────────────────────────────────────────
/** GET /session/{session_id} — metadata + canvas submissions only (no transcript). */
export async function getSession(sessionId: string) {
  const res = await api.get<SessionRecord>(`/session/${sessionId}`);
  return res.data;
}

// ── /session/end ──────────────────────────────────────────────────────────────
/** POST /session/end — student_id must own the session (else 404). */
export async function endSession(sessionId: string, studentId: string = STUDENT_ID) {
  const res = await api.post<SessionRecord>('/session/end', {
    session_id: sessionId,
    student_id: studentId,
  });
  return res.data;
}

// ── /interaction (text) ───────────────────────────────────────────────────────
export interface InteractionPayload {
  session_id: string;
  student_id: string;
  interaction_type: InteractionType;
  input_source: InputSource;
  /** 1–500 chars for TEXT input. */
  text_input?: string;
  /** Use for VOICE input instead of text_input. */
  voice_transcript?: string;
  transcript_confidence?: number;
  /** Reference to a prior /canvas/submit so the turn carries the canvas work. */
  canvas_snapshot_id?: string;
  current_phase: string;
  concept_id: string;
  question_id: string;
  hint_count: number;
}

/** Supporting picture the backend asks the frontend to show (e.g. an equation
 *  block). `show` drives visibility; `cue_type` (e.g. 'EQUATION_BLOCK') can pick
 *  which visual to render. Matches the backend VisualCue model. */
export interface VisualCue {
  show: boolean;
  cue_type: string | null;
  description: string | null;
}

export interface InteractionResponse {
  session_id: string;
  student_id: string;
  current_phase: string;
  current_question: string;
  question_id: string | null;
  interaction_mode: InteractionMode;
  message: string;
  message_voice: string;
  hint_count: number;
  phase_indicator: string;
  /** Optional tutor drawing to render on the canvas alongside this reply. */
  canvas_draw?: CanvasDrawPayload[];
  /** Whether to show the supporting visual cue after this turn. The backend also
   *  sends the richer `visual_cue` object; prefer that when present. */
  show_visual_cue?: boolean;
  visual_cue?: VisualCue | null;
}

/** POST /interaction — core tutoring call. Requires a started, owned session. */
export async function sendInteraction(payload: InteractionPayload) {
  const res = await api.post<InteractionResponse>('/interaction', payload);
  return res.data;
}

// ── /hint/request ─────────────────────────────────────────────────────────────
export interface HintPayload {
  session_id: string;
  student_id: string;
  current_phase: string;
  current_hint_count: number;
  concept_id: string;
  question_id: string;
}

export interface HintResponse {
  session_id: string;
  student_id: string;
  hint_level: number;
  hint: string;
  response_strategy: string;
}

/** POST /hint/request */
export async function requestHint(payload: HintPayload) {
  const res = await api.post<HintResponse>('/hint/request', payload);
  return res.data;
}

// ── /canvas/submit (live OCR) ─────────────────────────────────────────────────
export interface OcrResult {
  raw_ocr_text: string;
  detected_equation: string;
  detected_steps: string[];
  final_answer: string;
  confidence: number;
  needs_clarification: boolean;
  latex: string;
  detected_shapes: unknown[];
  confidence_source: string;
  provider: string;
}

export interface TutorResult {
  evaluation: string;
  error_type: string;
  response_strategy: string;
  tutor_message: string;
  hint_level: number;
  answer_reveal_allowed: boolean;
}

export interface CanvasLatency {
  ocr_latency_ms: number;
  tutor_latency_ms: number;
  total_latency_ms: number;
}

export interface CanvasSubmissionResult {
  session_id: string;
  student_id: string;
  status: string;
  submission_id: string;
  snapshot_reference: string;
  ocr: OcrResult;
  tutor: TutorResult;
  latency: CanvasLatency;
  /** Tutor drawing actions (e.g. mark up the student's working). The backend
   *  sends a LIST of draw actions here, unlike the WS path (one per message). */
  canvas_draw?: CanvasDrawPayload[];
}

const PNG_DATA_URL_PREFIX = 'data:image/png;base64,';
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024; // 2 MB

/** Approximate decoded byte size of a base64 data URL. */
function base64ByteSize(dataUrl: string): number {
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

/**
 * POST /canvas/submit — the only endpoint hitting a live AI provider (OCR).
 * Requires a started, owned, non-ended session. Guards the snapshot client-side
 * to match the backend rules (422 on bad prefix/base64, 413 if > 2 MB).
 */
export async function submitCanvas(
  sessionId: string,
  snapshotDataUrl: string,
  studentId: string = STUDENT_ID
) {
  if (!snapshotDataUrl.startsWith(PNG_DATA_URL_PREFIX)) {
    throw new Error(`snapshot_data_url must start with "${PNG_DATA_URL_PREFIX}"`);
  }
  if (base64ByteSize(snapshotDataUrl) > MAX_SNAPSHOT_BYTES) {
    throw new Error('snapshot exceeds 2 MB limit');
  }
  const res = await api.post<CanvasSubmissionResult>('/canvas/submit', {
    session_id: sessionId,
    student_id: studentId,
    snapshot_data_url: snapshotDataUrl,
  });
  return res.data;
}

// ── Voice (documented thin wrappers) ──────────────────────────────────────────
export interface VoiceSessionStartResponse {
  session_id: string;
  student_id: string;
  stream_active: boolean;
  current_turn: string;
  voice_session_token: string;
  fallback_active: boolean;
}

/** POST /voice/session/start — marks the session voice-active (mock token). */
export async function startVoiceSession(
  sessionId: string,
  studentId: string = STUDENT_ID
) {
  const res = await api.post<VoiceSessionStartResponse>('/voice/session/start', {
    session_id: sessionId,
    student_id: studentId,
  });
  return res.data;
}

export interface VoiceTranscriptPayload {
  session_id: string;
  student_id: string;
  transcript: string;
  confidence: number;
  audio_duration_seconds: number;
  turn: 'STUDENT';
  timestamp: string;
}

/** POST /voice/transcript — routes a completed voice turn through /interaction. */
export async function sendVoiceTranscript(payload: VoiceTranscriptPayload) {
  const res = await api.post<InteractionResponse>('/voice/transcript', payload);
  return res.data;
}

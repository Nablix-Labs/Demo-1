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
import { useAuthStore } from '@/store/useAuthStore';
import { allowAnonTutorCalls } from '@/lib/runtimeConfig';

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? '';

/**
 * Placeholder bearer for students with no real login (see allowAnonTutorCalls).
 * The backend only checks that a bearer is present — it doesn't validate it —
 * so this is purely to get past that check during testing. It is NOT a
 * credential and grants nothing; drop it once sign-up performs a real login.
 */
export const ANON_ACCESS_TOKEN = 'anonymous-testing';

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

// Carry the real auth token (from POST /auth/login) on tutoring calls when one
// is present. /interaction, /hint, /canvas and /voice reject a request with no
// bearer at all (401), so when NEXT_PUBLIC_ALLOW_ANON_TUTOR is on we fall back
// to a placeholder for students who signed up without logging in — see
// allowAnonTutorCalls. Imported lazily via getState so there's no import cycle
// with the store.
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken ?? (allowAnonTutorCalls ? ANON_ACCESS_TOKEN : null);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
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

/** One graded question from the backend's per-question history. */
export interface QuestionOutcome {
  question: string;    // the question as served (from the RAG question bank)
  correct: boolean;    // final evaluation on this question
  attempts: number;    // attempts it took
  hint_level: number;  // highest hint level used on it
}

/** Summary of an ended session, shown on the Review screen. */
export interface SessionSummary {
  session_id: string;
  concept_id: string;
  question: string;
  attempts: number;    // canvas submissions the student made
  hints_used: number;  // hints requested during the session
  status: string;      // e.g. "ended"
  /** Real per-question outcomes; empty when the backend sent no history. */
  outcomes: QuestionOutcome[];
}

/** Backend per-question attempt record inside session_summary. */
interface QuestionAttemptRecord {
  question_id: string;
  question_text?: string;
  evaluation: string;
  hint_level_used: number;
}

/** The five-category review generated by the backend engine. Categories 2/3 and
 *  the hook are null when the session gave no evidence for them. */
export interface FiveCategorySummary {
  category_1_strength: string;
  category_2_first_error: string | null;
  category_3_pattern: string | null;
  category_4_next_practice: string;
  category_5_mastery: string;
}

/** Engine-generated session review returned by /session/end as `session_review`. */
export interface SessionReview {
  five_category_summary: FiveCategorySummary;
  student_facing_summary: string;
  b6_hook: string | null;
  call_to_action: 'NEXT_TOPIC' | 'CONTINUE_PRACTICE' | 'NONE';
  voice_delivery_order: string[];
  answer_reveal_allowed: false;
  guardrail_passed: true;
}

/** /session/end returns the ended record; the backend may also attach an explicit
 *  `summary` object and an `attempt_count` alongside the existing fields. */
export interface SessionEndResponse extends SessionRecord {
  attempt_count?: number;
  summary?: Partial<SessionSummary>;
  session_summary?: {
    per_question_history?: QuestionAttemptRecord[];
  };
  session_review?: SessionReview | null;
}

/** Collapse attempt records into one outcome per question, in served order. */
function toOutcomes(history: QuestionAttemptRecord[] | undefined): QuestionOutcome[] {
  const byQuestion = new Map<string, QuestionOutcome>();
  for (const attempt of history ?? []) {
    const entry = byQuestion.get(attempt.question_id) ?? {
      question: attempt.question_text || attempt.question_id,
      correct: false,
      attempts: 0,
      hint_level: 0,
    };
    entry.attempts += 1;
    entry.correct = attempt.evaluation === 'CORRECT';
    entry.hint_level = Math.max(entry.hint_level, attempt.hint_level_used ?? 0);
    byQuestion.set(attempt.question_id, entry);
  }
  return [...byQuestion.values()];
}

/**
 * Build the Review-screen summary from the /session/end response. Prefers an
 * explicit `summary` object when the backend sends one, otherwise derives it
 * from the ended record. Returns null when the response has no usable session
 * (so the caller can surface "no summary returned").
 */
export function toSessionSummary(res: SessionEndResponse | null | undefined): SessionSummary | null {
  if (!res || !res.session_id) return null;
  const s = res.summary;
  return {
    session_id: res.session_id,
    concept_id: s?.concept_id ?? res.concept_id,
    question: s?.question ?? res.current_question,
    attempts: s?.attempts ?? res.attempt_count ?? res.canvas_submissions?.length ?? 0,
    hints_used: s?.hints_used ?? res.hint_count ?? 0,
    status: s?.status ?? res.status,
    outcomes: toOutcomes(res.session_summary?.per_question_history),
  };
}

/** POST /session/end — student_id must own the session (else 404). */
export async function endSession(sessionId: string, studentId: string = STUDENT_ID) {
  const res = await api.post<SessionEndResponse>('/session/end', {
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
  // Voice turn-sync contract (§3, §5). Optional so the request still works before
  // the backend adds these fields.
  /** Unique id for this student turn; reused verbatim on a network retry. */
  turn_id?: string;
  /** tutor_turn_id of the last tutor reply — lets the backend reject stale turns. */
  previous_tutor_turn_id?: string | null;
  /** Always true for a submitted voice turn — only final transcripts are sent. */
  transcript_final?: boolean;
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
  // Voice turn-sync contract (§11). All optional — present once the backend
  // implements the contract; the frontend falls back sensibly when they're absent.
  /** Turn-level status: normal turns omit it; DUPLICATE_TURN / STALE_TURN /
   *  CLARIFICATION_REQUIRED signal the frontend to not treat this as a fresh reply. */
  status?: 'DUPLICATE_TURN' | 'STALE_TURN' | 'CLARIFICATION_REQUIRED';
  /** The student turn_id this reply corresponds to. */
  accepted_turn_id?: string | null;
  /** New tutor turn id — becomes previous_tutor_turn_id on the next request. */
  tutor_turn_id?: string | null;
  /** Backend's next conversational move (ASK_QUESTION, ADVANCE_TO_NEXT_QUESTION, …). */
  conversation_action?: string;
  /** Whether another student response is expected after this reply. */
  expects_student_response?: boolean;
  /** The kind of response expected (ANSWER, EXPLANATION, ACKNOWLEDGEMENT_OR_CONTINUE, …). */
  expected_student_response?: string;
  /** Whether voice input is currently permitted. */
  allow_voice_input?: boolean;
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
  /** Phase state after this submission — same contract as InteractionResponse. */
  phase_changed?: boolean;
  previous_phase?: string | null;
  current_phase?: string;
  current_question?: string;
  question_id?: string;
  ui_state?: string;
  recommended_entry_phase?: string | null;
  phase_transition_message?: string | null;
  phase_transition_voice?: string | null;
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
  submissionRole: 'STANDALONE_ATTEMPT' | 'VOICE_ATTACHMENT',
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
    submission_role: submissionRole,
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

/** POST /voice/tts — OpenAI speech for a tutor/review message. Returns base64
 *  MP3, or null for empty text. Throws (502) when the provider is down after
 *  retries — callers fall back to browser speechSynthesis. */
export async function synthesizeSpeech(text: string): Promise<string | null> {
  const res = await api.post<{ audio_base64: string | null }>('/voice/tts', { text });
  return res.data.audio_base64;
}

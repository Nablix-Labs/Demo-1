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
import type { QuestionAnchor } from '@/lib/questionAnchors';
import type { CanvasDrawPayload, CanvasStrokeSnapshot } from '@/store/useNumeraStore';
import type { TutorCanvasAction } from '@/store/useNumeraStore';
import type { CanvasEvent } from '@/lib/canvasMemory';
import { useAuthStore } from '@/store/useAuthStore';
import { allowAnonTutorCalls } from '@/lib/runtimeConfig';
import type { Phase3ResponseFields } from '@/lib/phase3';
import { recordDebugCall } from '@/lib/debugJson';

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

/**
 * The student id to send on tutoring calls: the logged-in student's own code
 * when the backend has given us one, else the fixed demo id.
 *
 * The fallback is a known-wrong value for any real student — student_model
 * checks that the code belongs to the JWT's user and answers 403
 * STUDENT_FORBIDDEN when it doesn't (issue #40). It stays until
 * LoginResponse.student_code exists; see the note there for why nothing on the
 * frontend can do better today.
 */
export function studentId(): string {
  return useAuthStore.getState().studentCode ?? STUDENT_ID;
}
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

/**
 * A rejected LOGIN ends the session — the student is sent back to sign in.
 *
 * Expiry can be noticed two ways: the client sees the token's `exp` pass (the
 * gate's own timer), or the server rejects it first — a token revoked, a key
 * rotated, or a clock that disagrees. Only the first was handled, so a student
 * whose login the server had already stopped accepting kept working against a
 * wall of 401s, each one surfacing as "we couldn't reach the tutor". That reads
 * as an outage rather than a finished session (Manjusha, 11 Aug: "if any issues
 * redirect the user to log in again").
 *
 * Clearing the token rather than navigating here: AuthGate already decides
 * where an unauthenticated student belongs, and it re-runs on any auth change.
 * A redirect from inside a network layer would race it and has no idea which
 * screens are reachable signed-out.
 *
 * Deliberately NOT fired for the anonymous placeholder. That bearer is 401'd by
 * student_model BY DESIGN when no one has logged in; treating it as an expiry
 * would bounce every anonymous tester to a login screen they were never on.
 */
api.interceptors.response.use(
  (response) => {
    // Dev-only JSON capture (lib/debugJson.ts). Filtered to tutoring calls, so
    // /voice/tts cannot overwrite the turn under inspection.
    recordDebugCall(
      `${response.config.method?.toUpperCase() ?? 'POST'} ${response.config.url ?? ''}`,
      safeRequestBody(response.config.data),
      response.data,
    );
    return response;
  },
  (error: unknown) => {
    const status = (error as { response?: { status?: number } })?.response?.status;
    // A FAILED call is the one a tester most needs to see, so capture it too.
    const failed = error as {
      config?: { method?: string; url?: string; data?: unknown };
      response?: { data?: unknown };
    };
    if (failed?.config) {
      recordDebugCall(
        `${failed.config.method?.toUpperCase() ?? 'POST'} ${failed.config.url ?? ''} (failed)`,
        safeRequestBody(failed.config.data),
        failed.response?.data ?? String(error),
      );
    }
    const realLogin = useAuthStore.getState().accessToken !== null;
    if (status === 401 && realLogin) {
      console.warn('[auth] the server rejected our login — signing out');
      useAuthStore.getState().logout();
    }
    return Promise.reject(error);
  },
);

/**
 * Axios hands back the request body already serialised. Parse it so the panel
 * can pretty-print it, and never let a malformed body break the capture.
 */
function safeRequestBody(data: unknown): unknown {
  if (typeof data !== 'string') return data;
  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}


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
    | 'INTERNAL_ERROR'
    | 'JOURNEY_VERSION_CONFLICT'
    // The bearer we sent was rejected — either by this backend or by a service it
    // calls on our behalf (e.g. student_model). Observed 2026-07-26 on the first
    // CORRECT_ATTEMPT of a session: the backend posts a progress event to
    // student_model, which unlike the tutoring endpoints actually validates the
    // token, so ANON_ACCESS_TOKEN gets a 401 INVALID_TOKEN back. Nothing on the
    // frontend can satisfy it — it needs a real login (see below).
    | 'AUTHENTICATION_FAILED';
  message: string;
  field?: string;
  timestamp: string;
  request_id: string;
}

/**
 * Student-facing copy for a backend error, chosen by `error_code`.
 *
 * The backend's own `message` is written for developers — the auth one reads
 * `student_model rejected request url=… status=401 body={"error_code":…}` — so it
 * must never be shown to a student. Anything we don't have specific copy for
 * falls back to the caller's generic message.
 */
/**
 * What to say when the VOICE SERVER gives up on a turn.
 *
 * The socket's `error` frame is not an HTTP error, so it never reaches
 * `studentFacingError` — it arrives as a bare string meant for a server log
 * ("Tutor unavailable", "upstream timeout"). Showing that to an eleven-year-old
 * is no better than showing nothing, and showing NOTHING is what we did: the
 * turn ended in silence with the status still reading "Listening…", so a
 * student sat waiting for a reply that was never coming.
 *
 * The engineer-facing text stays in the console; this is the sentence the
 * student gets. It says the tutor failed rather than implying the student did,
 * and it says what to do next.
 */
/**
 * What to say when the transcript was too unclear to answer.
 *
 * Not a failure — nothing broke, the words just did not come through. It has
 * to say so in a way an eleven-year-old cannot read as their fault, and it has
 * to ask for the one thing that helps: saying it again.
 */
export function transcriptUnclearMessage(): string {
  return "I didn't quite catch that. Could you say it once more?";
}

export function voiceTurnFailedMessage(serverMessage?: string): string {
  const raw = (serverMessage ?? '').toLowerCase();
  if (/auth|token|unauthor|forbidden/.test(raw)) {
    return 'Your session needs to be signed in again before I can answer that. Please log in and try once more.';
  }
  // Only wording that actually says TIMEOUT gets the timeout copy.
  //
  // `unavailable` and `upstream` used to land here too, and that was wrong:
  // "Tutor unavailable. Please try again." is the voice server's single
  // catch-all (streaming_server.py:689), sent for a timeout AND for every
  // non-200 the tutor call returns — a 409, a 500, anything. Mapping it to
  // "my side was too slow" described a plain backend rejection as slowness,
  // and read from a screenshot it looks like a frontend timeout, which is the
  // one place the fault never was (7 Aug). The generic line below is what an
  // unexplained failure gets; the real reason is in the console, from the
  // server's own message.
  if (/timeout|timed out/.test(raw)) {
    return 'I didn’t manage to answer that in time — my side was too slow. Say it again and I’ll have another go.';
  }
  return 'Something went wrong on my side and I couldn’t answer that. Say it again in a moment and I’ll try again.';
}

/**
 * Is this failure "the session you are using no longer exists"?
 *
 * Backend session state is in-memory and dies with the process, so a session id
 * that was perfectly good five minutes ago can start answering 404. That is the
 * price of persisting the id across reloads — and persisting it is worth paying
 * for, because NOT persisting it meant every reload opened a brand-new session
 * on a topic the student already had in progress. The Student Model then
 * resumed it and stamped routing_reason_code=SESSION_RESUMED, which the backend
 * cannot serialise, so every turn in that session 500s (7 Aug: 164 session
 * starts, 16 resumed).
 *
 * So: keep the id, and recognise when it has gone stale so the lesson can open
 * a fresh one instead of wedging on a session the backend has forgotten.
 */
export function isStaleSessionError(err: unknown): boolean {
  const res = (err as { response?: { status?: number; data?: { message?: string } } })?.response;
  if (res?.status !== 404) return false;
  return /session/i.test(res?.data?.message ?? '');
}

export function studentFacingError(err: unknown): string | null {
  const res = (err as { response?: { status?: number; data?: Partial<ApiError> } })?.response;
  // 409 on a session call means the Student Model already has this topic part
  // way through and will not hand back a fresh one. There is no resume path yet
  // (backend ask #3), so say what is actually true rather than blaming the
  // network and sending the student off retrying forever.
  const backendMessage = typeof res?.data?.message === 'string' ? res.data.message.trim() : '';
  const code = res?.data?.error_code;
  if (code === 'JOURNEY_VERSION_CONFLICT') {
    return 'Two submissions arrived together. Your work is safe—please press Check once more.';
  }
  if (res?.status === 409) {
    // Not every 409 is the resume case. On 2026-07-29 a guided-practice turn
    // came back 409 "Student Model did not return metadata for
    // ALG_1STEP_GP_F01" and the student was told their topic was already in
    // progress \u2014 a confident, wrong explanation that sent the team looking in
    // the wrong place. Only claim the resume case when the backend says so.
    if (!backendMessage || /already|in progress|resume/i.test(backendMessage)) {
      return 'You already have this topic in progress, and the tutor can\u2019t pick it back up yet. Ask the team to reset it for you.';
    }
    // A non-resume conflict is a service-contract failure. Backend messages can
    // contain adapter URLs, payloads, student IDs, or authored error codes; none
    // of that belongs in learner chat. Keep the diagnostic in the browser
    // console/network response and give the learner safe, actionable wording.
    return 'The tutor hit a problem on its side. Nothing you did\u2014please try again in a moment.';
  }
  switch (code) {
    case 'AUTHENTICATION_FAILED':
      return 'Your session needs to be signed in again before I can mark that. Please log in and retry.';
    case 'INTERNAL_ERROR':
      return 'The tutor hit a problem on its side. Please try that again in a moment.';
  }

  /**
   * Attribute the failure to whatever actually failed.
   *
   * Everything that reached this point used to return null, so the caller fell
   * back to "Sorry — I couldn't reach the tutor just now." That sentence
   * describes a network problem. A 500, 502 or 422 is not a network problem —
   * the request arrived and the server rejected or broke on it — and describing
   * it as unreachable sends whoever is testing to look at the frontend and the
   * wifi while the actual fault sits in a service log nobody opened.
   *
   * Naming the source is not about deflecting blame; it is about the next
   * person spending their time in the right place. A student still gets one
   * plain sentence and something to do.
   */
  const status = res?.status;

  // No response at all: request never completed. This is the only case where
  // "couldn't reach" is the true story.
  if (status === undefined) return null;

  // Timeouts first: 504 is also a 5xx, and "took too long" is more actionable
  // than "hit an error" — it tells the student retrying is worth it.
  if (status === 408 || status === 504) {
    return 'The tutor took too long to answer that one. Try sending it again.';
  }
  if (status >= 500) {
    return 'The tutor service hit an error on its side. Nothing you did — try again in a moment.';
  }
  if (status === 429) {
    return 'The tutor is handling a lot right now. Give it a few seconds and try again.';
  }
  if (status === 422) {
    // A contract mismatch between frontend and backend. The student cannot fix
    // it and retrying will fail identically, so say so rather than inviting a
    // loop of futile retries.
    return 'The tutor could not accept that submission — this one needs the team to look at it.';
  }
  if (status === 403) {
    return 'This session belongs to a different student, so the tutor will not mark it.';
  }
  if (status >= 400) {
    return backendMessage
      ? `The tutor could not process that. ${backendMessage}`
      : 'The tutor could not process that request.';
  }
  return null;
}

// ── Shared enums ──────────────────────────────────────────────────────────────
export type InteractionMode = 'VOICE' | 'TEXT';
/**
 * Where a turn came from. SYSTEM is not the student: it marks turns the platform
 * originated, which today means inactivity nudges. Keeping it distinct is what
 * stops a nudge being counted as a learner interaction anywhere downstream.
 */
export type InputSource = 'TEXT' | 'VOICE' | 'CANVAS' | 'CHOICE' | 'SYSTEM';
export type InteractionType =
  | 'ANSWER_SUBMISSION'
  | 'OPTION_SELECTED'
  | 'TEACH_BACK_SUBMISSION'
  | 'CLARIFICATION_REQUEST'
  // Replay the current explanation. Neither an answer nor a help escalation:
  // the backend returns attempt_increment 0 and emits no Student Model event
  // (Phase 2 handoff, Chirudeva — Explain Again).
  | 'EXPLAIN_AGAIN'
  // Non-learner events (Phase 2 handoff, Chirudeva — Inactivity events). Neither
  // is an attempt: they change no attempt count, STUCK count, support state,
  // scaffold, question or phase.
  //   INACTIVITY_NUDGE  — the client claims a nudge after server-validated silence
  //   NUDGE_PRESENTED   — acknowledgement that one was actually shown or spoken
  | 'INACTIVITY_NUDGE'
  | 'NUDGE_PRESENTED'
  | 'HELP_REQUEST'
  | 'SUPPORT_REPLAY'
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

// ── Student Model Schema 3.0 payload ─────────────────────────────────────────
// The backend forwards Saravanan's event response verbatim on the session record
// as `student_model_event`. It is the source of truth for the diagnostic
// question set and the orientation bundle — the session record's own
// `current_question` only ever carries the FIRST question of a set.
//
// Only the fields the UI renders are typed here; the real payload carries more
// (including `tutor_view`, which holds the answer key — never read it, and never
// surface it).

export interface SchemaQuestionOption {
  option_id: string;
  text: string;
}

export type QuestionType =
  | 'SINGLE_CHOICE'
  | 'SHORT_RESPONSE'
  | 'MULTI_PART_SHORT_RESPONSE'
  | 'CHOICE_WITH_EXPLANATION'
  | 'TRUE_FALSE_WITH_EXPLANATION';

export interface SchemaStudentQuestionView {
  question_text: string;
  question_type: QuestionType;
  /** Empty for free-response questions. */
  options: SchemaQuestionOption[];
  requires_student_response: boolean;
}

export interface SchemaQuestion {
  question_id: string;
  student_view: SchemaStudentQuestionView;
}

export interface SchemaQuestionSet {
  questions: SchemaQuestion[];
}

/** A concept video the Student Model wants played during orientation. */
export interface SchemaOrientationVideo {
  video_id: string;
  title: string;
  /** Null when the content exists but no file has been uploaded for it yet. */
  asset_url: string | null;
  duration_seconds: number | null;
}

export interface SchemaWorkedExampleStep {
  step_id: string;
  sequence_no: number;
  /** What to put on screen for this step. */
  screen_content: string | null;
  /** What the tutor says while it's shown. */
  narration_text: string | null;
}

export interface SchemaWorkedExample {
  worked_example_id: string;
  title: string;
  final_answer: string | null;
  student_answer_required: boolean;
  steps: SchemaWorkedExampleStep[];
}

export interface SchemaOrientationItem {
  sequence_no: number;
  content_type: 'ORIENTATION_VIDEO' | 'WORKED_EXAMPLE';
  video: SchemaOrientationVideo | null;
  worked_example: SchemaWorkedExample | null;
}

export interface SchemaOrientationBundle {
  target_micro_skill_ids: string[];
  /** Play/show in `sequence_no` order. */
  delivery_sequence: SchemaOrientationItem[];
}

export interface SchemaPhasePayload {
  phase: string;
  payload_type: string;
  question_set: SchemaQuestionSet | null;
  orientation_bundle: SchemaOrientationBundle | null;
  review_summary?: Record<string, unknown> | null;
}

export interface StudentModelEvent {
  phase_payload: SchemaPhasePayload | null;
  /** Workbook topic this session runs on, e.g. 'ALG-ORI-02'. */
  journey_state: { topic_id: string };
}

/** Flattened learner state the backend projects from the journey. */
export interface StudentModelState {
  current_phase: string;
  mastery_status: string;
  recommended_entry_phase: string | null;
  target_micro_skill_ids: string[];
  completed_micro_skill_ids: string[];
  current_question_id: string | null;
}

/**
 * The tutor's spoken/shown lines for Phase 1, authored backend-side in
 * `configs/phase1_tutor.yaml`. Never hardcode these in the frontend — the
 * wording is content, and the backend owns it (Sanya, 2026-07-28).
 */
export interface OrientationMessages {
  transition_to_orientation_message: string;
  shared_video_transition_message: string;
  before_video_message: string;
  video_to_worked_example_message: string;
  between_videos_message: string;
  worked_example_to_guided_message: string;
}

export interface SessionRecord {
  session_id: string;
  student_id: string;
  concept_id: string;
  interaction_mode: InteractionMode;
  current_phase: string;
  /** Null between phases — orientation has no question of its own. */
  current_question: string | null;
  question_type?: QuestionType | null;
  question_id: string | null;
  question_number: number;
  last_tutor_turn_id?: string | null;
  expected_student_response?: string;
  student_model_event?: StudentModelEvent | null;
  student_model_state?: StudentModelState | null;
  voice_state: VoiceState;
  canvas_state: CanvasState;
  ui_state: string;
  message: string;
  conversation_history?: Array<{
    role: 'user' | 'assistant' | 'system';
    content: string;
  }>;
  diagnostic_transition_message?: string | null;
  diagnostic_transition_messages?: string[];
  orientation_messages?: OrientationMessages | null;
  // UI flags on the session record (start / read). Stash them client-side after
  // /session/start. Note: the backend also echoes show_visual_cue / visual_cue on
  // /interaction responses (see InteractionResponse), so those update per turn.
  show_canvas: boolean;
  show_hint_button: boolean;
  show_visual_cue: boolean;
  /**
   * The cue currently on screen for the active guided question, or null.
   *
   * Distinct from `show_visual_cue` beside it, which on the RECORD is a
   * per-phase capability ("this phase may show cues") rather than "a cue has
   * been served" — at session start the backend sets it to
   * `flags[...] or visual_cue is not None`, so it is true for every guided turn.
   * This field is the one that means a cue is live: session_service nulls it
   * unless the phase is GUIDED_PRACTICE and the question has not changed, so
   * its PRESENCE is the signal.
   *
   * Read on resume, which is the only place it matters — see resumeSession.
   */
  active_visual_cue?: VisualCue | null;
  show_scaffold_panel: boolean;
  scaffold_steps: unknown[];
  allow_text_input: boolean;
  allow_voice_input: boolean;
  hint_count: number;
  status: string;
  mode: string;
  canvas_submissions: CanvasSubmissionResult[];
  inactivity_policy?: InactivityPolicyResponse;
}

export interface InactivityPolicyResponse {
  initial_idle_threshold_ms: number;
  cooldown_ms: number;
  max_nudges_per_tutor_turn: number;
  generated_nudge_rate_limit: number;
}

export interface NudgeDelivery {
  interaction_id: string;
  status: 'GENERATED' | 'PRESENTED';
  message: string;
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

// ── Reading the Schema 3.0 payload off a session record ──────────────────────

/**
 * Every diagnostic question the Student Model served, in order.
 *
 * `record.current_question` is only the first one, so anything that walks the
 * whole diagnostic must come through here. Empty when the session predates
 * Schema 3.0 or the backend sent no set — callers fall back to demo content.
 */
export function diagnosticQuestions(record: SessionRecord | null | undefined): SchemaQuestion[] {
  const payload = record?.student_model_event?.phase_payload;
  // `questions` is required by the contract, but a field vanishing from a
  // response has been a live outage here twice — and this one is read during
  // render, so an absent array replaces the whole check screen with the error
  // boundary mid-attempt. The two siblings below already read it defensively.
  return (payload?.question_set?.questions ?? []).filter((q) => q.student_view?.question_text);
}

/**
 * Where a question sits in the phase's question set, for the progress rail.
 *
 * The rail is supposed to show question progress (§2 of the Phase 2 spec), and
 * this is the only place the frontend can learn the denominator: the Student
 * Model ships the whole set on the session record, while `/interaction` replies
 * only ever name the current question.
 *
 * Returns `{ index: 0, total: 0 }` when the set is absent or the id isn't in it
 * — the rail treats a zero total as "nothing true to show yet" and hides,
 * rather than inventing a position.
 */
export function questionProgress(
  record: SessionRecord | null | undefined,
  questionId: string | null | undefined,
): { index: number; total: number } {
  const questions = record?.student_model_event?.phase_payload?.question_set?.questions ?? [];
  if (questions.length === 0) return { index: 0, total: 0 };
  const index = questions.findIndex((q) => q.question_id === questionId);
  return index < 0
    ? { index: 0, total: 0 }
    : { index, total: questions.length };
}

/**
 * The student's view of one question in the session's set.
 *
 * `/interaction` replies name the current question and its `question_type`, but
 * never carry its options — the Student Model ships those once, on the session
 * record. So anything that needs to RENDER a choice question has to come back
 * here and look it up by id.
 *
 * Null when the set is absent or the id isn't in it. Callers render the plain
 * question rather than inventing options.
 */
export function studentViewFor(
  record: SessionRecord | null | undefined,
  questionId: string | null | undefined,
): SchemaStudentQuestionView | null {
  if (!questionId) return null;
  const questions = record?.student_model_event?.phase_payload?.question_set?.questions ?? [];
  return questions.find((q) => q.question_id === questionId)?.student_view ?? null;
}

/** Question types where the student picks from `options` rather than free-typing. */
const CHOICE_TYPES: QuestionType[] = [
  'SINGLE_CHOICE',
  'CHOICE_WITH_EXPLANATION',
  'TRUE_FALSE_WITH_EXPLANATION',
];

/**
 * Should this question show its options?
 *
 * Both halves matter. A type that expects a choice but arrived with an empty
 * `options` array must fall back to free response — rendering an empty chooser
 * would leave the student with a question and no way to answer it.
 */
export function hasSelectableOptions(
  view: Pick<SchemaStudentQuestionView, 'question_type' | 'options'> | null | undefined,
): boolean {
  if (!view) return false;
  // `options` is required by the backend model, so the optional read is not for
  // today's contract — it is because a field disappearing from a response has
  // twice become a live outage here, and a chooser is not worth throwing the
  // whole screen for. Absent reads the same as empty: fall back to free response.
  return CHOICE_TYPES.includes(view.question_type) && (view.options?.length ?? 0) > 0;
}

/**
 * POST /session/{id}/review/complete — tells the Student Model the topic review
 * is finished.
 *
 * This is the event that advances the journey past Review
 * (`REVIEW_COMPLETED`, session_service.py:1389). `/session/end` does NOT emit it
 * — it only sets `status: "ended"` — so without this call a student who works
 * all the way through Phase 4 is never recorded as having done so.
 *
 * Safe to send after `/session/end`: ending a session leaves `current_phase`
 * alone, so the endpoint's "must be in REVIEW" guard still passes.
 *
 * Returns the updated record, or null on any failure. Null rather than a throw
 * because this is bookkeeping the student cannot act on: a 409 means the backend
 * does not consider us in Review, and neither that nor a network failure is a
 * reason to trap someone on the review screen.
 */
export async function completeReview(
  sessionId: string,
  studentId: string,
  turnId: string,
): Promise<SessionRecord | null> {
  try {
    const res = await api.post<SessionRecord>(`/session/${sessionId}/review/complete`, {
      student_id: studentId,
      turn_id: turnId,
    });
    return res.data;
  } catch (err) {
    const status = (err as { response?: { status?: number } })?.response?.status;
    console.warn(`[review] review/complete did not land (status ${status ?? 'none'}).`);
    return null;
  }
}

/** The orientation bundle for this session, or null when there isn't one. */
export function orientationBundle(
  record: SessionRecord | null | undefined,
): SchemaOrientationBundle | null {
  return record?.student_model_event?.phase_payload?.orientation_bundle ?? null;
}

/** Orientation items in the order the Student Model wants them delivered. */
export function orientationSequence(
  record: SessionRecord | null | undefined,
): SchemaOrientationItem[] {
  const bundle = orientationBundle(record);
  if (!bundle) return [];
  // Spread-of-undefined throws "not iterable", and this runs in the render
  // body of BackendOrientation rather than inside its load() try — so the
  // screen renders nothing and its retry button looks broken.
  return [...(bundle.delivery_sequence ?? [])].sort((a, b) => a.sequence_no - b.sequence_no);
}

/** Workbook topic code for this session (e.g. 'ALG-ORI-02'), or null. */
export function sessionTopicCode(record: SessionRecord | null | undefined): string | null {
  return record?.student_model_event?.journey_state?.topic_id ?? null;
}

/**
 * What to CALL this session's topic on screen, or null when we don't know.
 *
 * The only human-readable name the backend sends is the orientation video's
 * title — `journey_state.topic_id` is a code ('ALG-ORI-02'), which is not
 * something to show a student. Null is a real answer here and callers must
 * handle it: the alternative is what row 42 reported, a Review header
 * confidently labelled "Linear equations" on a session about something else,
 * because the screen fell back to mock content instead of admitting it had
 * nothing.
 */
export function sessionTopicTitle(record: SessionRecord | null | undefined): string | null {
  // The optional chain used to stop one link early. By review time this record
  // carries a Phase 4 payload, where a bundle without a delivery_sequence is
  // ordinary — and the throw landed on the final screen of the lesson.
  const video = orientationBundle(record)?.delivery_sequence
    ?.find((item) => item.video?.title)?.video;
  return video?.title?.trim() || null;
}

// ── Phase 0 → 1 lifecycle ────────────────────────────────────────────────────
// The backend derives micro-skills from the answers themselves, so the client
// never sends micro_skill_ids (Chirudeva, 2026-07-27).

/** One diagnostic answer, exactly as served. */
export interface DiagnosticAnswer {
  question_id: string;
  /** Must be non-empty — the backend rejects a blank response. */
  student_response: string;
}

/**
 * POST /session/{id}/diagnostic/complete — submits every answer at once and
 * returns the session in whichever phase the Student Model routed to:
 * CONCEPT_ORIENTATION when a gap was found, INDEPENDENT_PRACTICE when not.
 * 409 if the session isn't in DIAGNOSTIC (e.g. submitted twice).
 */
export async function completeDiagnostic(
  sessionId: string,
  student: string,
  answers: DiagnosticAnswer[],
) {
  const res = await api.post<SessionRecord>(`/session/${sessionId}/diagnostic/complete`, {
    student_id: student,
    answers,
  });
  return res.data;
}

/**
 * POST /session/{id}/orientation/start — asks for the worked example. Returns
 * the record with `orientation_bundle` populated. 409 unless the session is in
 * CONCEPT_ORIENTATION.
 */
export async function startOrientation(sessionId: string, student: string) {
  const res = await api.post<SessionRecord>(`/session/${sessionId}/orientation/start`, {
    student_id: student,
  });
  return res.data;
}

/**
 * POST /session/{id}/orientation/complete — marks orientation done and routes
 * on to Guided Practice. Must be called before leaving the phase, or the
 * Student Model never advances and the student re-enters orientation forever.
 *
 * The id arrays must match EXACTLY what the bundle served: anything missing is
 * a 409, and a duplicate or unrecognised id is a 422. So they are collected as
 * each piece of content actually finishes, never assumed.
 */
export async function completeOrientation(
  sessionId: string,
  student: string,
  completed: { videoIds: string[]; workedExampleIds: string[] },
) {
  const url = `/session/${sessionId}/orientation/complete`;
  try {
    const res = await api.post<SessionRecord>(url, {
      student_id: student,
      completed_video_ids: completed.videoIds,
      completed_worked_example_ids: completed.workedExampleIds,
    });
    return res.data;
  } catch (err) {
    // A backend from before the completion contract (PR #44) sets extra="forbid"
    // on OrientationPhaseRequest, so the id arrays come back as
    // 422 "Extra inputs are not permitted". Retry without them so the frontend
    // works against either version — otherwise deploying the two out of step
    // leaves nobody able to finish orientation. Remove once #44 is everywhere.
    if (!isExtraInputsRejected(err)) throw err;
    console.warn('[orientation] backend predates the completion contract — retrying without content ids');
    const res = await api.post<SessionRecord>(url, { student_id: student });
    return res.data;
  }
}

/** True when the backend rejected a field it doesn't know about (pre-#44). */
function isExtraInputsRejected(err: unknown): boolean {
  const res = (err as { response?: { status?: number; data?: Partial<ApiError> } })?.response;
  if (res?.status !== 422) return false;
  const field = res.data?.field ?? '';
  return /Extra inputs are not permitted/i.test(res.data?.message ?? '')
    && (field === 'completed_video_ids' || field === 'completed_worked_example_ids');
}

/** The content ids this session's orientation bundle requires, in order. */
export function requiredOrientationContent(record: SessionRecord | null | undefined): {
  videoIds: string[];
  workedExampleIds: string[];
} {
  const items = orientationSequence(record);
  return {
    videoIds: items.flatMap((i) => (i.content_type === 'ORIENTATION_VIDEO' && i.video ? [i.video.video_id] : [])),
    workedExampleIds: items.flatMap((i) =>
      i.content_type === 'WORKED_EXAMPLE' && i.worked_example ? [i.worked_example.worked_example_id] : []),
  };
}

// ── GET /session/{session_id} ─────────────────────────────────────────────────
/** GET /session/{session_id} — restore one student-owned session. */
export async function getSession(sessionId: string, student: string = studentId()) {
  const res = await api.get<SessionRecord>(`/session/${sessionId}`, {
    params: { student_id: student },
  });
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
    question: s?.question ?? res.current_question ?? '',
    attempts: s?.attempts ?? res.attempt_count ?? res.canvas_submissions?.length ?? 0,
    hints_used: s?.hints_used ?? res.hint_count ?? 0,
    status: s?.status ?? res.status,
    outcomes: toOutcomes(res.session_summary?.per_question_history),
  };
}

// ── Phase 4 Review ────────────────────────────────────────────────────────────
/**
 * The tutor-review payload the frontend renders (Phase 4 spec §8).
 *
 * `tutor_replays` and `student_insights` are Sanya's engine output copied
 * VERBATIM — the field names below are the ones already shipped in
 * `app/models/phase4_review.py`, not a parallel invention. Chiru's orchestration
 * (§6.10) validates that output, merges the authoritative backend evidence and
 * sends the result here, so this type is deliberately her schema plus only what
 * the screen cannot render without:
 *
 *   question_journey  the left rail (§8.4). Sanya never sees the CORRECT
 *                     questions, and the rail has to show the whole Phase 3
 *                     journey, so it cannot be derived from the replays.
 *   question_text     shown above the tutor board. Present on Chiru's
 *                     `ReplayItem` and dropped from her `TutorReplay`.
 *   work_artifact     §8.4 asks for the student's original work and a page
 *                     selector; her `TutorReplay` carries only `artifact_id`.
 *
 * Nothing here is computed client-side. §6.9 makes correctness, counts, mastery
 * and routing authoritative backend data, and a screen that recomputes any of
 * them is a second source of truth for the thing the spec says has one.
 */
/**
 * The student's submitted Phase 3 work.
 *
 * One PDF per attempt, not a list of page images. §5.4 of the specification
 * suggests Phase 4 "should primarily use the ordered page images", but the
 * shipped storage contract does not produce them: `WorkArtifactPersistResponse`
 * (nablix-backend/app/models/work_artifact.py, Chiru PR #156) returns
 * `artifact_id`, `pdf_url` and `page_count` only, and the binary is a single
 * combined PDF. Page references work through PDF page numbers instead, which is
 * what `first_error.student_page_no` indexes into.
 */
export interface Phase4WorkArtifact {
  artifact_id: string;
  page_count: number;
  pdf_url: string;
}

export interface Phase4FirstError {
  summary: string;
  /** Which page of the student's work the error is on. Null = not page-located. */
  student_page_no?: number | null;
}

export interface Phase4ReplayStep {
  sequence_no: number;
  /** Spoken. */
  narration: string;
  /** Written onto the tutor board. */
  tutor_write: string;
}

export interface Phase4Replay {
  review_item_id: string;
  question_id: string;
  attempt_id: string;
  artifact_id: string;
  question_text: string;
  first_error: Phase4FirstError;
  replay_steps: Phase4ReplayStep[];
  work_artifact: Phase4WorkArtifact;
}

/**
 * §7.6. `learning_pattern_summary` and `recent_improvement_summary` are
 * nullable BY DESIGN, not by omission: §7.6C says a single isolated occurrence
 * must produce null rather than a claim, and §8.9 says the section is then
 * hidden. Typing them as always-present would invite a screen that prints an
 * empty heading where the spec asks for silence.
 */
export interface Phase4StudentInsights {
  strength_summary: string;
  development_summary: string;
  learning_pattern_summary: string | null;
  recent_improvement_summary: string | null;
  next_practice_focus: string;
  personalised_notes: string[];
}

export type Phase4Evaluation = 'CORRECT' | 'INCORRECT' | 'WRONG';

/** One question from the Phase 3 journey, for the left rail. */
export interface Phase4JourneyEntry {
  question_id: string;
  question_text: string;
  evaluation: Phase4Evaluation;
  /**
   * The replay this question owns, or null when there is none.
   *
   * The link is explicit rather than matched on `question_id` because a single
   * question can be answered wrong, repaired in Phase 2 and answered again
   * (§3, Case C) — so question id alone does not identify an attempt, and
   * matching on it would attach one replay to two rows.
   */
  review_item_id: string | null;
}

export interface Phase4Review {
  student_id: string;
  topic_id: string;
  topic_title: string;
  topic_outcome: { mastery_status: string; recommended_next_action: string };
  question_journey: Phase4JourneyEntry[];
  /** Wrong Phase 3 submissions only (§3). Empty is normal, not an error (§8.8). */
  tutor_replays: Phase4Replay[];
  student_insights: Phase4StudentInsights;
  /** §5.8 `key_takeaways_json`. Falls back to `personalised_notes` — see keyTakeaways(). */
  key_takeaways?: string[];
}

/** POST /session/end — student_id must own the session (else 404). */
export async function endSession(sessionId: string, student: string = studentId()) {
  const res = await api.post<SessionEndResponse>('/session/end', {
    session_id: sessionId,
    student_id: student,
  });
  return res.data;
}


// ── /interaction (text) ───────────────────────────────────────────────────────
export interface InteractionCanvasState {
  snapshot_data_url: string;
  strokes: Array<{
    stroke_id: string;
    tool: 'pen' | 'pencil' | 'highlighter' | 'eraser';
    points: Array<{ x: number; y: number }>;
    width: number;
  }>;
  captured_at: string;
  /**
   * Ordered canvas memory for the current question (§8 of the V1-Hybrid spec).
   *
   * Sent alongside the snapshot, not instead of it: the snapshot is what OCR
   * reads, the log is what tells the tutor the order things appeared in — and
   * §7 asks that Sanya be called "with compact current canvas memory, not just
   * a flat screenshot".
   *
   * Optional so the request stays valid before the backend adds the field.
   */
  canvas_events?: CanvasEvent[];
}

export interface InteractionPayload {
  session_id: string;
  student_id: string;
  interaction_type: InteractionType;
  input_source: InputSource;
  /** 1–500 chars for TEXT input. */
  text_input?: string;
  /** Authoritative option identifier selected on a choice question. */
  selected_option_id?: string;
  /**
   * The exact authored wording of that option (revised handoff, frontend §1).
   *
   * Sent alongside the id, not instead of it: the id stays authoritative, and
   * this is what lets a wrong choice get a focused explanation rather than
   * generic fallback wording. Omitted when the option cannot be resolved — see
   * lib/selectedOption.
   */
  selected_option_text?: string;
  /** Use for VOICE input instead of text_input. */
  voice_transcript?: string;
  transcript_confidence?: number;
  /** Legacy reference to a prior /canvas/submit. */
  canvas_snapshot_id?: string;
  /** Frozen at voice-turn end so speech and board work are evaluated together. */
  canvas_state?: InteractionCanvasState;
  idle_duration_ms?: number;
  nudge_id?: string;
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
  cue_id?: string | null;
  cue_type: string | null;
  description: string | null;
  /**
   * Illustration for the cue. Optional because the backend does not forward it
   * yet — Sanya, 12 Aug 2026: "a later enhancement is to preserve and forward
   * asset_url in the backend visual-cue response". The client reads it now so
   * the image appears the moment it starts arriving, and renders text-only
   * until then. Values are sanitised by lib/cueAsset.
   */
  asset_url?: string | null;
  /** Structured cue actions (backend adapters.py:175). Not rendered yet — Phase 2 §6. */
  actions?: Array<Record<string, unknown>>;
}

/**
 * Guided-practice state the backend owns (Phase 2 handoff, Chirudeva —
 * "Response contract"). Every field is optional because none of them exist on
 * the backend yet; the frontend handling for each is written and inert, and
 * lights up the moment the field starts arriving.
 *
 * Nothing here is ever shown to a learner verbatim — component ids, error codes,
 * STUCK counts and reason codes are diagnostic, and handoff item 6 forbids
 * putting them on screen.
 */
export interface GuidedStateFields {
  guided_student_state?: 'CORRECT' | 'PARTIAL' | 'WRONG' | 'STUCK' | 'UNCLEAR' | null;
  active_teaching_objective?: {
    target_concept_ids?: string[];
    confirmed_concept_ids?: string[];
    missing_concept_ids?: string[];
  } | null;
  /** The component the student still has to resolve — drives AFFIRM-THEN-ISOLATE. */
  first_unresolved_concept_id?: string | null;
  selected_error_code?: string | null;
  evaluation_reason_code?: string | null;
  support_reason_code?: string | null;
  /**
   * Newly served support for THIS accepted turn; null when nothing new.
   * A bare SupportUsed value, not an object — matches the backend
   * (models/interaction.py: `SupportUsed | None`).
   */
  support_served_this_turn?: SupportLevel | null;
  /** Persisted currently-active support level. Defaults to 'NONE', never null. */
  active_support_level?: SupportLevel;
  /** Persisted maximum for the question's mapped micro-skills. */
  highest_support_used?: SupportLevel;
  /** Persisted scaffold + authorised current step, independent of this turn. */
  active_scaffold?: {
    scaffold_id: string;
    current_step_id: string;
    step_number: number;
    step_text: string;
    step_voice?: string | null;
    total_steps: number;
  } | null;
  guided_rescue?: {
    rescue_type: 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';
    micro_skill_id: string;
    parallel_example: {
      parallel_example_id: string;
      problem: string;
      worked_steps: string[];
      final_answer: string;
    } | null;
    tutor_solved: {
      explanation: string;
      final_answer: string;
      answer_steps: string[];
    } | null;
  } | null;
  consecutive_stuck_count?: number;
  /** Matches models/guided_learning.py:PrerequisiteRepair. */
  prerequisite_repair?: {
    prerequisite_micro_skill_ids: string[];
    reason_code: string;
  } | null;
  /**
   * Monotonic per accepted response, defaulting to 0.
   *
   * Only incremented on turns that mutate pedagogical state, so consecutive
   * responses CAN share a version — see lib/responseGate.ts for why that case
   * fails open rather than dropping the response.
   */
  interaction_state_version?: number;
}

/** The support ladder rung, as the backend spells it (SupportUsed). */
export type SupportLevel =
  | 'NONE'
  | 'HINT'
  | 'VISUAL_CUE'
  | 'SCAFFOLD'
  | 'PARALLEL_EXAMPLE'
  | 'TUTOR_SOLVED';

export interface InteractionResponse extends GuidedStateFields, Phase3ResponseFields {
  session_id: string;
  student_id: string;
  current_phase: string;
  /** Null when the new phase has no question of its own (e.g. orientation). */
  current_question: string | null;
  question_type?: QuestionType | null;
  question_id: string | null;
  /**
   * Spans inside `current_question` the tutor is pointing at (Chirudeva
   * handoff, 18 Aug 2026 §1). Optional and often empty — "nothing to point at
   * this turn" is the ordinary case, not a missing feature.
   *
   * The backend deliberately sends no coordinates and never will: we lay the
   * question out, so resolving a span to a position is ours. See
   * lib/questionAnchors.
   */
  question_anchors?: QuestionAnchor[];
  /**
   * How confident the backend is about WHERE on the canvas a symbol is
   * (Chirudeva handoff §2).
   *
   *   grounded   — the marks in `canvas_draw` are precise; render them.
   *   uncertain  — `canvas_draw` is empty ON PURPOSE. The tutor guides in text
   *                and voice instead. NOT an error: show no failure, and never
   *                fall back to marking something ourselves. The previous
   *                behaviour could circle the wrong symbol confidently, which
   *                is worse than not marking at all.
   *   null       — no canvas evidence in this turn.
   */
  localization_status?: 'grounded' | 'uncertain' | null;
  interaction_mode: InteractionMode;
  message: string;
  message_voice: string;
  /** Authored support held separately from the tutor's conversational reply. */
  support_message?: string | null;
  hint_count: number;
  phase_indicator: string;
  /** Optional tutor drawing to render on the canvas alongside this reply. */
  canvas_draw?: CanvasDrawPayload[];
  /** Coordinate-free Guided Practice tutor-layer actions. */
  tutor_canvas_actions?: TutorCanvasAction[];
  /** OCR from the frozen voice-turn canvas. */
  ocr?: OcrResult | null;
  /** Whether to show the supporting visual cue after this turn. The backend also
   *  sends the richer `visual_cue` object; prefer that when present. */
  show_visual_cue?: boolean;
  visual_cue?: VisualCue | null;
  // Voice turn-sync contract (§11). All optional — present once the backend
  // implements the contract; the frontend falls back sensibly when they're absent.
  /** Turn-level status: normal turns omit it; DUPLICATE_TURN / STALE_TURN /
   *  CLARIFICATION_REQUIRED signal the frontend to not treat this as a fresh reply. */
  status?:
    | 'DUPLICATE_TURN'
    | 'CLARIFICATION_REQUIRED'
    | 'NUDGE_SUPPRESSED';
  /** The student turn_id this reply corresponds to. */
  accepted_turn_id?: string | null;
  /** New tutor turn id — becomes previous_tutor_turn_id on the next request. */
  tutor_turn_id?: string | null;
  /** Authoritative tutor turn returned when a request used stale context. */
  expected_previous_tutor_turn_id?: string | null;
  /** Spoken/shown framing when this reply moves the student into a new phase.
   *  The canvas response documents its phase block as "same contract as
   *  InteractionResponse", but these two were only ever declared there. */
  phase_transition_message?: string | null;
  phase_transition_voice?: string | null;
  /**
   * The Student Model event behind this turn, including the question set.
   *
   * The backend has always sent this (interaction.py:172) and the client never
   * declared it, so the cached session record was only ever refreshed at
   * session start and resume. Everything looked up out of that record —
   * question options above all — therefore went stale the moment the backend
   * issued a NEW question set, which is exactly what a phase change does.
   */
  student_model_event?: StudentModelEvent | null;
  student_model_state?: StudentModelState | null;
  /** Backend's next conversational move (ASK_QUESTION, ADVANCE_TO_NEXT_QUESTION, …). */
  conversation_action?: string;
  /** Whether another student response is expected after this reply. */
  expects_student_response?: boolean;
  /** The kind of response expected (ANSWER, EXPLANATION, ACKNOWLEDGEMENT_OR_CONTINUE, …). */
  expected_student_response?: string;
  /** Whether voice input is currently permitted. */
  allow_voice_input?: boolean;
  inactivity_policy?: InactivityPolicyResponse;
  nudge_delivery?: NudgeDelivery | null;
  is_canvas_solution_correct?: boolean | null;
  advance_to_next_question?: boolean;
  feedback_type?: 'PRAISE' | 'HINT' | 'CORRECTION' | 'CLARIFICATION' | null;

  // ── Phase 2 scaffolding (frontend handoff, 2026-07-29) ────────────────────
  //
  // The backend serves ONE authorised scaffold step per turn. Deliberately no
  // field here for the step catalogue or for `expected_response`: the Student
  // Model holds those so the Tutor can grade, and §9 of the handoff forbids
  // them reaching the browser at all. `SessionRecord.scaffold_steps` is the old
  // whole-catalogue shape and must not be rendered — see ActiveScaffold below.
  //
  // All optional. They are inert until the Tutor Backend ships them, which is
  // why the panel below simply does not open when they are absent.
  /** Whether the support panel should be visible after this turn. */
  show_scaffold_panel?: boolean;
  /** Stable id of the running scaffold. */
  scaffold_id?: string | null;
  /** The one step the backend has authorised for display right now. */
  current_scaffold_step_id?: string | null;
  /** Human-readable position, e.g. 1. Display only. */
  scaffold_step_number?: number | null;
  /** The guiding question to show. */
  scaffold_step_text?: string | null;
  /** What to speak for this step; falls back to `message` when absent. */
  scaffold_step_voice?: string | null;
  /** Total steps — a progress indicator, NOT permission to reveal later ones. */
  total_scaffold_steps?: number | null;
}

export interface StaleTurnResponse {
  status: 'STALE_TURN';
  accepted_turn_id: null;
  expected_previous_tutor_turn_id: string | null;
  conversation_action: 'WAIT_FOR_STUDENT';
  attempt_increment: 0;
  retry_safe: false;
  message: string;
}

export type InteractionResult = InteractionResponse | StaleTurnResponse;

export function isStaleTurnResponse(
  response: InteractionResult,
): response is StaleTurnResponse {
  return response.status === 'STALE_TURN';
}

/**
 * The scaffold state the UI renders: exactly one step, never a catalogue.
 *
 * Derived from the fields above by `activeScaffold`, so there is one place that
 * decides whether a panel is open and what is in it. The frontend never
 * computes the next step — §2 of the handoff: the backend response is the only
 * instruction for the next visible state.
 */
export interface ActiveScaffold {
  scaffoldId: string;
  currentStepId: string;
  stepNumber: number;
  stepText: string;
  stepVoice: string | null;
  totalSteps: number;
}

/**
 * Read the authorised scaffold step off an interaction response.
 *
 * Returns null when the backend has not opened a panel, has closed it
 * (`show_scaffold_panel: false`), or has not sent a step to show — so a partial
 * or older response can never leave a stale step on screen.
 */
export function activeScaffold(res: InteractionResponse | null | undefined): ActiveScaffold | null {
  if (!res || res.show_scaffold_panel !== true) return null;
  const stepText = res.scaffold_step_text?.trim();
  const stepId = res.current_scaffold_step_id?.trim();
  if (!stepText || !stepId) return null;
  // The backend types these as `int = 0`, not null, so 0 is its "unset" value
  // (app/models/interaction.py:101,104 — landed in #46/#47 on 2026-07-29).
  // `?? 1` only catches null and would render "Step 0 of 0"; `||` treats 0 as
  // unset too. Total is floored at the step number so a partial payload can
  // never say "Step 2 of 1".
  const stepNumber = res.scaffold_step_number || 1;
  const totalSteps = Math.max(res.total_scaffold_steps || 1, stepNumber);
  return {
    scaffoldId: res.scaffold_id?.trim() || stepId,
    currentStepId: stepId,
    stepNumber,
    stepText,
    stepVoice: res.scaffold_step_voice?.trim() || null,
    totalSteps,
  };
}

/** POST /interaction — core tutoring call. Requires a started, owned session. */
export async function sendInteraction(payload: InteractionPayload): Promise<InteractionResult> {
  try {
    const res = await api.post<InteractionResponse>('/interaction', payload);
    return res.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      const data: unknown = error.response.data;
      if (
        typeof data === 'object'
        && data !== null
        && 'status' in data
        && data.status === 'STALE_TURN'
        && 'expected_previous_tutor_turn_id' in data
      ) {
        return data as StaleTurnResponse;
      }
    }
    throw error;
  }
}

// ── /hint/request — REMOVED ───────────────────────────────────────────────────
//
// The backend deleted this endpoint in the Schema 3.0 refactor on 3 Aug 2026
// (app/api/hint.py, hint_service.py and models/hint.py are all gone, and
// HINT_REQUEST was dropped from InteractionType). The client is removed rather
// than left in place, because a dead endpoint that still type-checks is an
// invitation to call it, and calling it 404s.
//
// Hints have not disappeared — they arrive as the turn message when
// `conversation_action` is GIVE_HINT. lib/supportLadder.ts reads them from
// there. An explicit "ask for the next support item" request needs a new
// endpoint; that is ask B1 in docs/PHASE2-GUIDED-BACKEND-ASKS.md.

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

export interface CanvasSubmissionResult extends Phase3ResponseFields {
  session_id: string;
  student_id: string;
  status: string;
  submission_id: string;
  snapshot_reference: string;
  /**
   * Both are NULL on a live Phase 3 submission (Sanya, 12 Aug 2026).
   *
   * That is by design, not a fault: Independent Practice is silent, so there is
   * no tutor message to send, and a submission the backend accepted without
   * reading the ink back has no OCR block either. Typing them as always-present
   * meant the client dereferenced both, threw, and reported an ACCEPTED
   * submission to the student as a failure.
   */
  ocr: OcrResult | null;
  tutor: TutorResult | null;
  latency: CanvasLatency;
  /** Tutor drawing actions (e.g. mark up the student's working). The backend
   *  sends a LIST of draw actions here, unlike the WS path (one per message). */
  canvas_draw?: CanvasDrawPayload[];
  guided_rescue?: GuidedStateFields['guided_rescue'];
  /** Phase state after this submission — same contract as InteractionResponse. */
  phase_changed?: boolean;
  previous_phase?: string | null;
  current_phase?: string;
  current_question?: string | null;
  question_id?: string | null;
  student_model_event?: StudentModelEvent | null;
  student_model_state?: StudentModelState | null;
  ui_state?: string;
  recommended_entry_phase?: string | null;
  phase_transition_message?: string | null;
  phase_transition_voice?: string | null;
  /** Full Guided Practice presentation fields, returned by /canvas/submit too. */
  message?: string;
  message_voice?: string;
  support_message?: string | null;
  show_visual_cue?: boolean;
  visual_cue?: VisualCue | null;
  question_type?: QuestionType | null;
  question_anchors?: QuestionAnchor[];
  tutor_canvas_actions?: TutorCanvasAction[];
  tutor_turn_id?: string | null;
  expected_previous_tutor_turn_id?: string | null;
  expected_student_response?: string;
  allow_voice_input?: boolean;
  interaction_state_version?: number | null;
  accepted_turn_id?: string | null;
  conversation_action?: string | null;
  next_expected_input?: string | null;
  requires_written_math_evidence?: boolean | null;
  write_instruction?: string | null;
  active_scaffold?: GuidedStateFields['active_scaffold'];
  show_scaffold_panel?: boolean;
  scaffold_id?: string | null;
  current_scaffold_step_id?: string | null;
  scaffold_step_number?: number | null;
  scaffold_step_text?: string | null;
  scaffold_step_voice?: string | null;
  total_scaffold_steps?: number | null;
}

const PNG_DATA_URL_PREFIX = 'data:image/png;base64,';
const MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024; // 2 MB

/** Approximate decoded byte size of a base64 data URL. */
function base64ByteSize(dataUrl: string): number {
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

function isUnitCoordinate(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 1;
}

export function canvasStrokesForSubmission(strokes: CanvasStrokeSnapshot[]): CanvasStrokeSnapshot[] {
  return strokes.flatMap((stroke) => {
    const points = stroke.points.filter(
      (point) => isUnitCoordinate(point.x) && isUnitCoordinate(point.y),
    );
    return points.length > 0 ? [{ ...stroke, points }] : [];
  });
}

export function canvasEventsForSubmission(canvasEvents: CanvasEvent[]): CanvasEvent[] {
  return canvasEvents.map((event) => {
    const bbox = event.bbox;
    if (
      bbox === null
      || (isUnitCoordinate(bbox.x)
        && isUnitCoordinate(bbox.y)
        && isUnitCoordinate(bbox.w)
        && isUnitCoordinate(bbox.h))
    ) {
      return event;
    }
    return { ...event, bbox: null };
  });
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
  /**
   * The turn this submission belongs to — REQUIRED in Independent Practice.
   *
   * `canvas_service.py:130` answers 422 "turn_id is required for Independent
   * Practice Canvas submissions" without it, so every Phase 3 canvas submission
   * was being rejected (Chiru, 12 Aug 2026). It is also what makes a retry safe:
   * the backend keys the submission on this id, so re-sending the same turn is
   * deduplicated instead of counting as a second attempt.
   *
   * Mint it with the store's `beginSubmissionTurn()` and reuse it verbatim on a
   * retry — a fresh id on a retry is a NEW submission, which is the bug this
   * field exists to prevent.
   */
  turnId: string,
  /**
   * The pen strokes behind the snapshot — REQUIRED, not optional.
   *
   * The image alone tells the backend WHAT was written; the strokes are what
   * let it say WHERE. `canvas_service` turns them into spatial tokens, and
   * without tokens the tutor can read a wrong answer but cannot circle the
   * symbol that is wrong — it can only mark the whole line (Sanya, 13 Aug 2026).
   *
   * Required for the same reason `turnId` is: this call sent no strokes for
   * weeks while the field existed on both sides and every submission validated
   * cleanly, because the omission is invisible to a type that allows it. The
   * voice path has always sent them via `canvas_state.strokes`; the Check
   * button had not.
   */
  strokes: CanvasStrokeSnapshot[],
  /**
   * Ordered canvas memory for the current question — REQUIRED (§8, §9).
   *
   * Strokes say where the ink is; this says what happened and in what order,
   * including the work the student rubbed out. §13 asks that the tutor "does
   * not repeat already-completed reasoning steps", and nothing in a snapshot or
   * a stroke list can tell it which steps those were.
   *
   * Required for the same reason `strokes` is — the field the caller may omit
   * is the field that silently stops being sent.
   */
  canvasEvents: CanvasEvent[],
  student: string = studentId()
) {
  if (!snapshotDataUrl.startsWith(PNG_DATA_URL_PREFIX)) {
    throw new Error(`snapshot_data_url must start with "${PNG_DATA_URL_PREFIX}"`);
  }
  if (base64ByteSize(snapshotDataUrl) > MAX_SNAPSHOT_BYTES) {
    throw new Error('snapshot exceeds 2 MB limit');
  }
  const res = await api.post<CanvasSubmissionResult>('/canvas/submit', {
    session_id: sessionId,
    student_id: student,
    turn_id: turnId,
    snapshot_data_url: snapshotDataUrl,
    // Field name and shape match `CanvasSubmitRequest.strokes` (canvas.py:108)
    // and are the same objects the voice turn already sends.
    // Canvas coordinates are stored in screen pixels. A viewport resize can
    // leave historical off-screen points outside the current normalised stage;
    // they are not visible in this snapshot and must not invalidate the whole
    // submission. The remaining visible points still provide spatial evidence.
    strokes: canvasStrokesForSubmission(strokes),
    // Not yet on `CanvasSubmitRequest`, and safe to send: the model does not
    // forbid extra fields, so it is ignored until Chirudeva adds it (§12
    // stage 2). Sending it now means the day the field lands, the data is
    // already arriving — no second frontend release in the middle of his work.
    canvas_events: canvasEventsForSubmission(canvasEvents),
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
  student: string = studentId()
) {
  const res = await api.post<VoiceSessionStartResponse>('/voice/session/start', {
    session_id: sessionId,
    student_id: student,
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

/** POST /voice/tts — tutor speech for a tutor/review message. Returns base64
 *  MP3, or null for empty text. Throws (502) when the provider is down after
 *  retries — callers fall back to browser speechSynthesis.
 *
 *  `provider`/`voice` carry the testing-only voice variant (lib/voiceOptions.ts).
 *  VoiceTTSRequest accepts both and falls back to the VOICE_TTS_PROVIDER /
 *  VOICE_TTS_VOICE env vars, so they're omitted entirely when nothing is
 *  selected and the default request shape is unchanged. */
export async function synthesizeSpeech(
  text: string,
  opts?: { provider?: string | null; voice?: string | null },
): Promise<string | null> {
  const res = await api.post<{ audio_base64: string | null }>('/voice/tts', {
    text,
    ...(opts?.provider ? { provider: opts.provider } : {}),
    ...(opts?.voice ? { voice: opts.voice } : {}),
  });
  return res.data.audio_base64;
}

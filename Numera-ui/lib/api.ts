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
import type { Phase3ResponseFields } from '@/lib/phase3';

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
  if (!payload?.question_set) return [];
  return payload.question_set.questions.filter((q) => q.student_view?.question_text);
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
  return CHOICE_TYPES.includes(view.question_type) && view.options.length > 0;
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
  return [...bundle.delivery_sequence].sort((a, b) => a.sequence_no - b.sequence_no);
}

/** Workbook topic code for this session (e.g. 'ALG-ORI-02'), or null. */
export function sessionTopicCode(record: SessionRecord | null | undefined): string | null {
  return record?.student_model_event?.journey_state?.topic_id ?? null;
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
    question: s?.question ?? res.current_question ?? '',
    attempts: s?.attempts ?? res.attempt_count ?? res.canvas_submissions?.length ?? 0,
    hints_used: s?.hints_used ?? res.hint_count ?? 0,
    status: s?.status ?? res.status,
    outcomes: toOutcomes(res.session_summary?.per_question_history),
  };
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
}

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
  /** Legacy reference to a prior /canvas/submit. */
  canvas_snapshot_id?: string;
  /** Frozen at voice-turn end so speech and board work are evaluated together. */
  canvas_state?: InteractionCanvasState;
  selected_option_id?: string;
  phase3_submission_confirmed?: boolean;
  phase3_submission_kind?: 'CANVAS' | 'CHOICE';
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
  cue_type: string | null;
  description: string | null;
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
  interaction_mode: InteractionMode;
  message: string;
  message_voice: string;
  hint_count: number;
  phase_indicator: string;
  /** Optional tutor drawing to render on the canvas alongside this reply. */
  canvas_draw?: CanvasDrawPayload[];
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
  ocr: OcrResult;
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
  phase3Submission: boolean,
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
    snapshot_data_url: snapshotDataUrl,
    submission_role: submissionRole,
    phase3_submission_confirmed: phase3Submission || undefined,
    phase3_submission_kind: phase3Submission ? 'CANVAS' : undefined,
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

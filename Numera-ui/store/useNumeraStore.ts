/**
 * Numera — Global Zustand store
 *
 * The frontend is a DISPLAY + INTERACTION layer only.
 * All tutoring logic and session decisions live in the backend.
 * This store holds only UI-relevant state derived from backend events.
 */
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { LearningPhase } from '@/lib/phases';
import type { FlowStage } from '@/lib/flow';
import { TOPICS } from '@/lib/topics';
import { isPhase3 } from '@/lib/phase3';
import {
  DEMO_CONCEPT_ID,
  studentViewFor,
  hasSelectableOptions,
  type ActiveScaffold,
  type QuestionType,
  type SchemaQuestionOption,
  type SessionRecord,
  type SessionReview,
  type SessionSummary,
} from '@/lib/api';
import { uid } from '@/lib/uid';
import type { SupportRung } from '@/lib/supportLadder';
import { EMPTY_APPLIED, type AppliedState } from '@/lib/responseGate';
import type { InactivityPolicy } from '@/lib/inactivity';
import {
  appendCanvasEvent,
  clearCanvasEvents,
  itemBBox,
  supersedeCanvasEvents,
  tutorActionType,
  tutorElementBBox,
  tutorElementText,
  type CanvasEvent,
  type CanvasEventContext,
  type CanvasEventDraft,
  type CanvasSize,
} from '@/lib/canvasMemory';

// A turn id is an idempotency key, so it must remain unique across reloads and
// reconnects. A module-local counter restarted at TURN-0001 after refresh and
// collided with the backend's cached turns from the same session.
const nextTurnId = (): string => `TURN-${uid()}`;

/**
 * Tutor panel width.
 *
 * The default is the width the panel was designed at. The minimum is where the
 * chat bubbles stop being readable; below it the panel should be collapsed, not
 * shrunk, which is what the collapse control is for.
 *
 * The maximum is a share of the window rather than a fixed number of pixels,
 * because the thing actually being protected is the canvas — a student writing
 * maths needs room whatever monitor they are on. Half the window is generous
 * and still leaves the canvas usable.
 */
export const PANEL_WIDTH_DEFAULT = 234;
export const PANEL_WIDTH_MIN = 200;
const PANEL_WIDTH_MAX_FRACTION = 0.5;
/** Fallback for SSR and tests, where there is no window to measure. */
const PANEL_WIDTH_MAX_FALLBACK = 560;

export function panelWidthMax(viewportWidth?: number): number {
  const w = viewportWidth ?? (typeof window === 'undefined' ? undefined : window.innerWidth);
  if (w === undefined) return PANEL_WIDTH_MAX_FALLBACK;
  // Never below the minimum: on a narrow window the fraction alone would invert
  // the bounds and clamp() would then throw the two ends the wrong way round.
  return Math.max(PANEL_WIDTH_MIN, Math.round(w * PANEL_WIDTH_MAX_FRACTION));
}

/**
 * Clamped on write, not on read.
 *
 * A width dragged wide on an external monitor and restored on a laptop would
 * otherwise leave the canvas a sliver, and the student would have to go find
 * the drag handle before they could work. Rounded because a fractional width
 * makes the panel's inner text land on half-pixels and blur.
 */
export function clampPanelWidth(px: number, viewportWidth?: number): number {
  if (!Number.isFinite(px)) return PANEL_WIDTH_DEFAULT;
  return Math.round(Math.min(Math.max(px, PANEL_WIDTH_MIN), panelWidthMax(viewportWidth)));
}

// ─── Types ────────────────────────────────────────────────────────────────────

export type SessionState =
  | 'idle'
  | 'state_1'   // Warm-up
  | 'state_2'   // Explanation
  | 'state_3'   // Step-by-step
  | 'state_4'   // Student work
  | 'state_5';  // Review

export type DrawingTool = 'pen' | 'pencil' | 'highlighter' | 'eraser' | 'shape' | 'ruler';
export type ShapeKind = 'rect' | 'circle' | 'triangle';
export type EraserMode = 'stroke' | 'object';
export type CanvasGrid = 'plain' | 'dots' | 'grid-sm' | 'grid' | 'grid-lg' | 'lines';

export type InputMode = 'voice' | 'text' | 'canvas';

/**
 * A single committed item on the drawing canvas.
 *  - stroke:   freehand pen / pencil / eraser path (eraser uses destination-out)
 *  - line:     straight line drawn with the ruler tool
 *  - rect:     rectangle (shape tool)
 *  - ellipse:  circle / ellipse (shape tool)
 *  - triangle: triangle (shape tool)
 * `size` is the stroke width in px.
 */
export type DrawnItem =
  | { id: string; kind: 'stroke'; tool: 'pen' | 'pencil' | 'highlighter' | 'eraser'; points: number[]; color: string; size: number }
  | { id: string; kind: 'line'; points: number[]; color: string; size: number }
  | { id: string; kind: 'rect'; x: number; y: number; w: number; h: number; color: string; size: number }
  | { id: string; kind: 'ellipse'; x: number; y: number; w: number; h: number; color: string; size: number }
  | { id: string; kind: 'triangle'; points: number[]; color: string; size: number };

export interface CanvasStrokeSnapshot {
  stroke_id: string;
  tool: 'pen' | 'pencil' | 'highlighter' | 'eraser';
  points: Array<{ x: number; y: number }>;
  width: number;
}

export interface CanvasSnapshot {
  snapshotDataUrl: string;
  strokes: CanvasStrokeSnapshot[];
  capturedAt: string;
}

export type CanvasExporter = () => CanvasSnapshot | null;

/**
 * Tutor-drawn element, rendered on a separate (non-erasable) canvas layer.
 * Geometry is NORMALISED 0–1 relative to canvas width/height, so the backend
 * never needs to know the pixel size — the renderer multiplies by the live
 * stage dimensions. Matches the `canvas_draw` message contract.
 */
export type TutorElementKind =
  | 'text' | 'math' | 'line' | 'arrow' | 'rect' | 'ellipse' | 'freehand' | 'highlight';

export interface TutorElement {
  id: string;
  kind: TutorElementKind;
  x?: number; y?: number; w?: number; h?: number;     // normalised 0–1
  from?: [number, number]; to?: [number, number];     // normalised endpoints
  points?: number[];                                  // normalised x,y pairs
  text?: string; tex?: string;                        // text / KaTeX content
  color?: string; strokeWidth?: number; size?: number;
}

/** Payload the backend/LLM sends to draw on the canvas. */
export interface CanvasDrawPayload {
  author?: 'tutor';
  actionId?: string;
  mode?: 'append' | 'replace';
  elements: Array<Omit<TutorElement, 'id'> & { id?: string }>;
}

// Idempotency for tutor draw commands: a command may be re-delivered (e.g. on a
// WebSocket reconnect). We drop any actionId we've already applied. Module-level
// (not React state) since it's plumbing, not UI.
const seenDrawActionIds = new Set<string>();

/**
 * Which turn and question a canvas event belongs to (§8: "links canvas activity
 * to the conversation turn and active problem").
 *
 * Read off live state at emit time rather than passed in by callers — a
 * component that drew before the ids updated would otherwise file the event
 * against the previous question, which is precisely the mix-up ordered memory
 * exists to prevent.
 */
function eventContext(s: { currentTurnId: string | null; activeQuestionId: string | null }): CanvasEventContext {
  return { turnId: s.currentTurnId, questionId: s.activeQuestionId };
}

export interface TranscriptMessage {
  id: string;
  role: 'ai' | 'student';
  text: string;
  partial?: boolean; // true while still transcribing
  /**
   * The student is still mid-turn — more speech may join this message.
   *
   * Streaming ASR emits a FINAL at every speech-final point, which in practice
   * means every breath the student takes. Committing each one as its own
   * message turned one spoken answer into six bubbles ("Okay. I think the
   * answer for this question is" / "option b." / "Again, plus four." / …,
   * Manjusha 6 Aug). How many bubbles a turn becomes is a presentation
   * decision, so it is made here rather than blamed on the transcriber.
   */
  open?: boolean;
  timestamp: number;
}

/**
 * One entry in the current session's interaction trail.
 *
 * The backend stores no transcript and resets on reload (see
 * api-endpoint-readiness.docx), so the frontend keeps its own ordered record of
 * what happened this run — question shown, student answer, canvas/OCR result,
 * tutor reply, hint. Kept in memory only (never persisted), matching the store's
 * policy for ephemeral session state.
 */
export type TrailKind = 'question' | 'answer' | 'canvas' | 'tutor' | 'hint';

export interface TrailEntry {
  id: string;
  kind: TrailKind;
  text: string;
  meta?: string; // short detail, e.g. OCR confidence, hint level, evaluation
  timestamp: number;
}

/** A participant in a group/live session. Cursor is normalised 0–1. */
export interface Participant {
  id: string;
  name: string;
  color: string;
  cursor: { x: number; y: number } | null;
  isLocal?: boolean;
}

// ─── Group Challenge Mode ───────────────────────────────────────────────────
// Each student works privately; the AI observes all canvases and drives the
// shared board. These types model what the student's client renders.

/** A live AI comment shown on the shared board. */
export interface ChallengeComment {
  id: string;
  text: string;
  tone: 'observe' | 'encourage' | 'hint';
  timestamp: number;
}

/** AI selection of work to display on the shared board. */
export interface Spotlight {
  kind: 'good' | 'mistake' | 'solution';
  caption: string;
  studentName: string | null; // named for good work, null = anonymous
}

/** Auto-review status of the student's private canvas. */
export type ReviewStatus = 'idle' | 'reviewing' | 'reviewed';

export interface NumeraState {
  // Session
  sessionId: string | null;
  sessionState: SessionState;
  activeSlide: number;
  totalSlides: number;

  // Question displayed on canvas (backend-controlled)
  questionText: string;
  questionNumber: number;

  // Active question the tutor session runs on. Sent as concept_id/question_id;
  // changing it restarts the session so the backend serves that equation.
  //
  // Null when the current phase has no question — orientation is the case that
  // matters. The backend answers with question_id: null there, and carrying the
  // previous id forward left the diagnostic question on screen through the whole
  // orientation and attached the next turn to a question that was already done.
  activeConceptId: string;
  activeQuestionId: string | null;

  // How the current question expects to be answered, and the choices it offers.
  //
  // The Student Model sends both — `question_type` on the interaction reply,
  // `options` once on the session record — and until now the frontend read
  // neither, so every question rendered as free response no matter what it was.
  // A CHOICE_WITH_EXPLANATION question showed its text and nothing to choose
  // from.
  //
  // Empty rather than null when there are no options, so callers can render the
  // list unconditionally. `selectedOptionId` is the student's current pick; it
  // is deliberately NOT persisted (see partialize) — a choice belongs to the
  // attempt being made, not to the browser.
  questionType: QuestionType | null;
  questionOptions: SchemaQuestionOption[];
  selectedOptionId: string | null;

  // Tutoring phase the session is in. Seeded from the session's current_phase
  // and advanced from each interaction response's current_phase — the value we
  // send back on the next turn, so the backend can drive phase transitions.
  currentPhase: string;

  // Latest session record from the backend, kept whole so the screens can read
  // the Schema 3.0 payload off it (diagnosticQuestions / orientationSequence in
  // lib/api.ts) rather than each one re-fetching the session. Null in mock mode.
  backendSession: SessionRecord | null;

  // Summary of the ended session (attempts, hints used, …) returned by
  // /session/end. Shown on the Review screen. Ephemeral — never persisted.
  sessionSummary: SessionSummary | null;

  // Engine-generated review from /session/end (five categories, student-facing
  // summary, call to action). Shown verbatim on the Review screen.
  sessionReview: SessionReview | null;

  // Voice
  micMuted: boolean;
  // Half-duplex turn phase (voice contract §12). LISTENING = mic open for the
  // student; PROCESSING = request in flight, mic closed; SPEAKING = tutor audio
  // playing, mic closed; WAITING/IDLE = no active turn.
  voiceStatus: 'idle' | 'listening' | 'speaking' | 'processing' | 'waiting';
  // Turn identifiers (voice contract §3). currentTurnId is minted when the
  // student's LISTENING turn begins and travels on the /interaction request;
  // lastTutorTurnId is the tutor_turn_id of the latest backend reply, sent back
  // as previous_tutor_turn_id so the backend can reject stale/duplicate turns.
  currentTurnId: string | null;
  lastTutorTurnId: string | null;
  // Backend-owned gating (voice contract §11/§12): whether another student turn
  // is expected and whether voice input is currently allowed. The frontend only
  // opens the mic when both are true.
  expectsStudentResponse: boolean;
  allowVoiceInput: boolean;
  /**
   * The tutor's last turn failed and nothing has replaced it.
   *
   * A failed turn leaves `expectsStudentResponse` true — deliberately, so the
   * student can retry — and leaves `lastTutorTurnId` pointing at the last turn
   * that DID work. To the inactivity controller that is indistinguishable from a
   * student who has gone quiet on a live question, so it nudges them: the tutor
   * errors twice, the student stops, and the third bubble asks "what is the
   * first thing you would try?" (10 Aug). They already tried. Twice.
   *
   * Cleared by `setTutorTurn`, which is the only place a real tutor turn is
   * established, so recovery needs no separate signal.
   */
  tutorTurnFailed: boolean;

  // Visual cue card — supporting guidance shown when the AI Engine flags a
  // mistake. `visualCueType` is the backend cue_type (picks which card renders);
  // `visualCueDescription` is the backend's instructional text. Session-scoped.
  /**
   * The single scaffold step the backend has authorised, or null.
   *
   * Holds `ActiveScaffold` — one step, no catalogue, no expected answer — so
   * there is nothing tutor-only in student-visible state (Phase 2 handoff §9).
   * Never persisted: support state belongs to the live session, and a stale
   * step restored on reload would contradict the Student Model.
   */
  activeScaffold: ActiveScaffold | null;
  /**
   * The authorised hint currently ON SCREEN, or null.
   *
   * Distinct from `lastHintText`, which is the record kept for the "Need help?"
   * replay and for `hint_count` — that one has to survive being dismissed. This
   * is only what the student can see right now, so dismissing it clears this
   * and leaves the record alone.
   *
   * It exists because a hint had no UI of its own in Guided Practice: it was
   * appended to the transcript as an ordinary tutor bubble, so it looked exactly
   * like the tutor talking and vanished entirely when the panel was collapsed
   * (Sanya, 13 Aug 2026: "hints are gone noww").
   *
   * Never persisted — support state belongs to the live turn, and a hint
   * restored on reload would contradict the Student Model.
   */
  visibleHint: string | null;
  visualCueVisible: boolean;
  /**
   * The backend's `cue_id` (e.g. 'VC-T01-ADD-NOT-MULTIPLY'), when it sent one.
   *
   * This is the cue's IDENTITY, and the only reliable evidence that what we are
   * holding is an authored visual cue at all. `cue_type` is null on the real
   * Topic 1 cues (Sanya, 13 Aug), so it can answer neither question.
   */
  visualCueId: string | null;
  visualCueType: string | null;
  visualCueDescription: string | null;
  /** Illustration for the cue, when the backend sent a usable asset_url. */
  visualCueAssetUrl: string | null;
  /** Structured cue actions as sent. Stored whole; not rendered yet (Phase 2 §6). */
  visualCueActions: Array<Record<string, unknown>> | null;

  // Support ladder (§6 of the Phase 2 spec). `supportShown` is the highest rung
  // revealed for the CURRENT question, so "Need help?" climbs rather than
  // repeating itself; `lastHintText` is the tutor message from the most recent
  // GIVE_HINT turn, which is the only hint source left now that /hint/request
  // has been removed from the backend. Both reset when the question changes.
  supportShown: SupportRung | null;
  lastHintText: string | null;
  /**
   * The question whose Phase 3 attempt has been accepted and locked.
   *
   * Keyed by question id, not a flag: the lock must survive a reconnect and a
   * duplicate reply (replaying it changes nothing) and must lift for a rescue
   * question by virtue of its different id — Phase 3 spec §3.3/§3.4.
   */
  phase3LockedQuestionId: string | null;
  /**
   * A tutor line that has been shown but not yet spoken.
   *
   * Set when one screen hands the student to another: the phase-entry line
   * belongs to the screen being ENTERED, so the departing screen cannot speak
   * it — starting speech on a route that is unmounting is how this codebase
   * previously ended up with two tutor voices at once. The arriving screen
   * claims it, speaks it, and clears it.
   */
  pendingTutorSpeech: string | null;

  // Ordering guard for interaction responses (Phase 2 handoff item 2). Holds the
  // highest interaction_state_version applied and the accepted_turn_ids already
  // rendered at it, so an out-of-order reply cannot overwrite newer state and a
  // cached replay is applied exactly once. Never persisted — it describes what
  // is on screen right now, not the lesson.
  appliedResponse: AppliedState;

  // Server-owned inactivity policy. Null until the backend sends one, and that
  // is what keeps nudging off: the handoff requires explicit validated config
  // with no model defaults, so a locally invented threshold would interrupt the
  // first student who paused to think on a number nobody agreed.
  inactivityPolicy: InactivityPolicy | null;

  // Transcript
  transcript: TranscriptMessage[];

  // Current-session interaction trail (in-memory; backend keeps no transcript)
  interactionTrail: TrailEntry[];

  // Canvas / drawing
  activeTool: DrawingTool;
  shapeKind: ShapeKind;        // which shape the shape tool draws
  eraserMode: EraserMode;      // freehand rub vs tap-to-delete an object
  strokeColor: string;
  strokeWidth: number;
  items: DrawnItem[];          // committed student items
  undone: DrawnItem[];         // student redo stack
  tutorElements: TutorElement[]; // AI-tutor marks (separate, non-erasable layer)

  /**
   * Ordered canvas memory — §8 of the Phase 2 V1-Hybrid spec.
   *
   * Append-only for the life of a question, so it records the ORDER in which
   * the maths appeared and not just what survived. `items` answers "what is on
   * the board"; this answers "what happened, and in what order" — which is the
   * question the tutor needs answered to resume at the first unresolved step
   * rather than starting the question again. See lib/canvasMemory.ts.
   *
   * Not persisted: it describes one live question, and a log restored from
   * storage would tell the tutor about reasoning the student cannot see.
   */
  canvasEvents: CanvasEvent[];

  /**
   * Live pixel size of the drawing surface, reported by DrawingCanvas.
   *
   * The store holds raw Konva pixels in `items` but §8's bbox has to be
   * normalised, like all tutor geometry — so the size has to be readable
   * outside the component that measures it. Zero until first measured, which
   * `itemBBox` treats as "no box yet" rather than inventing one.
   */
  canvasSize: CanvasSize;

  // Input mode (voice | text | canvas)
  inputMode: InputMode;
  textInput: string;

  // UI preferences (guided-learning layout)
  panelSide: 'left' | 'right';        // assistant panel side relative to canvas
  panelCollapsed: boolean;            // panel collapsed to a thin edge tab, giving canvas the width back
  /**
   * Tutor panel width in px, dragged by the student and kept across reloads.
   *
   * Clamped on write rather than on read: a width persisted on a wide monitor
   * and restored on a laptop would otherwise leave the canvas a sliver, and the
   * student would have to find the handle to get their work back.
   */
  panelWidth: number;
  transcriptVisible: boolean;         // transcript can be hidden
  toolbarPos: { x: number; y: number } | null; // null = default docked position
  toolbarCollapsed: boolean;          // collapsed to a small bubble
  toolbarOrientation: 'horizontal' | 'vertical'; // rotates when docked at a side
  micButtonPos: { x: number; y: number } | null; // draggable mic button; null = default (bottom-centre)
  canvasGrid: CanvasGrid;             // paper style behind the drawing surface

  // Tutor voice variant (testing only — see lib/voiceOptions.ts). null = let the
  // backend use whatever VOICE_TTS_PROVIDER / VOICE_TTS_VOICE are set to, which
  // is the only thing that has any effect until the backend reads a per-request
  // voice. Persisted so a tester's pick survives a reload.
  ttsProvider: string | null;
  ttsVoice: string | null;

  // Runtime: canvas PNG exporter, registered by the canvas for PDF notes
  canvasExporter: CanvasExporter | null;

  // Group / live session (collaboration)
  sessionMode: 'solo' | 'group';
  participants: Participant[];   // remote peers (local user not shown to self)
  remoteItems: DrawnItem[];      // strokes drawn by peers, in their colours

  // Learning progress (persisted) — lesson ids the student has marked learned
  completedLessons: string[];
  practiceCompleted: boolean; // has the student finished an independent practice

  // Learning-flow funnel (persisted) — which gated phases the student has cleared
  phasesDone: LearningPhase[];

  // Adaptive per-topic loop (persisted) — see lib/flow.ts
  entryTopicId: string | null;            // topic N, assigned by the Main Diagnostic
  currentTopicId: string;                 // topic the student is on right now
  flowStage: FlowStage;                   // stage within the current topic
  masteryByTopic: Record<string, boolean>; // topics the student has mastered

  // Student profile (persisted) — age drives the Key Stage they're shown
  studentAge: number;
  studentName: string; // collected at onboarding, used for greetings

  // Group Challenge Mode
  challengeActive: boolean;
  challengeProblem: string;
  reviewStatus: ReviewStatus;             // auto-review of the private canvas
  commentary: ChallengeComment[];         // AI live commentary feed
  spotlight: Spotlight | null;            // work currently on the shared board
  boardItems: DrawnItem[];                // AI-drawn strokes on the shared board
  privateFeedback: string | null;         // feedback only this student sees

  // Actions
  setSessionId: (id: string) => void;
  setSessionState: (s: SessionState) => void;
  setActiveSlide: (n: number) => void;
  setTotalSlides: (n: number) => void;
  setQuestionText: (q: string) => void;
  applyBackendPhase: (p: {
    phase: string;
    questionId: string | null;
    questionText: string | null;
    /** From the interaction reply. Falls back to the session record's view. */
    questionType?: QuestionType | null;
  }) => void;
  /** The student picked an option. Null clears the pick. */
  setSelectedOption: (optionId: string | null) => void;
  setQuestionNumber: (n: number) => void;
  setActiveEquation: (conceptId: string, questionId: string, label?: string) => void;
  setCurrentPhase: (phase: string) => void;
  setBackendSession: (record: SessionRecord | null) => void;
  setSessionSummary: (summary: SessionSummary | null) => void;
  setSessionReview: (review: SessionReview | null) => void;
  clearSessionId: () => void;
  toggleMic: () => void;
  setMicMuted: (value: boolean) => void;
  setVoiceStatus: (s: NumeraState['voiceStatus']) => void;
  /** Begin a new student LISTENING turn: mint a fresh turn_id and open the mic
   *  phase. Call when the student's turn starts (session open, or after the tutor
   *  finishes and another response is expected). */
  beginListeningTurn: () => void;
  /**
   * Mint a turn id for a NON-voice submission (typed answer, Explain Again).
   *
   * Voice turns get theirs from beginListeningTurn when the mic opens, but text
   * and Explain Again had no turn at all, so they sent none — which meant the
   * backend could not dedupe them and a retry looked like a second answer.
   * Returns the id so the caller can reuse it verbatim on a retry, which is the
   * whole point of the contract.
   */
  beginSubmissionTurn: () => string;
  /** Record the tutor's reply turn (voice contract §11): store its tutor_turn_id
   *  as the next previous_tutor_turn_id, and the backend gating for the next turn. */
  setTutorTurn: (tutorTurnId: string | null, gating: { expects: boolean; allow: boolean }) => void;
  /** The tutor turn failed; the student is owed a reply, not a nudge. */
  markTutorTurnFailed: () => void;
  setVisibleHint: (hint: string | null) => void;
  setVisualCueVisible: (v: boolean) => void;
  setActiveScaffold: (s: ActiveScaffold | null) => void;

  setVisualCue: (cue: {
    show: boolean;
    cueId?: string | null;
    cueType?: string | null;
    description?: string | null;
    assetUrl?: string | null;
    actions?: Array<Record<string, unknown>> | null;
  }) => void;
  setSupportShown: (rung: SupportRung | null) => void;
  setAppliedResponse: (a: AppliedState) => void;
  setInactivityPolicy: (p: InactivityPolicy | null) => void;
  setLastHintText: (text: string | null) => void;
  lockPhase3Attempt: (questionId: string | null) => void;
  /** Queue a line for the next screen to speak. */
  setPendingTutorSpeech: (text: string | null) => void;
  /** Take the queued line, clearing it — so two mounts cannot speak it twice. */
  claimPendingTutorSpeech: () => string | null;
  /** Position within this phase's question set, for the progress rail. */
  setQuestionProgress: (index: number, total: number) => void;
  toggleVisualCue: () => void;
  /** Returns the new message's id, so a caller can later retract it. */
  addTranscriptMessage: (msg: Omit<TranscriptMessage, 'id' | 'timestamp'>) => string;
  removeTranscriptMessage: (id: string) => void;
  setTranscript: (msgs: Pick<TranscriptMessage, 'role' | 'text'>[]) => void;
  updatePartialTranscript: (text: string) => void;
  commitPartialTranscript: (text: string) => void;
  addTrailEntry: (entry: Omit<TrailEntry, 'id' | 'timestamp'>) => void;
  clearTrail: () => void;
  setActiveTool: (t: DrawingTool) => void;
  setShapeKind: (k: ShapeKind) => void;
  setEraserMode: (m: EraserMode) => void;
  setStrokeColor: (c: string) => void;
  setStrokeWidth: (w: number) => void;
  addItem: (item: DrawnItem) => void;
  removeItem: (id: string) => void;
  undo: () => void;
  redo: () => void;
  clearCanvas: () => void;
  applyCanvasDraw: (payload: CanvasDrawPayload | CanvasDrawPayload[]) => void;
  clearTutorMarks: () => void;
  setCanvasSize: (size: CanvasSize) => void;
  /** Record a support action (cue shown, scaffold step opened) in canvas memory. */
  recordSupportEvent: (draft: CanvasEventDraft) => void;
  setInputMode: (m: InputMode) => void;
  setTextInput: (v: string) => void;
  setPanelSide: (s: 'left' | 'right') => void;
  /** Drag the panel edge. Clamped — see `clampPanelWidth`. */
  setPanelWidth: (px: number) => void;
  /** Back to the designed width (double-click the handle). */
  resetPanelWidth: () => void;
  togglePanelSide: () => void;
  togglePanelCollapsed: () => void;
  toggleTranscript: () => void;
  setToolbarPos: (pos: { x: number; y: number } | null) => void;
  toggleToolbarCollapsed: () => void;
  setToolbarOrientation: (o: 'horizontal' | 'vertical') => void;
  setMicButtonPos: (pos: { x: number; y: number } | null) => void;
  setCanvasGrid: (g: CanvasGrid) => void;
  setTtsVoice: (provider: string | null, voice: string | null) => void;
  setCanvasExporter: (fn: CanvasExporter | null) => void;
  startGroupSession: () => void;
  endGroupSession: () => void;
  upsertParticipant: (p: Participant) => void;
  removeParticipant: (id: string) => void;
  setParticipantCursor: (id: string, cursor: { x: number; y: number }) => void;
  addRemoteItem: (item: DrawnItem) => void;
  toggleLessonLearned: (lessonId: string) => void;
  setPracticeDone: () => void;
  setStudentAge: (age: number) => void;
  setStudentName: (name: string) => void;
  completePhase: (phase: LearningPhase) => void;
  setEntryTopic: (id: string) => void;
  setCurrentTopic: (id: string) => void;
  setFlowStage: (stage: FlowStage) => void;
  setMastery: (id: string, value: boolean) => void;
  startChallenge: (problem: string) => void;
  endChallenge: () => void;
  setReviewStatus: (s: ReviewStatus) => void;
  addCommentary: (c: Omit<ChallengeComment, 'id' | 'timestamp'>) => void;
  setSpotlight: (s: Spotlight | null) => void;
  addBoardItem: (item: DrawnItem) => void;
  setPrivateFeedback: (text: string | null) => void;
  reset: () => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initial: Omit<
  NumeraState,
  | 'setSessionId' | 'setSessionState' | 'setActiveSlide' | 'setTotalSlides'
  | 'setQuestionText' | 'applyBackendPhase' | 'setSelectedOption' | 'setQuestionNumber' | 'setActiveEquation' | 'setCurrentPhase' | 'setBackendSession' | 'setSessionSummary' | 'setSessionReview' | 'clearSessionId' | 'toggleMic' | 'setMicMuted' | 'setVoiceStatus' | 'beginListeningTurn' | 'beginSubmissionTurn' | 'setTutorTurn' | 'markTutorTurnFailed'
  | 'setVisualCueVisible' | 'setVisualCue' | 'toggleVisualCue' | 'setVisibleHint'
  | 'setSupportShown' | 'setLastHintText' | 'lockPhase3Attempt'
  | 'setPendingTutorSpeech' | 'claimPendingTutorSpeech' | 'setQuestionProgress' | 'setAppliedResponse' | 'setInactivityPolicy'
  | 'addTranscriptMessage' | 'removeTranscriptMessage' | 'setTranscript' | 'updatePartialTranscript' | 'commitPartialTranscript'
  | 'addTrailEntry' | 'clearTrail' | 'setActiveTool'
  | 'setShapeKind' | 'setEraserMode'
  | 'setStrokeColor' | 'setStrokeWidth' | 'addItem' | 'removeItem' | 'undo' | 'redo'
  | 'clearCanvas' | 'applyCanvasDraw' | 'clearTutorMarks' | 'setCanvasSize' | 'recordSupportEvent'
  | 'setInputMode' | 'setTextInput' | 'setPanelSide' | 'setPanelWidth' | 'resetPanelWidth' | 'togglePanelSide' | 'togglePanelCollapsed'
  | 'toggleTranscript' | 'setToolbarPos' | 'toggleToolbarCollapsed' | 'setToolbarOrientation' | 'setMicButtonPos' | 'setCanvasGrid' | 'setTtsVoice' | 'setActiveScaffold'
  | 'setCanvasExporter' | 'startGroupSession' | 'endGroupSession'
  | 'upsertParticipant' | 'removeParticipant' | 'setParticipantCursor'
  | 'addRemoteItem' | 'toggleLessonLearned' | 'setPracticeDone' | 'setStudentAge' | 'setStudentName'
  | 'completePhase'
  | 'setEntryTopic' | 'setCurrentTopic' | 'setFlowStage' | 'setMastery'
  | 'startChallenge' | 'endChallenge'
  | 'setReviewStatus' | 'addCommentary' | 'setSpotlight' | 'addBoardItem'
  | 'setPrivateFeedback' | 'reset'
> = {
  sessionId: null,
  sessionState: 'idle',
  // Progress rail position. Both zero until a session reports a question set —
  // they used to default to 2 and 9 and were never assigned by anything, so
  // every student saw "step 3 of 9" for the whole lesson no matter where they
  // actually were. The rail now hides itself until it knows something true
  // (§2: "Progress rail — shows question progress, not mastery labels").
  activeSlide: 0,
  totalSlides: 0,
  // No hardcoded equation: the backend session drives the question. Empty until
  // it loads so a stale demo equation never flashes on the live build.
  questionText: '',
  questionNumber: 0,
  // The concept to open a session on. Still a constant because the frontend has
  // no other source for it — the concept_id -> topic_code mapping lives in the
  // backend's settings.student_model_topic_codes. Everything else below is
  // backend-owned and starts EMPTY: seeding a phase and a question id meant the
  // app claimed to be in GUIDED_PRACTICE on a question nobody had served,
  // routing the student to the lesson screen before the backend had spoken.
  activeConceptId: DEMO_CONCEPT_ID,
  activeQuestionId: null,
  questionType: null as QuestionType | null,
  questionOptions: [] as SchemaQuestionOption[],
  selectedOptionId: null as string | null,
  currentPhase: '',
  backendSession: null,
  sessionSummary: null,
  sessionReview: null,
  micMuted: false,
  // 'idle' until something real happens: the socket opening or a session
  // starting promotes it. Starting at 'listening' had the panel claiming
  // "Listening…" — and the capture effect opening the mic — before any
  // socket existed to receive the audio, which was then simply discarded.
  voiceStatus: 'idle',
  currentTurnId: null,
  lastTutorTurnId: null,
  expectsStudentResponse: true,
  allowVoiceInput: true,
  tutorTurnFailed: false,
  activeScaffold: null as ActiveScaffold | null,
  visibleHint: null as string | null,
  visualCueVisible: false,
  visualCueId: null as string | null,
  visualCueType: null,
  visualCueDescription: null,
  visualCueAssetUrl: null as string | null,
  visualCueActions: null as Array<Record<string, unknown>> | null,
  supportShown: null as SupportRung | null,
  lastHintText: null as string | null,
  phase3LockedQuestionId: null as string | null,
  pendingTutorSpeech: null as string | null,
  appliedResponse: EMPTY_APPLIED,
  inactivityPolicy: null as InactivityPolicy | null,
  // Empty. This used to seed a three-message demo conversation about
  // "2x + 5 = 13", which rendered for every student before the backend had said
  // anything — a real tester reported it as "I am getting my old questions"
  // (2026-07-28). Mock mode fills it from demoContent; the live session fills it
  // from the tutor's replies.
  transcript: [],
  interactionTrail: [],
  activeTool: 'pen',
  shapeKind: 'rect',
  eraserMode: 'stroke',
  strokeColor: '#1a1a1a',
  strokeWidth: 3,
  items: [],
  undone: [],
  tutorElements: [],
  canvasEvents: [] as CanvasEvent[],
  canvasSize: { width: 0, height: 0 } as CanvasSize,
  inputMode: 'voice',
  textInput: '',
  panelSide: 'left',
  panelCollapsed: false,
  panelWidth: PANEL_WIDTH_DEFAULT,
  transcriptVisible: true,
  toolbarPos: null,
  toolbarCollapsed: false,
  toolbarOrientation: 'horizontal',
  micButtonPos: null,
  canvasGrid: 'grid',
  ttsProvider: null,
  ttsVoice: null,
  canvasExporter: null,
  sessionMode: 'solo',
  participants: [],
  remoteItems: [],
  completedLessons: [],
  practiceCompleted: false,
  phasesDone: [],
  entryTopicId: null,
  currentTopicId: TOPICS[0].id,
  flowStage: 'orientation',
  masteryByTopic: {},
  studentAge: 14,
  studentName: '',
  challengeActive: false,
  challengeProblem: '3x + 5 = 20',
  reviewStatus: 'idle',
  commentary: [],
  spotlight: null,
  boardItems: [],
  privateFeedback: null,
};

// ─── Store ────────────────────────────────────────────────────────────────────

export const useNumeraStore = create<NumeraState>()(
  persist(
    (set, get) => ({
  ...initial,

  // Opening a session resets the ordering guard. interaction_state_version is
  // monotonic WITHIN a session, so a fresh session starts counting again — and
  // carrying the previous session's high-water mark forward would make every
  // reply in the new one look stale and be dropped, freezing the lesson.
  // A Phase 3 lock belongs to the session that took the attempt. Persisting it
  // (so a refresh cannot reopen closed evidence) means it can otherwise outlive
  // its session and freeze the FIRST question of the next one, because a lock
  // held with no active question yet reads as locked by design.
  setSessionId: (id) =>
    set({ sessionId: id, appliedResponse: EMPTY_APPLIED, phase3LockedQuestionId: null }),
  setSessionState: (sessionState) => set({ sessionState }),
  setActiveSlide: (activeSlide) => set({ activeSlide }),
  setTotalSlides: (totalSlides) => set({ totalSlides }),
  setQuestionText: (questionText) => set({ questionText }),

  /**
   * Apply the phase/question the backend just reported.
   *
   * Shared by both transports (useDemoTutor's REST sync and useWebSocket's
   * tutor_response) because the rule below is subtle and they had drifted into
   * two different wrong answers.
   *
   * The rule turns on whether the PHASE changed:
   *
   *   - Phase changed → take the backend's answer verbatim, null included.
   *     Orientation genuinely has no question, and falling back to the previous
   *     one left a finished diagnostic question on screen for the whole phase.
   *
   *   - Phase unchanged → a missing question does NOT erase the current one.
   *     Mid-lesson replies are conversational and often carry no
   *     `current_question`; treating that as "no question" blanked the canvas
   *     while the student was still working on it (Manjusha, 2026-07-29).
   */
  applyBackendPhase: ({ phase, questionId, questionText, questionType }) =>
    set((s) => {
      const phaseChanged = phase !== s.currentPhase;
      const text = questionText?.trim() ?? '';
      const nextQuestionId =
        phaseChanged || questionId !== null ? questionId : s.activeQuestionId;
      // A cue belongs to the question it was raised for. Nothing cleared it, so
      // a cue shown on one question stayed on screen through the next one and
      // the one after — the student reading guidance about work they had
      // already finished (Sanya, 2026-07-29). Moving question or phase drops
      // it; the backend re-sends a cue when the new question needs one.
      const questionChanged = nextQuestionId !== s.activeQuestionId || phaseChanged;
      // Options live on the session record, not on the reply, so they have to be
      // looked up by id every time the question moves. The reply's own
      // `question_type` wins when it sent one — it is the more current of the
      // two — and the record's view fills in when it didn't.
      const view = studentViewFor(s.backendSession, nextQuestionId);
      const nextQuestionType =
        questionType ?? view?.question_type ?? (questionChanged ? null : s.questionType);
      const questionUsesOptions =
        nextQuestionType === 'SINGLE_CHOICE' ||
        nextQuestionType === 'CHOICE_WITH_EXPLANATION' ||
        nextQuestionType === 'TRUE_FALSE_WITH_EXPLANATION';
      return {
        currentPhase: phase,
        activeQuestionId: nextQuestionId,
        questionText: text || (phaseChanged ? '' : s.questionText),
        questionType: nextQuestionType,
        questionOptions: questionUsesOptions
          ? view?.options ?? (questionChanged ? [] : s.questionOptions)
          : [],
        // The support ladder is per-question too (§6: support is requested one
        // rung at a time for the question being worked on). Carrying `supportShown`
        // across a question boundary would leave the next question's "Need help?"
        // starting at the scaffold, skipping the hint the student should get first.
        ...(questionChanged
          ? {
              visualCueVisible: false,
              visualCueId: null,
              visualCueType: null,
              visualCueDescription: null,
              visualCueAssetUrl: null,
              visualCueActions: null,
              supportShown: null,
              lastHintText: null,
              // A hint is about the question it was given on. Left up, it would
              // sit beside the next question nudging the wrong step.
              visibleHint: null,
              // A pick belongs to the question it was made on. Carrying it over
              // would show the next question opening with an answer already
              // chosen.
              selectedOptionId: null,
              // So does the working. Nothing cleared the student's ink on a
              // question change, so the next question opened underneath the
              // last one's solution — and since the canvas is what gets
              // submitted, the OCR then read both (row 32, 11 Aug).
              items: [],
              undone: [],
              // The tutor's marks belong to the question they annotated.
              tutorElements: [],
              // Ordered memory is scoped to one question (§8: it exists so the
              // tutor can resume at the first unresolved step of the CURRENT
              // problem). Carrying it over would offer the tutor a completed
              // question's reasoning as if it were unfinished. Cross-question
              // history is session state, which the backend persists (§7).
              canvasEvents: [],
              // Ink and marks are gone, so a Phase 3 lock on the question just
              // left has nothing to hold; keeping it would freeze the new one.
              phase3LockedQuestionId: null,
            }
          : {}),
      };
    }),
  setSelectedOption: (selectedOptionId) => set({ selectedOptionId }),
  setQuestionNumber: (questionNumber) => set({ questionNumber }),

  // Switch the question the session runs on. Clearing sessionId makes the lesson
  // page start a fresh backend session for this concept/question; label gives
  // immediate feedback (and is the displayed equation when there's no backend).
  setActiveEquation: (activeConceptId, activeQuestionId, label) =>
    set({
      activeConceptId,
      activeQuestionId,
      sessionId: null,
      ...(label ? { questionText: label } : {}),
    }),

  setCurrentPhase: (currentPhase) => set({ currentPhase }),
  /**
   * Store the session record — and backfill the options that depend on it.
   *
   * Options do not travel on an interaction reply; they are looked up out of
   * this record by question id. So any turn applied BEFORE the record has
   * loaded finds nothing and sets `questionOptions: []` — and nothing ever put
   * them back, because every later reply is for the same question and so leaves
   * the (empty) list alone. The student was left with a choice question and no
   * choices: "Which is the general rule:" and nothing under it.
   *
   * That is the intermittent refresh case (Manjusha, 13 Aug 2026): reload
   * clears the record, and whether the options survive depends on whether the
   * record or the first reply lands first — a race the student should not be
   * exposed to. Re-deriving here removes the ordering dependency entirely.
   */
  setBackendSession: (backendSession) =>
    set((s) => {
      const view = studentViewFor(backendSession, s.activeQuestionId);
      if (!hasSelectableOptions(view) || s.questionOptions.length > 0) {
        return { backendSession };
      }
      return {
        backendSession,
        questionOptions: view!.options,
        // The record is also the authority on the type when the reply omitted
        // it, which is what decides that a chooser is rendered at all.
        questionType: s.questionType ?? view!.question_type,
      };
    }),
  setSessionSummary: (sessionSummary) => set({ sessionSummary }),
  setSessionReview: (sessionReview) => set({ sessionReview }),
  clearSessionId: () => set({
    sessionId: null,
    backendSession: null,
    appliedResponse: EMPTY_APPLIED,
    phase3LockedQuestionId: null,
  }),

  // Mute is orthogonal to the turn phase (voice contract §12): the LISTENING/
  // PROCESSING/SPEAKING phase is owned by the turn machine (beginListeningTurn /
  // submitVoiceTurn), not the mic button. Unmuting mid-tutor-speech must NOT open
  // the mic — the capture gate requires voiceStatus === 'listening' too.
  toggleMic: () => set((s) => ({ micMuted: !s.micMuted })),

  setMicMuted: (micMuted) => set({ micMuted }),

  setVoiceStatus: (voiceStatus) => set({ voiceStatus }),

  beginSubmissionTurn: () => {
    const id = nextTurnId();
    set({ currentTurnId: id });
    return id;
  },

  beginListeningTurn: () =>
    set({ currentTurnId: nextTurnId(), voiceStatus: 'listening' }),

  setTutorTurn: (tutorTurnId, { expects, allow }) =>
    set({
      lastTutorTurnId: tutorTurnId,
      expectsStudentResponse: expects,
      allowVoiceInput: allow,
      // A turn landed, so whatever failed before it is over.
      tutorTurnFailed: false,
    }),

  markTutorTurnFailed: () => set({ tutorTurnFailed: true }),

  setVisibleHint: (visibleHint) => set({ visibleHint }),

  setVisualCueVisible: (visualCueVisible) => set({ visualCueVisible }),

  // §8 logs SCAFFOLD_STEP as a SYSTEM_SUPPORT action, with `source_id` so every
  // support action stays traceable to the DB content it came from (§13). Only a
  // step the student can actually see is recorded: closing the panel is not a
  // teaching move, it is the absence of one.
  setActiveScaffold: (activeScaffold) =>
    set((s) => ({
      activeScaffold,
      canvasEvents: activeScaffold
        ? appendCanvasEvent(s.canvasEvents, {
            actor: 'SYSTEM_SUPPORT',
            action_type: 'SCAFFOLD_STEP',
            content: activeScaffold.stepText,
            source_id: activeScaffold.currentStepId,
            target_object_id: activeScaffold.scaffoldId,
          }, eventContext(s))
        : s.canvasEvents,
    })),

  setVisualCue: ({
    show, cueId = null, cueType = null, description = null, assetUrl = null, actions = null,
  }) =>
    set((s) => ({
      visualCueVisible: show,
      visualCueId: cueId,
      visualCueType: cueType,
      visualCueDescription: description,
      visualCueAssetUrl: assetUrl,
      visualCueActions: actions,
      canvasEvents: appendCanvasEvent(s.canvasEvents, {
        actor: 'SYSTEM_SUPPORT',
        action_type: show ? 'SHOW_CUE' : 'HIDE_CUE',
        content: description,
        // The cue's own id is its identity AND its DB provenance, so it is both
        // what was acted on and where the support came from (Sanya, 13 Aug).
        target_object_id: cueId,
        source_id: cueId,
      }, eventContext(s)),
    })),
  setSupportShown: (supportShown) => set({ supportShown }),
  setAppliedResponse: (appliedResponse) => set({ appliedResponse }),
  setInactivityPolicy: (inactivityPolicy) => set({ inactivityPolicy }),
  setLastHintText: (lastHintText) => set({ lastHintText }),

  // Idempotent by construction: locking the same question twice is the same
  // state, which is what makes a duplicate reply harmless.
  lockPhase3Attempt: (phase3LockedQuestionId) => set({ phase3LockedQuestionId }),

  setPendingTutorSpeech: (pendingTutorSpeech) => set({ pendingTutorSpeech }),

  // Claim-and-clear in one call: React mounts effects twice in development, and
  // a read-then-clear pair would speak the line twice before the clear landed.
  claimPendingTutorSpeech: () => {
    const { pendingTutorSpeech } = get();
    if (pendingTutorSpeech !== null) set({ pendingTutorSpeech: null });
    return pendingTutorSpeech;
  },
  setQuestionProgress: (index, total) =>
    set({ activeSlide: Math.max(0, index), totalSlides: Math.max(0, total) }),
  toggleVisualCue: () => set((s) => ({ visualCueVisible: !s.visualCueVisible })),

  addTranscriptMessage: (msg) => {
    const id = uid();
    set((s) => ({
      // Anything the tutor says ends the student's turn, so the next thing they
      // say starts a new bubble instead of joining the last one. This is the
      // only place the turn closes, because it is the only true signal: the
      // tutor answering IS the turn being over.
      transcript: [
        ...(msg.role === 'ai'
          ? s.transcript.map((m) => (m.open ? { ...m, open: false } : m))
          : s.transcript),
        { ...msg, id, timestamp: Date.now() },
      ],
    }));
    return id;
  },

  removeTranscriptMessage: (id) =>
    set((s) => ({ transcript: s.transcript.filter((m) => m.id !== id) })),

  setTranscript: (msgs) =>
    set({
      transcript: msgs.map((m, idx) => ({
        id: `seed-${idx}`,
        role: m.role,
        text: m.text,
        timestamp: Date.now() - (msgs.length - idx) * 10_000,
      })),
    }),

  /**
   * The live caption of what the student is saying.
   *
   * INVARIANT: at most one partial bubble exists at any time, and it is always
   * last. Both actions below enforce it by dropping every existing partial
   * before writing, reusing its id so the bubble is updated rather than
   * remounted (which would flicker mid-sentence).
   *
   * The previous version only looked at `transcript[length - 1]`. If the tutor
   * replied while a partial was still pending — which happens whenever speech
   * is still being finalised as the reply lands — the last entry was the AI's
   * message, the check failed, and the partial was orphaned: a grey
   * "…transcribing" bubble stuck in the log forever, with the student's real
   * words appended below it as a second bubble. Every turn after that added
   * another pair (Manjusha's recording, 2026-07-29).
   */
  updatePartialTranscript: (text) =>
    set((s) => {
      const existing = s.transcript.find((m) => m.partial);
      return {
        transcript: [
          ...s.transcript.filter((m) => !m.partial),
          {
            id: existing?.id ?? uid(),
            role: 'student',
            text,
            partial: true,
            timestamp: existing?.timestamp ?? Date.now(),
          },
        ],
      };
    }),

  commitPartialTranscript: (text) =>
    set((s) => {
      const existing = s.transcript.find((m) => m.partial);
      const settled = s.transcript.filter((m) => !m.partial);
      const last = settled[settled.length - 1];

      // Still the same spoken turn: join this segment onto it rather than
      // starting another bubble. The turn is closed by the tutor replying, in
      // addTranscriptMessage.
      if (last && last.role === 'student' && last.open) {
        const joined = `${last.text} ${text}`.replace(/\s+/g, ' ').trim();
        return {
          transcript: [...settled.slice(0, -1), { ...last, text: joined }],
        };
      }

      return {
        transcript: [
          ...settled,
          {
            id: existing?.id ?? uid(),
            role: 'student',
            text,
            open: true,
            timestamp: existing?.timestamp ?? Date.now(),
          },
        ],
      };
    }),

  addTrailEntry: (entry) =>
    set((s) => ({
      interactionTrail: [
        ...s.interactionTrail,
        { ...entry, id: uid(), timestamp: Date.now() },
      ],
    })),

  clearTrail: () => set({ interactionTrail: [] }),

  setActiveTool: (activeTool) => set({ activeTool }),
  setShapeKind: (shapeKind) => set({ shapeKind, activeTool: 'shape' }),
  setEraserMode: (eraserMode) => set({ eraserMode, activeTool: 'eraser' }),
  setStrokeColor: (strokeColor) => set({ strokeColor }),
  setStrokeWidth: (strokeWidth) => set({ strokeWidth }),

  // ── Canvas mutations, each also written to ordered memory (§8) ─────────────
  //
  // The events are emitted HERE rather than in DrawingCanvas because the store
  // is the one place every path goes through — pointer strokes, the object
  // eraser, undo/redo and the toolbar's clear. An emitter in the component
  // would have to be repeated at each, and the one that got missed would be
  // invisible: the board would still look right, and only the tutor would be
  // working from an incomplete history.

  addItem: (item) =>
    set((s) => ({
      items: [...s.items, item],
      undone: [],
      canvasEvents: appendCanvasEvent(s.canvasEvents, {
        actor: 'STUDENT',
        action_type: 'WRITE',
        target_object_id: item.id,
        bbox: itemBBox(item, s.canvasSize),
        content: item.kind === 'stroke' ? item.tool : item.kind,
      }, eventContext(s)),
    })),

  removeItem: (id) =>
    set((s) => {
      const removed = s.items.find((it) => it.id === id);
      if (!removed) return s;
      return {
        items: s.items.filter((it) => it.id !== id),
        canvasEvents: appendCanvasEvent(
          supersedeCanvasEvents(s.canvasEvents, [id]),
          { actor: 'STUDENT', action_type: 'ERASE', target_object_id: id },
          eventContext(s),
        ),
      };
    }),

  // Undo is an ERASE in the log, not a rewind of it. The student did write the
  // thing and then take it back, and that sequence is evidence — §8 keeps the
  // trail of thinking, so removing the WRITE would make the log claim they
  // never tried it.
  undo: () =>
    set((s) => {
      if (s.items.length === 0) return s;
      const last = s.items[s.items.length - 1];
      return {
        items: s.items.slice(0, -1),
        undone: [...s.undone, last],
        canvasEvents: appendCanvasEvent(
          supersedeCanvasEvents(s.canvasEvents, [last.id]),
          { actor: 'STUDENT', action_type: 'ERASE', target_object_id: last.id },
          eventContext(s),
        ),
      };
    }),

  redo: () =>
    set((s) => {
      if (s.undone.length === 0) return s;
      const last = s.undone[s.undone.length - 1];
      return {
        items: [...s.items, last],
        undone: s.undone.slice(0, -1),
        canvasEvents: appendCanvasEvent(s.canvasEvents, {
          actor: 'STUDENT',
          action_type: 'WRITE',
          target_object_id: last.id,
          bbox: itemBBox(last, s.canvasSize),
          content: last.kind === 'stroke' ? last.tool : last.kind,
        }, eventContext(s)),
      };
    }),

  clearCanvas: () =>
    set((s) => ({
      items: [],
      undone: [],
      canvasEvents: appendCanvasEvent(
        clearCanvasEvents(s.canvasEvents),
        { actor: 'STUDENT', action_type: 'CLEAR' },
        eventContext(s),
      ),
    })),

  setCanvasSize: (canvasSize) => set({ canvasSize }),

  recordSupportEvent: (draft) =>
    set((s) => ({ canvasEvents: appendCanvasEvent(s.canvasEvents, draft, eventContext(s)) })),

  applyCanvasDraw: (payload) =>
    set((s) => {
      // Phase 3 spec §3.2/§1.5: no tutor ink or correction overlays during an
      // independent attempt, and no canvas_draw built from Phase 3 metadata.
      // Refused HERE rather than hidden at the render, so a drawing the backend
      // still sends never enters the tutor layer at all — hiding it would leave
      // it waiting to appear the moment the phase changed.
      if (isPhase3(s.currentPhase)) return {};
      // The WS path delivers one action per message; REST responses deliver a
      // list of actions. Accept both here so no caller has to care.
      const actions = Array.isArray(payload) ? payload : [payload];
      let tutorElements = s.tutorElements;
      let canvasEvents = s.canvasEvents;
      const context = eventContext(s);
      for (const action of actions) {
        // A new "replace" resets the layer and the idempotency window.
        if (action.mode === 'replace') {
          seenDrawActionIds.clear();
          // The marks leave the screen; their events stay in the log as
          // SUPERSEDED. The tutor drew them, so they are part of how the
          // reasoning unfolded even once they are gone (§11).
          canvasEvents = supersedeCanvasEvents(canvasEvents, tutorElements.map((el) => el.id));
          tutorElements = [];
        }
        // Drop a duplicate command (re-delivered on reconnect). It must not
        // reach the log either — a reconnect would otherwise show the tutor
        // annotating twice and read as a repeated teaching move.
        if (action.actionId) {
          if (seenDrawActionIds.has(action.actionId)) continue;
          seenDrawActionIds.add(action.actionId);
        }
        const incoming: TutorElement[] = (action.elements ?? []).map((el) => ({
          ...el,
          id: el.id ?? uid(),
        }));
        for (const element of incoming) {
          canvasEvents = appendCanvasEvent(canvasEvents, {
            actor: 'TUTOR',
            action_type: tutorActionType(element.kind),
            target_object_id: element.id,
            bbox: tutorElementBBox(element),
            content: tutorElementText(element),
            math_text: element.tex?.trim() || null,
            source_id: action.actionId ?? null,
          }, context);
        }
        tutorElements = [...tutorElements, ...incoming];
      }
      return { tutorElements, canvasEvents };
    }),

  clearTutorMarks: () => {
    seenDrawActionIds.clear();
    set({ tutorElements: [] });
  },

  setInputMode: (inputMode) => set({ inputMode }),
  setTextInput: (textInput) => set({ textInput }),

  setPanelWidth: (px) => set({ panelWidth: clampPanelWidth(px) }),
  resetPanelWidth: () => set({ panelWidth: PANEL_WIDTH_DEFAULT }),
  setPanelSide: (panelSide) => set({ panelSide }),
  togglePanelSide: () => set((s) => ({ panelSide: s.panelSide === 'left' ? 'right' : 'left' })),
  togglePanelCollapsed: () => set((s) => ({ panelCollapsed: !s.panelCollapsed })),
  toggleTranscript: () => set((s) => ({ transcriptVisible: !s.transcriptVisible })),
  setToolbarPos: (toolbarPos) => set({ toolbarPos }),
  toggleToolbarCollapsed: () => set((s) => ({ toolbarCollapsed: !s.toolbarCollapsed })),
  setToolbarOrientation: (toolbarOrientation) => set({ toolbarOrientation }),
  setMicButtonPos: (micButtonPos) => set({ micButtonPos }),
  setCanvasGrid: (canvasGrid) => set({ canvasGrid }),

  /** Pick a tutor voice variant, or pass (null, null) to fall back to the
   *  backend's configured default. */
  setTtsVoice: (ttsProvider, ttsVoice) => set({ ttsProvider, ttsVoice }),
  setCanvasExporter: (canvasExporter) => set({ canvasExporter }),

  startGroupSession: () => set({ sessionMode: 'group' }),
  endGroupSession: () => set({ sessionMode: 'solo', participants: [], remoteItems: [] }),
  upsertParticipant: (p) =>
    set((s) => {
      const exists = s.participants.some((x) => x.id === p.id);
      return {
        participants: exists
          ? s.participants.map((x) => (x.id === p.id ? { ...x, ...p } : x))
          : [...s.participants, p],
      };
    }),
  removeParticipant: (id) =>
    set((s) => ({ participants: s.participants.filter((p) => p.id !== id) })),
  setParticipantCursor: (id, cursor) =>
    set((s) => ({
      participants: s.participants.map((p) => (p.id === id ? { ...p, cursor } : p)),
    })),
  addRemoteItem: (item) => set((s) => ({ remoteItems: [...s.remoteItems, item] })),

  toggleLessonLearned: (lessonId) =>
    set((s) => ({
      completedLessons: s.completedLessons.includes(lessonId)
        ? s.completedLessons.filter((id) => id !== lessonId)
        : [...s.completedLessons, lessonId],
    })),
  setPracticeDone: () => set({ practiceCompleted: true }),
  setStudentAge: (studentAge) => set({ studentAge }),
  setStudentName: (studentName) => set({ studentName }),

  completePhase: (phase) =>
    set((s) =>
      s.phasesDone.includes(phase)
        ? s
        : { phasesDone: [...s.phasesDone, phase] }
    ),

  // Main Diagnostic places the student at topic N: it becomes both the entry
  // topic and the current one, started at orientation.
  setEntryTopic: (id) =>
    set({ entryTopicId: id, currentTopicId: id, flowStage: 'orientation' }),
  setCurrentTopic: (currentTopicId) => set({ currentTopicId }),
  setFlowStage: (flowStage) => set({ flowStage }),
  setMastery: (id, value) =>
    set((s) => ({ masteryByTopic: { ...s.masteryByTopic, [id]: value } })),

  startChallenge: (challengeProblem) =>
    set({
      challengeActive: true,
      challengeProblem,
      sessionMode: 'group',
      reviewStatus: 'idle',
      commentary: [],
      spotlight: null,
      boardItems: [],
      privateFeedback: null,
    }),
  endChallenge: () =>
    set({
      challengeActive: false,
      sessionMode: 'solo',
      participants: [],
      reviewStatus: 'idle',
      commentary: [],
      spotlight: null,
      boardItems: [],
      privateFeedback: null,
    }),
  setReviewStatus: (reviewStatus) => set({ reviewStatus }),
  addCommentary: (c) =>
    set((s) => ({
      commentary: [
        ...s.commentary,
        { ...c, id: uid(), timestamp: Date.now() },
      ].slice(-8), // keep the feed short
    })),
  setSpotlight: (spotlight) => set({ spotlight }),
  addBoardItem: (item) => set((s) => ({ boardItems: [...s.boardItems, item] })),
  setPrivateFeedback: (privateFeedback) => set({ privateFeedback }),

  reset: () => set({ ...initial }),
    }),
    {
      name: 'numera-store',
      storage: createJSONStorage(() => localStorage),
      // Persist durable UI preferences, learning progress — and the session id.
      //
      // The id used to be excluded with the rest of the "backend-driven &
      // ephemeral" state, and that reasoning was wrong in one specific way:
      // dropping it did not give the student a clean slate, it gave them a
      // SECOND session on a topic they already had open. The Student Model
      // resumed it and stamped routing_reason_code=SESSION_RESUMED, which the
      // backend cannot serialise into InteractionResponse, so every turn in
      // that session answered 500 (7 Aug: 164 session starts, 16 resumed).
      //
      // Canvas and transcript stay out — those really are per-session.
      // A persisted id CAN outlive the backend, whose sessions are in memory;
      // isStaleSessionError + clearSessionId in useDemoTutor is what recovers
      // from that, rather than leaving the lesson wedged.
      partialize: (s) => ({
        sessionId: s.sessionId,
        // Phase 3 spec §3.3: "Keep the locked state through reconnect." The
        // canvas and transcript are deliberately per-session below, but an
        // accepted independent attempt must NOT come back editable after a
        // refresh — that would let a student reopen closed evidence.
        phase3LockedQuestionId: s.phase3LockedQuestionId,
        panelSide: s.panelSide,
        panelCollapsed: s.panelCollapsed,
        panelWidth: s.panelWidth,
        transcriptVisible: s.transcriptVisible,
        toolbarPos: s.toolbarPos,
        toolbarCollapsed: s.toolbarCollapsed,
        toolbarOrientation: s.toolbarOrientation,
        micButtonPos: s.micButtonPos,
        canvasGrid: s.canvasGrid,
        ttsProvider: s.ttsProvider,
        ttsVoice: s.ttsVoice,
        shapeKind: s.shapeKind,
        eraserMode: s.eraserMode,
        completedLessons: s.completedLessons,
        practiceCompleted: s.practiceCompleted,
        phasesDone: s.phasesDone,
        entryTopicId: s.entryTopicId,
        currentTopicId: s.currentTopicId,
        flowStage: s.flowStage,
        masteryByTopic: s.masteryByTopic,
        studentAge: s.studentAge,
        studentName: s.studentName,
      }),
      // Hydrate manually after mount to avoid SSR/client mismatch (see AppFrame).
      skipHydration: true,
    }
  )
);

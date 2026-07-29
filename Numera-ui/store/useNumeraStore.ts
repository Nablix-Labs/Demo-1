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
import { DEMO_CONCEPT_ID, type ActiveScaffold, type SessionRecord, type SessionReview, type SessionSummary } from '@/lib/api';
import { uid } from '@/lib/uid';

// Sequential, human-readable student turn ids (voice contract §3): TURN-0001, …
// One per LISTENING turn; kept sequential (not uuid) so logs read cleanly.
let turnCounter = 0;
const nextTurnId = () => `TURN-${String(++turnCounter).padStart(4, '0')}`;

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

export interface TranscriptMessage {
  id: string;
  role: 'ai' | 'student';
  text: string;
  partial?: boolean; // true while still transcribing
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
  visualCueVisible: boolean;
  visualCueType: string | null;
  visualCueDescription: string | null;

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

  // Input mode (voice | text | canvas)
  inputMode: InputMode;
  textInput: string;

  // UI preferences (guided-learning layout)
  panelSide: 'left' | 'right';        // assistant panel side relative to canvas
  panelCollapsed: boolean;            // panel collapsed to a thin edge tab, giving canvas the width back
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
  canvasExporter: (() => string | null) | null;

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
  }) => void;
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
  /** Record the tutor's reply turn (voice contract §11): store its tutor_turn_id
   *  as the next previous_tutor_turn_id, and the backend gating for the next turn. */
  setTutorTurn: (tutorTurnId: string | null, gating: { expects: boolean; allow: boolean }) => void;
  setVisualCueVisible: (v: boolean) => void;
  setActiveScaffold: (s: ActiveScaffold | null) => void;

  setVisualCue: (cue: { show: boolean; cueType?: string | null; description?: string | null }) => void;
  toggleVisualCue: () => void;
  addTranscriptMessage: (msg: Omit<TranscriptMessage, 'id' | 'timestamp'>) => void;
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
  setInputMode: (m: InputMode) => void;
  setTextInput: (v: string) => void;
  setPanelSide: (s: 'left' | 'right') => void;
  togglePanelSide: () => void;
  togglePanelCollapsed: () => void;
  toggleTranscript: () => void;
  setToolbarPos: (pos: { x: number; y: number } | null) => void;
  toggleToolbarCollapsed: () => void;
  setToolbarOrientation: (o: 'horizontal' | 'vertical') => void;
  setMicButtonPos: (pos: { x: number; y: number } | null) => void;
  setCanvasGrid: (g: CanvasGrid) => void;
  setTtsVoice: (provider: string | null, voice: string | null) => void;
  setCanvasExporter: (fn: (() => string | null) | null) => void;
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
  | 'setQuestionText' | 'applyBackendPhase' | 'setQuestionNumber' | 'setActiveEquation' | 'setCurrentPhase' | 'setBackendSession' | 'setSessionSummary' | 'setSessionReview' | 'clearSessionId' | 'toggleMic' | 'setMicMuted' | 'setVoiceStatus' | 'beginListeningTurn' | 'setTutorTurn'
  | 'setVisualCueVisible' | 'setVisualCue' | 'toggleVisualCue'
  | 'addTranscriptMessage' | 'setTranscript' | 'updatePartialTranscript' | 'commitPartialTranscript'
  | 'addTrailEntry' | 'clearTrail' | 'setActiveTool'
  | 'setShapeKind' | 'setEraserMode'
  | 'setStrokeColor' | 'setStrokeWidth' | 'addItem' | 'removeItem' | 'undo' | 'redo'
  | 'clearCanvas' | 'applyCanvasDraw' | 'clearTutorMarks'
  | 'setInputMode' | 'setTextInput' | 'setPanelSide' | 'togglePanelSide' | 'togglePanelCollapsed'
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
  activeSlide: 2,
  totalSlides: 9,
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
  currentPhase: '',
  backendSession: null,
  sessionSummary: null,
  sessionReview: null,
  micMuted: false,
  voiceStatus: 'listening',
  currentTurnId: null,
  lastTutorTurnId: null,
  expectsStudentResponse: true,
  allowVoiceInput: true,
  activeScaffold: null as ActiveScaffold | null,
  visualCueVisible: false,
  visualCueType: null,
  visualCueDescription: null,
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
  inputMode: 'voice',
  textInput: '',
  panelSide: 'left',
  panelCollapsed: false,
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
    (set) => ({
  ...initial,

  setSessionId: (id) => set({ sessionId: id }),
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
  applyBackendPhase: ({ phase, questionId, questionText }) =>
    set((s) => {
      const phaseChanged = phase !== s.currentPhase;
      const text = questionText?.trim() ?? '';
      return {
        currentPhase: phase,
        activeQuestionId:
          phaseChanged || questionId !== null ? questionId : s.activeQuestionId,
        questionText: text || (phaseChanged ? '' : s.questionText),
      };
    }),
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
  setBackendSession: (backendSession) => set({ backendSession }),
  setSessionSummary: (sessionSummary) => set({ sessionSummary }),
  setSessionReview: (sessionReview) => set({ sessionReview }),
  clearSessionId: () => set({ sessionId: null }),

  // Mute is orthogonal to the turn phase (voice contract §12): the LISTENING/
  // PROCESSING/SPEAKING phase is owned by the turn machine (beginListeningTurn /
  // submitVoiceTurn), not the mic button. Unmuting mid-tutor-speech must NOT open
  // the mic — the capture gate requires voiceStatus === 'listening' too.
  toggleMic: () => set((s) => ({ micMuted: !s.micMuted })),

  setMicMuted: (micMuted) => set({ micMuted }),

  setVoiceStatus: (voiceStatus) => set({ voiceStatus }),

  beginListeningTurn: () =>
    set({ currentTurnId: nextTurnId(), voiceStatus: 'listening' }),

  setTutorTurn: (tutorTurnId, { expects, allow }) =>
    set({
      lastTutorTurnId: tutorTurnId,
      expectsStudentResponse: expects,
      allowVoiceInput: allow,
    }),

  setVisualCueVisible: (visualCueVisible) => set({ visualCueVisible }),
  setActiveScaffold: (activeScaffold) => set({ activeScaffold }),

  setVisualCue: ({ show, cueType = null, description = null }) =>
    set({ visualCueVisible: show, visualCueType: cueType, visualCueDescription: description }),
  toggleVisualCue: () => set((s) => ({ visualCueVisible: !s.visualCueVisible })),

  addTranscriptMessage: (msg) =>
    set((s) => ({
      transcript: [
        ...s.transcript,
        { ...msg, id: uid(), timestamp: Date.now() },
      ],
    })),

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
      return {
        transcript: [
          ...s.transcript.filter((m) => !m.partial),
          {
            id: existing?.id ?? uid(),
            role: 'student',
            text,
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

  addItem: (item) =>
    set((s) => ({ items: [...s.items, item], undone: [] })),

  removeItem: (id) =>
    set((s) => ({ items: s.items.filter((it) => it.id !== id) })),

  undo: () =>
    set((s) => {
      if (s.items.length === 0) return s;
      const last = s.items[s.items.length - 1];
      return { items: s.items.slice(0, -1), undone: [...s.undone, last] };
    }),

  redo: () =>
    set((s) => {
      if (s.undone.length === 0) return s;
      const last = s.undone[s.undone.length - 1];
      return { items: [...s.items, last], undone: s.undone.slice(0, -1) };
    }),

  clearCanvas: () => set({ items: [], undone: [] }),

  applyCanvasDraw: (payload) =>
    set((s) => {
      // The WS path delivers one action per message; REST responses deliver a
      // list of actions. Accept both here so no caller has to care.
      const actions = Array.isArray(payload) ? payload : [payload];
      let tutorElements = s.tutorElements;
      for (const action of actions) {
        // A new "replace" resets the layer and the idempotency window.
        if (action.mode === 'replace') {
          seenDrawActionIds.clear();
          tutorElements = [];
        }
        // Drop a duplicate command (re-delivered on reconnect).
        if (action.actionId) {
          if (seenDrawActionIds.has(action.actionId)) continue;
          seenDrawActionIds.add(action.actionId);
        }
        const incoming: TutorElement[] = (action.elements ?? []).map((el) => ({
          ...el,
          id: el.id ?? uid(),
        }));
        tutorElements = [...tutorElements, ...incoming];
      }
      return { tutorElements };
    }),

  clearTutorMarks: () => {
    seenDrawActionIds.clear();
    set({ tutorElements: [] });
  },

  setInputMode: (inputMode) => set({ inputMode }),
  setTextInput: (textInput) => set({ textInput }),

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
      // Persist only durable UI preferences + learning progress — never
      // session/canvas/transcript state, which is backend-driven & ephemeral.
      partialize: (s) => ({
        panelSide: s.panelSide,
        panelCollapsed: s.panelCollapsed,
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

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

  // Voice
  micMuted: boolean;
  voiceStatus: 'idle' | 'listening' | 'speaking' | 'processing';

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
  transcriptVisible: boolean;         // transcript can be hidden
  toolbarPos: { x: number; y: number } | null; // null = default docked position
  toolbarCollapsed: boolean;          // collapsed to a small bubble
  toolbarOrientation: 'horizontal' | 'vertical'; // rotates when docked at a side
  canvasGrid: CanvasGrid;             // paper style behind the drawing surface

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
  setQuestionNumber: (n: number) => void;
  toggleMic: () => void;
  setMicMuted: (value: boolean) => void;
  setVoiceStatus: (s: NumeraState['voiceStatus']) => void;
  addTranscriptMessage: (msg: Omit<TranscriptMessage, 'id' | 'timestamp'>) => void;
  setTranscript: (msgs: Pick<TranscriptMessage, 'role' | 'text'>[]) => void;
  updatePartialTranscript: (text: string) => void;
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
  applyCanvasDraw: (payload: CanvasDrawPayload) => void;
  clearTutorMarks: () => void;
  setInputMode: (m: InputMode) => void;
  setTextInput: (v: string) => void;
  setPanelSide: (s: 'left' | 'right') => void;
  togglePanelSide: () => void;
  toggleTranscript: () => void;
  setToolbarPos: (pos: { x: number; y: number } | null) => void;
  toggleToolbarCollapsed: () => void;
  setToolbarOrientation: (o: 'horizontal' | 'vertical') => void;
  setCanvasGrid: (g: CanvasGrid) => void;
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
  | 'setQuestionText' | 'setQuestionNumber' | 'toggleMic' | 'setMicMuted' | 'setVoiceStatus'
  | 'addTranscriptMessage' | 'setTranscript' | 'updatePartialTranscript'
  | 'addTrailEntry' | 'clearTrail' | 'setActiveTool'
  | 'setShapeKind' | 'setEraserMode'
  | 'setStrokeColor' | 'setStrokeWidth' | 'addItem' | 'removeItem' | 'undo' | 'redo'
  | 'clearCanvas' | 'applyCanvasDraw' | 'clearTutorMarks'
  | 'setInputMode' | 'setTextInput' | 'setPanelSide' | 'togglePanelSide'
  | 'toggleTranscript' | 'setToolbarPos' | 'toggleToolbarCollapsed' | 'setToolbarOrientation' | 'setCanvasGrid'
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
  questionText: '2x + 5 = 13',
  questionNumber: 3,
  micMuted: false,
  voiceStatus: 'listening',
  transcript: [
    {
      id: '1',
      role: 'ai',
      text: 'What do we do first to get the x term on its own?',
      timestamp: Date.now() - 30_000,
    },
    {
      id: '2',
      role: 'student',
      text: 'Subtract 5 from both sides?',
      timestamp: Date.now() - 20_000,
    },
    {
      id: '3',
      role: 'ai',
      text: 'Exactly. So what does the left side become?',
      timestamp: Date.now() - 10_000,
    },
  ],
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
  transcriptVisible: true,
  toolbarPos: null,
  toolbarCollapsed: false,
  toolbarOrientation: 'horizontal',
  canvasGrid: 'grid',
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
  setQuestionNumber: (questionNumber) => set({ questionNumber }),

  toggleMic: () =>
    set((s) => ({
      micMuted: !s.micMuted,
      voiceStatus: s.micMuted ? 'listening' : 'idle',
    })),

  setMicMuted: (micMuted) =>
    set({ micMuted, voiceStatus: micMuted ? 'idle' : 'listening' }),

  setVoiceStatus: (voiceStatus) => set({ voiceStatus }),

  addTranscriptMessage: (msg) =>
    set((s) => {
      const last = s.transcript[s.transcript.length - 1];
      const message = { ...msg, id: crypto.randomUUID(), timestamp: Date.now() };
      if (last?.partial && last.role === msg.role) {
        return { transcript: [...s.transcript.slice(0, -1), message] };
      }
      return { transcript: [...s.transcript, message] };
    }),

  setTranscript: (msgs) =>
    set({
      transcript: msgs.map((m, idx) => ({
        id: `seed-${idx}`,
        role: m.role,
        text: m.text,
        timestamp: Date.now() - (msgs.length - idx) * 10_000,
      })),
    }),

  updatePartialTranscript: (text) =>
    set((s) => {
      const last = s.transcript[s.transcript.length - 1];
      if (last?.partial) {
        return {
          transcript: [
            ...s.transcript.slice(0, -1),
            { ...last, text },
          ],
        };
      }
      return {
        transcript: [
          ...s.transcript,
          {
            id: crypto.randomUUID(),
            role: 'student',
            text,
            partial: true,
            timestamp: Date.now(),
          },
        ],
      };
    }),

  addTrailEntry: (entry) =>
    set((s) => ({
      interactionTrail: [
        ...s.interactionTrail,
        { ...entry, id: crypto.randomUUID(), timestamp: Date.now() },
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
      const incoming: TutorElement[] = payload.elements.map((el) => ({
        ...el,
        id: el.id ?? crypto.randomUUID(),
      }));
      return {
        tutorElements:
          payload.mode === 'replace' ? incoming : [...s.tutorElements, ...incoming],
      };
    }),

  clearTutorMarks: () => set({ tutorElements: [] }),

  setInputMode: (inputMode) => set({ inputMode }),
  setTextInput: (textInput) => set({ textInput }),

  setPanelSide: (panelSide) => set({ panelSide }),
  togglePanelSide: () => set((s) => ({ panelSide: s.panelSide === 'left' ? 'right' : 'left' })),
  toggleTranscript: () => set((s) => ({ transcriptVisible: !s.transcriptVisible })),
  setToolbarPos: (toolbarPos) => set({ toolbarPos }),
  toggleToolbarCollapsed: () => set((s) => ({ toolbarCollapsed: !s.toolbarCollapsed })),
  setToolbarOrientation: (toolbarOrientation) => set({ toolbarOrientation }),
  setCanvasGrid: (canvasGrid) => set({ canvasGrid }),
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
        { ...c, id: crypto.randomUUID(), timestamp: Date.now() },
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
        transcriptVisible: s.transcriptVisible,
        toolbarPos: s.toolbarPos,
        toolbarCollapsed: s.toolbarCollapsed,
        toolbarOrientation: s.toolbarOrientation,
        canvasGrid: s.canvasGrid,
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

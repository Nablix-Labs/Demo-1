/**
 * The canvas teaching plan — what the tutor draws WHILE it talks (Sanya, PR
 * #364, 25 Sep 2026; docs/FRONTEND_CANVAS_TEACHING_HANDOFF.md).
 *
 * A plan is a list of beats. Each beat is tied to an exact phrase of
 * `message_voice` and carries a few operations: circle this token, box that
 * one, write this example in the reasoning column. The scheduler
 * (lib/canvasTeachingScheduler) fires a beat when the audio reaches its phrase;
 * this module decides what a beat turns into on screen.
 *
 * It is VISUAL ONLY, and a third channel beside the two that already exist:
 *
 *   - `canvas_draw` stays the OCR correction channel (marks round student ink);
 *   - `tutor_canvas_actions` stays the support/control channel (cue, scaffold,
 *     rescue steps, confirmations).
 *
 * Nothing here advances support, decides correctness, or reveals an answer.
 * `teaching_mode` is the backend's; it is read only to REFUSE operations the
 * mode does not allow, in case the backend's own validation ever lets one
 * through — the same stance `revealsAnswer` takes on `answer_reveal_allowed`.
 *
 * Like every other tutor target, an operation is resolved against what the
 * client can see right now, and one whose target cannot be found is DROPPED
 * rather than placed somewhere plausible. A circle round the wrong token
 * teaches the wrong thing.
 */

import type { QuestionAnchor } from '@/lib/questionAnchors';
import { itemBBox, type CanvasBBox, type CanvasSize } from '@/lib/canvasMemory';
import {
  RESCUE_GAP, RESCUE_SUFFIX, RESCUE_WRAP_WIDTH, ladderTop,
} from '@/lib/tutorCanvasActions';
import { sceneNoteElements } from '@/lib/canvasTeachingScene';
import type { DrawnItem, TutorElement } from '@/store/useNumeraStore';

// ─── Contract (nablix-backend/app/models/canvas_teaching.py) ────────────────

export type CanvasTeachingOperationKind =
  | 'FOCUS' | 'HIGHLIGHT' | 'CIRCLE' | 'CONNECT' | 'WRITE_TEXT' | 'WRITE_MATH' | 'BOX' | 'CHECK';
export type CanvasTeachingTargetKind = 'QUESTION_ANCHOR' | 'STUDENT_TOKEN' | 'CANVAS_ZONE';
export type CanvasTeachingZone = 'QUESTION' | 'REASONING' | 'TUTOR_SOLUTION';
export type CanvasTeachingColor = 'NAVY' | 'AMBER' | 'TEAL';
export type CanvasTeachingMode =
  | 'GUIDED' | 'DIRECT_EXPLANATION' | 'HINT' | 'VISUAL_CUE' | 'SCAFFOLD'
  | 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';

export interface CanvasTeachingOperation {
  operation_id: string;
  kind: CanvasTeachingOperationKind;
  target_kind: CanvasTeachingTargetKind;
  target_ids: string[];
  zone: CanvasTeachingZone;
  persistence: 'PULSE' | 'PERSIST';
  evidence_ref?: string | null;
  text?: string | null;
  latex?: string | null;
  color_role?: CanvasTeachingColor;
  /** Server-assigned slot for a learner-confirmed note; never a coordinate. */
  scene_slot?: string | null;
}

export interface CanvasTeachingBeat {
  beat_id: string;
  sequence: number;
  /** An exact span of `message_voice`. */
  speech_anchor: { start_char: number; end_char: number; text: string };
  operations: CanvasTeachingOperation[];
}

export interface CanvasTeachingPlan {
  plan_id: string;
  question_id: string;
  source_turn_id: string;
  tutor_turn_id?: string | null;
  scene_revision: number;
  mode: 'append' | 'replace';
  teaching_mode: CanvasTeachingMode;
  beats: CanvasTeachingBeat[];
}

// ─── What a beat becomes on screen ──────────────────────────────────────────

/**
 * A mark on a token of the question text.
 *
 * Rendered by AnchoredText, not the canvas, for the reason the question
 * anchors already are: the question is HTML that rewraps with the panel, and
 * only the text renderer knows where the token currently is.
 */
export interface TeachingTokenMark {
  id: string;
  tokenId: string;
  style: 'highlight' | 'circle' | 'box' | 'check';
  color: CanvasTeachingColor;
  /** Temporary emphasis; the store takes it down after PULSE_MS. */
  pulse: boolean;
}

/** An arrow between two question tokens (CONNECT). */
export interface TeachingConnector {
  id: string;
  fromTokenId: string;
  toTokenId: string;
  color: CanvasTeachingColor;
  pulse: boolean;
}

export interface TeachingEffects {
  tokenMarks: TeachingTokenMark[];
  connectors: TeachingConnector[];
  /** Tutor-layer canvas marks. Every id starts with TEACHING_ID_PREFIX. */
  elements: TutorElement[];
  /** Ids (of any of the three) that are temporary. */
  pulseIds: string[];
}

/** How long a PULSE stays up. */
export const PULSE_MS = 2400;

/** Every tutor-layer mark this contract draws. `mode: replace` removes exactly these. */
export const TEACHING_ID_PREFIX = 'ctp:';

/** Handoff rule 4: amber changes, teal is fixed structure, navy is confirmed. */
export const TEACHING_COLORS: Record<CanvasTeachingColor, string> = {
  AMBER: '#FF9F1C', // highlight-amber
  TEAL: '#008B8B',  // dark-cyan
  NAVY: '#1B2A4A',  // focus-navy
};

// ─── Which plan applies ─────────────────────────────────────────────────────

export interface ResponseScene {
  interaction_state_version?: number | null;
  accepted_turn_id?: string | null;
}

/**
 * Does this plan belong to the response it arrived on? (handoff rule 1)
 *
 * The question itself is checked again when each beat fires, because on the
 * voice transport the phase and question are applied AFTER the support, and
 * because the student can move on while the tutor is still talking. A field
 * the response did not send is not a mismatch — see `shouldApply`.
 */
export function planMatchesResponse(plan: CanvasTeachingPlan, response: ResponseScene): boolean {
  if (plan.teaching_mode === 'PARALLEL_EXAMPLE') return false; // never emitted; never drawn
  const version = response.interaction_state_version;
  if (version !== undefined && version !== null && version !== plan.scene_revision) return false;
  const turn = response.accepted_turn_id;
  if (turn && turn !== plan.source_turn_id) return false;
  return Array.isArray(plan.beats) && plan.beats.length > 0;
}

export interface VisibleScene {
  phase: string;
  questionId: string | null;
  version: number | null;
}

/** Is the scene this plan was made for still the one on screen? */
export function planStillVisible(plan: CanvasTeachingPlan, scene: VisibleScene): boolean {
  return scene.phase === 'GUIDED_PRACTICE'
    && scene.questionId === plan.question_id
    && (scene.version === null || scene.version === plan.scene_revision);
}

/**
 * Where a beat starts, as a fraction of the narration.
 *
 * A fraction rather than a character offset because the line actually voiced
 * is not always `message_voice` character for character (a scaffold turn
 * speaks the step's own voice line), and no engine reports word timings — see
 * `tutorSpeechProgress`.
 */
export function beatStart(beat: CanvasTeachingBeat, narrationLength: number): number {
  if (narrationLength <= 0) return 0;
  return Math.min(1, Math.max(0, beat.speech_anchor.start_char / narrationLength));
}

// ─── Mode rules (handoff "Required behaviour by teaching mode") ─────────────

const WRITES = new Set<CanvasTeachingOperationKind>(['WRITE_TEXT', 'WRITE_MATH']);
/** Pulse / circle / highlight only — nothing that completes the rule. */
const ATTENTION_ONLY = new Set<CanvasTeachingMode>(['HINT', 'VISUAL_CUE', 'SCAFFOLD']);

export function operationPermitted(op: CanvasTeachingOperation, mode: CanvasTeachingMode): boolean {
  if (mode === 'PARALLEL_EXAMPLE') return false;
  const writes = WRITES.has(op.kind);
  if ((writes || op.kind === 'CHECK') && ATTENTION_ONLY.has(mode)) return false;
  if (!writes) return true;
  // Written ink never goes in the question, and must name its zone.
  if (op.target_kind !== 'CANVAS_ZONE' || op.zone === 'QUESTION') return false;
  // A direct explanation is concrete examples in the reasoning zone, only.
  if (mode === 'DIRECT_EXPLANATION') return op.zone === 'REASONING';
  return true;
}

// ─── The reasoning trail ────────────────────────────────────────────────────

/**
 * Where written tutor ink goes: the column between the reference labels and
 * the support lane, which is also where a tutor-solved rescue writes its steps.
 *
 * Right of WRITE_AREA (x ends 0.40) by construction, so nothing here can land
 * where the student is asked to write (handoff rule 5). Shared with the rescue
 * column on purpose: on a Tutor Solved turn the plan illustrates the same step
 * the rescue just wrote, and a trail somewhere else would split one idea across
 * the board. Rows are allocated BELOW everything already in the column, so the
 * two never overprint — the occupancy rule the confirmation ladder uses.
 */
const TRAIL_X = 0.44;
const TRAIL_FIRST_Y = 0.14;
const TRAIL_GAP = 0.075;
const TRAIL_LAST_Y = 0.86;
const TRAIL_SIZE = 22;
/** A check tick sits in the margin just left of the line it checks. */
const CHECK_OFFSET = 0.03;
const ROW_SUFFIX = ':row';

function isTrailRow(el: TutorElement): boolean {
  return el.id.startsWith(TEACHING_ID_PREFIX) && el.id.endsWith(ROW_SUFFIX);
}

/** The first free row of the trail, below whatever the column already holds. */
export function nextTrailRow(elements: TutorElement[], top: number = TRAIL_FIRST_Y): number {
  let y = top;
  for (const el of elements) {
    if (el.y === undefined) continue;
    if (el.id.endsWith(RESCUE_SUFFIX)) y = Math.max(y, el.y + RESCUE_GAP);
    else if (isTrailRow(el)) y = Math.max(y, el.y + TRAIL_GAP);
  }
  return Math.min(TRAIL_LAST_Y, y);
}

// ─── Resolving a beat ───────────────────────────────────────────────────────

export interface TeachingContext {
  anchors: QuestionAnchor[];
  items: DrawnItem[];
  tutorElements: TutorElement[];
  canvasSize: CanvasSize;
  /** Bottom of the question strip in canvas px, from `questionStripBottom`. */
  stripBottomPx?: number | null;
}

const PAD = 0.012;
const HIGHLIGHT_WEIGHT = 16;

function padded(box: CanvasBBox): CanvasBBox {
  return {
    x: Math.max(0, box.x - PAD),
    y: Math.max(0, box.y - PAD),
    w: Math.min(1, box.w + PAD * 2),
    h: Math.min(1, box.h + PAD * 2),
  };
}

/**
 * Everything one beat draws.
 *
 * Operations are resolved against `ctx` in order, and the trail rows written
 * by earlier operations of the same beat count as occupied for later ones.
 */
export function beatEffects(
  plan: CanvasTeachingPlan,
  beat: CanvasTeachingBeat,
  ctx: TeachingContext,
): TeachingEffects {
  const out: TeachingEffects = { tokenMarks: [], connectors: [], elements: [], pulseIds: [] };
  const top = ladderTop(TRAIL_FIRST_Y, ctx.stripBottomPx ?? null, ctx.canvasSize.height);
  const frame = { ...ctx.canvasSize };

  for (const op of beat.operations ?? []) {
    if (!op || !Array.isArray(op.target_ids)) continue;
    if (!operationPermitted(op, plan.teaching_mode)) continue;

    const id = `${TEACHING_ID_PREFIX}${plan.plan_id}:${beat.beat_id}:${op.operation_id}`;
    const color = op.color_role ?? 'NAVY';
    // FOCUS and HIGHLIGHT are emphasis ("temporary emphasis" in the mapping);
    // a HIGHLIGHT the backend marks PERSIST is kept.
    const pulse = op.persistence === 'PULSE' || op.kind === 'FOCUS';
    const ink = TEACHING_COLORS[color];

    if (op.target_kind === 'QUESTION_ANCHOR') {
      // Only tokens the question actually rendered. A SCAFFOLD may only point
      // at what the learner has already confirmed.
      const tokens = op.target_ids.filter((tokenId) => ctx.anchors.some(
        (a) => a.token_id === tokenId && (plan.teaching_mode !== 'SCAFFOLD' || a.confirmed),
      ));
      if (tokens.length !== op.target_ids.length) continue;

      if (op.kind === 'CONNECT') {
        for (let i = 1; i < tokens.length; i += 1) {
          const connectorId = `${id}:${i}`;
          out.connectors.push({ id: connectorId, fromTokenId: tokens[i - 1], toTokenId: tokens[i], color, pulse });
          if (pulse) out.pulseIds.push(connectorId);
        }
        continue;
      }
      const style = op.kind === 'CIRCLE' ? 'circle'
        : op.kind === 'BOX' ? 'box'
          : op.kind === 'CHECK' ? 'check'
            : op.kind === 'FOCUS' || op.kind === 'HIGHLIGHT' ? 'highlight'
              : null;
      if (!style) continue; // a write aimed at a token: refused by the contract
      tokens.forEach((tokenId, i) => {
        const markId = `${id}:${i}`;
        out.tokenMarks.push({ id: markId, tokenId, style, color, pulse });
        if (pulse) out.pulseIds.push(markId);
      });
      continue;
    }

    if (op.target_kind === 'STUDENT_TOKEN') {
      // Only against what is on the board right now (handoff rule 2).
      const boxes = op.target_ids.map((itemId) => {
        const item = ctx.items.find((it) => it.id === itemId);
        return item ? itemBBox(item, ctx.canvasSize) : null;
      });
      if (boxes.some((b) => !b)) continue;
      const resolved = (boxes as CanvasBBox[]).map(padded);
      const marks = studentTokenMarks(op, id, resolved, ink);
      for (const mark of marks) {
        out.elements.push({ ...mark, frame });
        if (pulse) out.pulseIds.push(mark.id);
      }
      continue;
    }

    // CANVAS_ZONE. Only writing and checking have a zone-level meaning; a
    // circle round "the reasoning zone" points at nothing in particular.
    if (WRITES.has(op.kind)) {
      const content = (op.kind === 'WRITE_MATH' ? op.latex ?? op.text : op.text ?? op.latex)?.trim();
      if (!content) continue;
      if (op.scene_slot) {
        const sceneElements = sceneNoteElements(
          plan.question_id,
          op.scene_slot,
          op.kind,
          content,
          top,
          TEACHING_COLORS,
          [...ctx.tutorElements, ...out.elements],
        );
        if (sceneElements !== null) {
          out.elements.push(...sceneElements);
          if (pulse) out.pulseIds.push(...sceneElements.map((element) => element.id));
          continue;
        }
      }
      const rowId = `${id}${ROW_SUFFIX}`;
      const y = nextTrailRow([...ctx.tutorElements, ...out.elements], top);
      out.elements.push(op.kind === 'WRITE_MATH'
        ? { id: rowId, kind: 'math', x: TRAIL_X, y, tex: content, color: ink, size: TRAIL_SIZE }
        : { id: rowId, kind: 'text', x: TRAIL_X, y, text: content, color: ink, size: TRAIL_SIZE, wrapWidth: RESCUE_WRAP_WIDTH });
      if (pulse) out.pulseIds.push(rowId);
      continue;
    }
    if (op.kind === 'CHECK') {
      // Ticks the latest line of the trail — the step just said aloud.
      const rows = [...ctx.tutorElements, ...out.elements].filter(isTrailRow);
      const last = rows.reduce<TutorElement | null>((a, b) => (!a || (b.y ?? 0) >= (a.y ?? 0) ? b : a), null);
      if (!last || last.y === undefined) continue;
      const tickId = `${id}:check`;
      out.elements.push({ id: tickId, kind: 'text', x: TRAIL_X - CHECK_OFFSET, y: last.y, text: '✓', color: ink, size: TRAIL_SIZE, fontStyle: 'bold' });
      if (pulse) out.pulseIds.push(tickId);
    }
  }
  return out;
}

/** Tutor-layer marks around the student's own ink. */
function studentTokenMarks(
  op: CanvasTeachingOperation,
  id: string,
  boxes: CanvasBBox[],
  color: string,
): TutorElement[] {
  switch (op.kind) {
    case 'FOCUS':
    case 'HIGHLIGHT':
      return boxes.map((b, i) => ({
        id: `${id}:hl${i}`, kind: 'highlight', color, strokeWidth: HIGHLIGHT_WEIGHT,
        points: [b.x, b.y + b.h / 2, b.x + b.w, b.y + b.h / 2],
      }));
    case 'CIRCLE':
      return boxes.map((b, i) => ({
        id: `${id}:ring${i}`, kind: 'ellipse', color, strokeWidth: 2,
        x: b.x + b.w / 2, y: b.y + b.h / 2, w: b.w * 1.15, h: b.h * 1.3,
      }));
    case 'BOX':
      return boxes.map((b, i) => ({ id: `${id}:box${i}`, kind: 'rect', color, strokeWidth: 2, ...b }));
    case 'CONNECT':
      return boxes.slice(1).map((b, i) => {
        const a = boxes[i];
        return {
          id: `${id}:link${i}`, kind: 'arrow', color, strokeWidth: 2,
          from: [a.x + a.w / 2, a.y + a.h] as [number, number],
          to: [b.x + b.w / 2, b.y] as [number, number],
        };
      });
    case 'CHECK':
      return boxes.map((b, i) => ({
        id: `${id}:check${i}`, kind: 'text', text: '✓', color, size: TRAIL_SIZE, fontStyle: 'bold',
        x: Math.min(0.97, b.x + b.w + 0.01), y: b.y,
      }));
    default:
      return [];
  }
}

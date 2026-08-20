/**
 * Semantic tutor canvas actions — turning a coordinate-free instruction into
 * something on screen (Sanya, 19 Aug 2026).
 *
 * The contract's whole point is that the backend never sends geometry. It sends
 * WHAT to point at, by a stable id, and the client is the only side that knows
 * where that id currently sits — the question can rewrap, the student can write
 * anywhere, and the canvas can be any size. So every action is resolved against
 * local state at render time, and an action whose target cannot be found is
 * DROPPED rather than placed somewhere plausible.
 *
 * That last rule is the same one the question anchors follow, for the same
 * reason: a highlight on the wrong token teaches the wrong thing, and is worse
 * than no highlight at all. A tutor pointing confidently at the wrong symbol is
 * not a cosmetic bug.
 *
 * What this module deliberately does NOT do:
 *
 *   - decide correctness, advance a question, count an attempt, escalate
 *     support, or unlock an answer reveal. Those are backend-owned, and
 *     `answer_reveal_allowed` grants nothing here — see `revealsAnswer`.
 *   - touch student ink. Marks are tutor-layer only; the student's strokes are
 *     immutable and fading one is a visual state, never a deletion.
 *   - prefill a WRITE_AREA. The tutor may ask for the rule; it must never write
 *     the rule into the place the student is being asked to write it.
 */

import type { QuestionAnchor } from '@/lib/questionAnchors';
import {
  itemBBox, tutorElementBBox,
  type CanvasBBox, type CanvasSize, type CanvasActionType,
} from '@/lib/canvasMemory';
import type { DrawnItem, TutorCanvasAction, TutorElement } from '@/store/useNumeraStore';

/** Where an action's target turned out to be, once resolved locally. */
export type ResolvedTarget =
  /** A span of the question text; the label rides on the anchor, not the canvas. */
  | { kind: 'anchor'; tokenId: string }
  /** A box on the canvas, normalised 0–1 against the live canvas size. */
  | { kind: 'box'; box: CanvasBBox }
  /** The area the student is being asked to write in. Carries no content. */
  | { kind: 'write-area' };

export interface ResolveContext {
  anchors: QuestionAnchor[];
  items: DrawnItem[];
  tutorElements: TutorElement[];
  canvasSize: CanvasSize;
}

/**
 * Resolve an action's target against what the client can currently see.
 *
 * Null means "not found here" — the caller drops the action. A missing target
 * is expected and ordinary: the backend may reference an object the student has
 * since erased, or an anchor for a question that has already moved on.
 */
export function resolveTarget(
  action: TutorCanvasAction,
  ctx: ResolveContext,
): ResolvedTarget | null {
  if (action.target_kind === 'WRITE_AREA') return { kind: 'write-area' };

  const id = action.target_object_id?.trim();
  if (!id) return null;

  if (action.target_kind === 'QUESTION_ANCHOR') {
    return ctx.anchors.some((a) => a.token_id === id) ? { kind: 'anchor', tokenId: id } : null;
  }

  if (action.target_kind === 'TUTOR_ANCHOR') {
    const element = ctx.tutorElements.find((el) => el.id === id);
    const box = element ? tutorElementBBox(element) : null;
    return box ? { kind: 'box', box } : null;
  }

  // CANVAS_OBJECT and STUDENT_ATTEMPT both name a thing the student drew. They
  // differ in what the tutor means by it, not in how it is found.
  const item = ctx.items.find((it) => it.id === id);
  const box = item ? itemBBox(item, ctx.canvasSize) : null;
  return box ? { kind: 'box', box } : null;
}

/** Breathing room around a box so a highlight frames the work, not clips it. */
const PAD = 0.012;
const INK = '#1B2A4A';
const EMPHASIS = '#C9A227';

function padded(box: CanvasBBox): CanvasBBox {
  return {
    x: Math.max(0, box.x - PAD),
    y: Math.max(0, box.y - PAD),
    w: Math.min(1, box.w + PAD * 2),
    h: Math.min(1, box.h + PAD * 2),
  };
}

/**
 * Does this action put a final answer on the board?
 *
 * `answer_reveal_allowed` is read ONLY to refuse — never to permit. The backend
 * owns the reveal policy (§"Answer reveal remains blocked except for the final
 * approved tutor-solved condition"), and a client that unlocked a reveal
 * because a payload said it could would make the flag a second source of truth
 * for the one decision the spec insists has one. So a `true` flag changes
 * nothing about what is rendered; it is the backend's own record, not our
 * permission slip.
 */
export function revealsAnswer(): boolean {
  return false;
}

/**
 * The tutor-layer marks an action becomes, or [] when it draws nothing.
 *
 * Empty is a normal outcome, not a failure: FOCUS moves attention without
 * leaving a mark, an anchor label rides on the question text rather than the
 * canvas, and a WRITE_AREA deliberately renders no content at all.
 */
export function actionMarks(
  action: TutorCanvasAction,
  target: ResolvedTarget,
): TutorElement[] {
  // The rule that matters most here. WRITE_AREA is the place the student is
  // being asked to commit the answer; writing the answer into it would hand
  // them the thing that was being asked for, and would do it while looking
  // like ordinary tutor support.
  if (target.kind === 'write-area') return [];

  // A question-text anchor is styled by the text renderer (AnchoredText), which
  // knows where the token actually wrapped to. Drawing a box on the canvas for
  // it would put a mark on the board for something that is not on the board.
  if (target.kind === 'anchor') return [];

  const box = target.box;
  const id = (suffix: string) => `${action.action_id}:${suffix}`;

  switch (action.type) {
    case 'HIGHLIGHT':
      return [{ id: id('hl'), kind: 'highlight', ...padded(box), color: EMPHASIS }];

    // A group says "these belong together". Drawn as an outline rather than a
    // fill so it reads as enclosure, and so it stays legible over ink already
    // carrying a highlight.
    case 'GROUP':
      return [{ id: id('grp'), kind: 'rect', ...padded(box), color: EMPHASIS, strokeWidth: 2 }];

    // Arrives from above-left, which is where a tutor's hand comes from and
    // keeps the arrow clear of the work it points at.
    case 'ARROW': {
      const p = padded(box);
      return [{
        id: id('arw'),
        kind: 'arrow',
        from: [Math.max(0, p.x - 0.08), Math.max(0, p.y - 0.06)],
        to: [p.x, p.y],
        color: INK,
        strokeWidth: 2,
      }];
    }

    // Written just under the work it comments on, so the two read as one idea.
    case 'INSERT_MATH':
    case 'INSERT_LABEL': {
      const text = action.text?.trim();
      if (!text) return [];
      const p = padded(box);
      return [{
        id: id('txt'),
        kind: action.type === 'INSERT_MATH' ? 'math' : 'text',
        x: p.x,
        y: Math.min(1, p.y + p.h + 0.02),
        text,
        color: INK,
        size: 26,
      }];
    }

    // FOCUS draws nothing — it is an emphasis instruction, and the support
    // rungs (cue, scaffold, parallel, tutor-solved) render in their own panels
    // rather than on the canvas.
    default:
      return [];
  }
}

/** Does this action ask for the tutor-owned write affordance (and nothing else)? */
export function showsWriteAffordance(action: TutorCanvasAction): boolean {
  return action.target_kind === 'WRITE_AREA';
}

/**
 * The canvas-memory action type for a semantic action.
 *
 * `OPEN_SCAFFOLD_STEP` is the one name that differs between the two
 * vocabularies — ordered memory has always called it `SCAFFOLD_STEP`. Kept in
 * one place because it was already written out twice and a third caller
 * assigned the raw value, which does not compile.
 */
export function memoryActionType(type: TutorCanvasAction['type']): CanvasActionType {
  return type === 'OPEN_SCAFFOLD_STEP' ? 'SCAFFOLD_STEP' : type;
}

/** Support rungs are the system's doing, not a tutor mark on the board. */
export function memoryActor(type: TutorCanvasAction['type']): 'TUTOR' | 'SYSTEM_SUPPORT' {
  return type === 'SHOW_CUE' || type === 'OPEN_SCAFFOLD_STEP' ? 'SYSTEM_SUPPORT' : 'TUTOR';
}

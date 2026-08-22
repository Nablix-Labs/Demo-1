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
  | { kind: 'write-area' }
  /** A reserved reference slot, clear of the writing area. Text sits AT the point. */
  | { kind: 'slot'; at: { x: number; y: number } };

export interface ResolveContext {
  anchors: QuestionAnchor[];
  questionId: string | null;
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
    const writeRuleMatch = id.match(/^TUTOR_ANCHOR:WRITE_RULE:(\d+)$/);
    if (writeRuleMatch) return nextSlot(ctx.tutorElements, WRITE_RULE_X);
    const confirmedMatch = id.match(/^TUTOR_ANCHOR:CONFIRMED:(.+):(\d+)$/);
    if (confirmedMatch) {
      return confirmedMatch[1] === ctx.questionId ? nextSlot(ctx.tutorElements, CONFIRMED_X) : null;
    }
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

/**
 * The writing area, mirrored from the backend's own write-request draw
 * (canvas_annotations.plan_write_request_tutor_draw): a highlight band across
 * x 0.58–0.92 / y 0.62–0.74, the prompt "Write your rule here." at (0.62, 0.66),
 * and an arrow dropping into it at x 0.75 from y 0.56.
 *
 * Kept here so the reference slots below are positioned AGAINST it rather than
 * by independent guesswork. The first attempt put the slots at y 0.58 and 0.65,
 * which rendered their labels at y 0.652 and 0.722 — one on top of the prompt,
 * the other inside the band. Two sets of magic numbers chosen apart from each
 * other will always eventually land on each other.
 */
export const WRITE_AREA = { x: 0.06, y: 0.58, w: 0.34, h: 0.12 };
const WRITE_ARROW_TOP = 0.52;

/**
 * Where the writing block sits, and why it is on the LEFT.
 *
 * The backend hardcodes this block on the right (x 0.58-0.92) — the one place
 * it does send coordinates, which the semantic-action contract otherwise
 * forbids ("never sends pixels, dimensions, coordinates"). The right-hand
 * column is where the cue card, the hint note and the "write it down" note
 * live, so the writing block landed underneath them and the student had, in
 * Sanya's words, nowhere to write.
 *
 * Layout is the client's job — it is the only side that knows what else is on
 * screen — so the block is relocated here rather than left where the payload
 * put it. `relocateWriteRequest` moves the backend's own three elements onto
 * the same geometry the reference slots are positioned against, so the labels,
 * the arrow, the band and the prompt always travel together.
 */
export const WRITE_PROMPT_AT = { x: WRITE_AREA.x + 0.04, y: WRITE_AREA.y + 0.04 };
const WRITE_ARROW_X = WRITE_AREA.x + 0.10;

/**
 * Where a reference label goes.
 *
 * Two kinds of label share this column: the persistent CONFIRMED notes ("m →
 * changes") and the WRITE_RULE parts the tutor shows while asking for the rule.
 * They are allocated from ONE ladder, by occupancy — the next label goes on the
 * first free row, whatever kind it is.
 *
 * Occupancy rather than the position the backend sends, because the backend
 * numbers each turn from 1 and has no memory of what is already on the canvas
 * (`add_confirmation_canvas_slots` enumerates that turn's actions). Three
 * confirmations arriving on three separate turns are therefore all "position 1",
 * and every one of them landed on the same row: Sanya's m + 7 screenshot, where
 * "7 → fixed" and "+ → addition" were written on top of "m → changes". The
 * client is the only side that knows what is already on the board, which is the
 * same reason every other target here resolves locally.
 *
 * Downward, so the first label sits highest and the parts read in the order they
 * were confirmed. Bounded above the writing area: the arrow into it starts at
 * WRITE_ARROW_TOP, and a reference that drifts into the band the student answers
 * in stops being a reference.
 */
const SLOT_FIRST_Y = 0.14;
const SLOT_GAP = 0.07;
/** Never below this: the arrow into the writing area starts at WRITE_ARROW_TOP. */
const SLOT_LAST_Y = 0.46;

/** A slot mark, identified by the suffix `actionMarks` gives it. */
const SLOT_SUFFIX = ':slot';

/** How many reference rows are already occupied. */
export function occupiedSlots(tutorElements: TutorElement[]): number {
  return tutorElements.filter((el) => el.id.endsWith(SLOT_SUFFIX)).length;
}

/** The first free row, at the given column. */
export function nextSlot(tutorElements: TutorElement[], x: number): ResolvedTarget {
  const index = occupiedSlots(tutorElements);
  return { kind: 'slot', at: { x, y: Math.min(SLOT_LAST_Y, SLOT_FIRST_Y + index * SLOT_GAP) } };
}

/** WRITE_RULE parts are indented, so a reference still reads apart from a note. */
const WRITE_RULE_X = WRITE_AREA.x + 0.04;
/** Persistent tutor confirmations sit at the left margin. */
const CONFIRMED_X = 0.06;

/** Does this box overlap the writing area? Used by the tests, and by nothing else. */
export function overlapsWriteArea(box: CanvasBBox): boolean {
  return (
    box.x < WRITE_AREA.x + WRITE_AREA.w
    && box.x + box.w > WRITE_AREA.x
    && box.y < WRITE_AREA.y + WRITE_AREA.h
    && box.y + box.h > WRITE_AREA.y
  );
}

/** Breathing room around a box so a highlight frames the work, not clips it. */
const PAD = 0.012;
const INK = '#1B2A4A';
/** Highlighter thickness in px, matching the backend's own write-area band. */
const HIGHLIGHT_WEIGHT = 16;
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

  // A reserved slot takes its text exactly where the slot is — no offset. The
  // offset below applies to marks that COMMENT on something, which sit under the
  // thing they comment on; a slot is the position itself.
  if (target.kind === 'slot') {
    const slotText = action.text?.trim();
    if (!slotText) return [];
    return [{
      id: `${action.action_id}:slot`,
      kind: action.type === 'INSERT_MATH' ? 'math' : 'text',
      x: target.at.x,
      y: target.at.y,
      text: slotText,
      color: INK,
      // Bolder than an ordinary tutor mark: these are the reference the student
      // is meant to read while writing, not a passing annotation (Sanya).
      size: 26,
      fontStyle: 'bold',
    }];
  }

  const box = target.box;
  const id = (suffix: string) => `${action.action_id}:${suffix}`;

  switch (action.type) {
    case 'HIGHLIGHT': {
      // A highlight is drawn as a stroke through `points`, like a highlighter
      // pen — TutorLayer's `highlight` case reads ONLY `points` and returns null
      // without them, so the x/y/w/h this used to emit rendered nothing at all.
      const p = padded(box);
      const midY = p.y + p.h / 2;
      return [{
        id: id('hl'),
        kind: 'highlight',
        points: [p.x, midY, p.x + p.w, midY],
        color: EMPHASIS,
        strokeWidth: HIGHLIGHT_WEIGHT,
      }];
    }

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


/** Suffixes the backend gives the three elements of its write request. */
const WRITE_HIGHLIGHT = ':write-highlight';
const WRITE_PROMPT = ':write-prompt';
const WRITE_ARROW = ':write-arrow';

/**
 * Move the backend's write-request block onto the client's layout.
 *
 * Returns the elements unchanged except for the three the backend positions by
 * hand. Matched on the id suffix, which the backend builds from the turn id
 * (`f"{turn_id}:write-highlight"` and friends) and so is stable.
 *
 * An element the backend stops sending simply never matches; one it renames
 * passes through at its original coordinates, which is visibly wrong rather
 * than silently wrong, and is the failure we want of the two.
 */
export function relocateWriteRequest(elements: TutorElement[]): TutorElement[] {
  return elements.map((el) => {
    if (el.id.endsWith(WRITE_HIGHLIGHT)) {
      const { x, y, w, h } = WRITE_AREA;
      return { ...el, x: undefined, y: undefined, w: undefined, h: undefined,
        points: [x, y, x + w, y, x + w, y + h, x, y + h] };
    }
    if (el.id.endsWith(WRITE_PROMPT)) {
      return { ...el, x: WRITE_PROMPT_AT.x, y: WRITE_PROMPT_AT.y, points: undefined };
    }
    if (el.id.endsWith(WRITE_ARROW)) {
      return { ...el,
        from: [WRITE_ARROW_X, WRITE_ARROW_TOP],
        to: [WRITE_ARROW_X, WRITE_AREA.y],
        points: undefined };
    }
    return el;
  });
}

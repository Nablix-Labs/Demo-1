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
import {
  parseRescueAnchor, answerRevealPermitted, writesToStudentCanvas,
} from '@/lib/rescueActions';

/** Where an action's target turned out to be, once resolved locally. */
export type ResolvedTarget =
  /** A span of the question text; the label rides on the anchor, not the canvas. */
  | { kind: 'anchor'; tokenId: string }
  /** A box on the canvas, normalised 0–1 against the live canvas size. */
  | { kind: 'box'; box: CanvasBBox }
  /** The area the student is being asked to write in. Carries no content. */
  | { kind: 'write-area' }
  /** A reserved reference slot, clear of the writing area. Text sits AT the point. */
  | { kind: 'slot'; at: { x: number; y: number } }
  /** A rescue step's row. Its own ladder — see RESCUE_X. */
  | { kind: 'rescue-slot'; at: { x: number; y: number } };

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
    // A rescue step's anchor is registered by the renderer itself, from the
    // action, so it resolves without anything having to be on the board first.
    // That is what stops a rescue arriving before its anchor exists — the case
    // the ordinary "target not on screen" drop was written for, and which for
    // a rescue would drop the only step the student was going to be shown.
    //
    // Both ladders below start clear of whatever the question strip currently
    // occupies; see `ladderTop`. Measured per action rather than cached: the
    // question rewraps with the panel and the viewport, and a turn only ever
    // carries a handful of actions.
    const stripBottom = questionStripBottom(
      typeof document === 'undefined' ? undefined : document,
    );
    const topFor = (fixed: number) => ladderTop(fixed, stripBottom, ctx.canvasSize.height);

    const rescue = parseRescueAnchor(id);
    if (rescue) return rescueSlot(rescue.stepIndex, topFor(RESCUE_FIRST_Y));
    const writeRuleMatch = id.match(/^TUTOR_ANCHOR:WRITE_RULE:(\d+)$/);
    if (writeRuleMatch) {
      return nextSlot(ctx.tutorElements, WRITE_RULE_X, topFor(SLOT_FIRST_Y));
    }
    const confirmedMatch = id.match(/^TUTOR_ANCHOR:CONFIRMED:(.+):(\d+)$/);
    if (confirmedMatch) {
      return confirmedMatch[1] === ctx.questionId
        ? nextSlot(ctx.tutorElements, CONFIRMED_X, topFor(SLOT_FIRST_Y))
        : null;
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

/* ── Clearing the question strip ────────────────────────────────────────────
 *
 * SLOT_FIRST_Y and RESCUE_FIRST_Y are fractions of the WHOLE canvas, measured
 * from its top edge — and the question strip is an HTML overlay sitting on that
 * same top edge (Canvas/index.tsx, `absolute top-[26px]`), whose height depends
 * entirely on the question. A one-line question ends around 70px and the fixed
 * ladder clears it; the Topic 1 general-rule question is three worked rows plus
 * two wrapped prose lines, ends near 200px, and the first two rows land inside
 * it. That is Manjusha's 1 Sep screenshot: "Start: n" beside `14 + 5`, and
 * "Gain: +5" written across the word "rule".
 *
 * So the top is measured rather than assumed, which is the rule the rest of
 * this module already follows — the client is the only side that knows where
 * anything currently is. The fixed constants stay as the floor: a short
 * question must not push the labels DOWN from where they have always been.
 */

/** Breathing room between the bottom of the question and the first label. */
const LADDER_PAD = 0.03;

/**
 * The lowest a ladder may be pushed to.
 *
 * Two rows still fit below it (0.39, then 0.46) before SLOT_LAST_Y clamps them
 * onto each other. Past this the honest answer is that the question is too tall
 * to also hold a reference column, and crowding the writing area — the arrow
 * into it starts at WRITE_ARROW_TOP — would cost more than the overlap does.
 */
const LADDER_TOP_MAX = 0.39;

/**
 * How far down the canvas the question strip reaches, in canvas pixels.
 *
 * Null when there is nothing to measure — server render, tests, or a screen
 * with no question — and the caller then keeps the fixed ladder. Read off the
 * live DOM like `rescueReturn`, for the same reason: layout is only knowable
 * where it is laid out.
 */
export function questionStripBottom(doc: Document | undefined): number | null {
  const canvas = doc?.querySelector<HTMLElement>('[aria-label="Drawing canvas"]');
  const strip = doc?.querySelector<HTMLElement>('[data-question-text]');
  if (!canvas || !strip) return null;
  const stripRect = strip.getBoundingClientRect();
  if (stripRect.height === 0) return null;
  return stripRect.bottom - canvas.getBoundingClientRect().top;
}

/** The first row of a ladder, clear of the question strip. */
export function ladderTop(
  fixedTop: number,
  stripBottomPx: number | null,
  canvasHeight: number,
): number {
  if (stripBottomPx === null || canvasHeight <= 0) return fixedTop;
  const clear = stripBottomPx / canvasHeight + LADDER_PAD;
  return Math.max(fixedTop, Math.min(LADDER_TOP_MAX, clear));
}

/** How many reference rows are already occupied. */
export function occupiedSlots(tutorElements: TutorElement[]): number {
  return tutorElements.filter((el) => el.id.endsWith(SLOT_SUFFIX)).length;
}

/** The first free row, at the given column, starting below the question. */
export function nextSlot(
  tutorElements: TutorElement[],
  x: number,
  top: number = SLOT_FIRST_Y,
): ResolvedTarget {
  const index = occupiedSlots(tutorElements);
  return { kind: 'slot', at: { x, y: Math.min(SLOT_LAST_Y, top + index * SLOT_GAP) } };
}

/** WRITE_RULE parts are indented, so a reference still reads apart from a note. */
const WRITE_RULE_X = WRITE_AREA.x + 0.04;
/** Persistent tutor confirmations sit at the left margin. */
const CONFIRMED_X = 0.06;

/**
 * Where a tutor-solved rescue step goes, and why it has its own ladder.
 *
 * The handoff (§4) requires rescue geometry to stay separate from confirmation
 * labels, highlights and write-rule anchors. Separate COLUMN, so a walkthrough
 * never lands on a reference the student is reading while they write; and
 * separate OCCUPANCY, so a three-step walkthrough does not push the next
 * confirmation three rows down a ladder it has nothing to do with.
 *
 * x 0.44 is the gap between the two columns already spoken for: the references
 * and the writing band run to x 0.40, and the cue card, hint note and scaffold
 * panel start at 0.58. Placement is the client's call for the same reason the
 * write block is relocated — this side is the only one that knows what else is
 * on screen. It is a genuinely tight column, and long authored steps will run
 * toward the cards; that is worth watching in the Topic 1 verification.
 *
 * The row comes from `step_index`, NOT from occupancy — the opposite of the
 * confirmation ladder, and deliberately so. Confirmations are numbered per
 * turn by a backend with no memory of the board, so their numbers collide and
 * occupancy is the only reliable order. A rescue step index is authored,
 * persistent and owned by Chirudeva, so step 3 belongs on row 3 — even if it
 * arrives after a reconnect that lost rows 1 and 2, where occupancy would
 * silently promote it to the top and misrepresent where the student is.
 */
const RESCUE_X = 0.44;
const RESCUE_FIRST_Y = 0.14;
const RESCUE_GAP = 0.09;
const RESCUE_LAST_Y = 0.68;

/** A rescue mark, identified by the suffix `actionMarks` gives it. */
export const RESCUE_SUFFIX = ':rescue';

/** The row a rescue step occupies, from its authored index (1-based). */
export function rescueSlot(
  stepIndex: number,
  top: number = RESCUE_FIRST_Y,
): ResolvedTarget {
  const row = Math.max(1, stepIndex) - 1;
  return {
    kind: 'rescue-slot',
    at: { x: RESCUE_X, y: Math.min(RESCUE_LAST_Y, top + row * RESCUE_GAP) },
  };
}

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
 * The band the student is being asked to write in.
 *
 * Nothing the action carries is drawn. A WRITE_AREA action may arrive with
 * `text`, and that text can be the rule itself — putting it on the board would
 * hand the student the very thing they are being asked to produce, dressed as
 * ordinary tutor support. That rule is unchanged; what was missing is the band.
 *
 * The backend's older write request came as three hand-positioned ELEMENTS
 * (`:write-highlight`, `:write-prompt`, `:write-arrow`) which
 * relocateWriteRequest moves onto the geometry below. That is the yellow area
 * Manjusha knows. The semantic action that replaced it drew nothing at all: it
 * raised the rose "write it down" note in the support lane and stopped there,
 * so the ASK survived the migration and the PLACE did not. Row 56, "Phase 2
 * yellow writing area to write the answer is not shown".
 *
 * Same geometry as the relocated block, so the two spellings of one request
 * land in the same place and the reference slots above stay positioned against
 * it. Closed, unlike the backend's three-sided polygon: this is a region to
 * write inside, and an open box reads as a mark someone abandoned.
 *
 * No prompt text. The wording already exists once, on the WriteNote this same
 * action raises; a second copy inside the band would say it twice, and writing
 * canvas copy here is how the frontend starts authoring content it does not own.
 */
function writeAreaMarks(actionId: string): TutorElement[] {
  const { x, y, w, h } = WRITE_AREA;
  return [
    {
      id: `${actionId}${WRITE_HIGHLIGHT}`,
      kind: 'highlight',
      points: [x, y, x + w, y, x + w, y + h, x, y + h, x, y],
      strokeWidth: HIGHLIGHT_WEIGHT,
    },
    {
      id: `${actionId}${WRITE_ARROW}`,
      kind: 'arrow',
      from: [WRITE_ARROW_X, WRITE_ARROW_TOP],
      to: [WRITE_ARROW_X, y],
    },
  ];
}

/**
 * The tutor-layer marks an action becomes, or [] when it draws nothing.
 *
 * Empty is a normal outcome, not a failure: FOCUS moves attention without
 * leaving a mark, and an anchor label rides on the question text rather than
 * the canvas. A WRITE_AREA draws its band but never any CONTENT — that
 * distinction is the whole of writeAreaMarks.
 */
export function actionMarks(
  action: TutorCanvasAction,
  target: ResolvedTarget,
): TutorElement[] {
  // The rule that matters most here. WRITE_AREA is the place the student is
  // being asked to commit the answer; writing the answer into it would hand
  // them the thing that was being asked for, and would do it while looking
  // like ordinary tutor support. So the BAND is drawn and nothing the action
  // carries is — see writeAreaMarks.
  if (target.kind === 'write-area') return writeAreaMarks(action.action_id);

  // A question-text anchor is styled by the text renderer (AnchoredText), which
  // knows where the token actually wrapped to. Drawing a box on the canvas for
  // it would put a mark on the board for something that is not on the board.
  if (target.kind === 'anchor') return [];

  // A rescue step is written at its own row, in its own column.
  //
  // Only the text that arrived. No step is derived, no later step is drawn
  // ahead of time, and nothing is appended when the text is empty — the client
  // has never been told what step 3 says, which is exactly what makes it unable
  // to leak it.
  if (target.kind === 'rescue-slot') {
    const stepText = action.text?.trim();
    if (!stepText) return [];
    // A parallel example is a DIFFERENT problem, so it never goes on the page
    // the student is working on — it belongs in the panel beside the original
    // question (Sanya's "split view"). Only tutor-solved is written here, and
    // only additively. See writesToStudentCanvas for the full account.
    if (!writesToStudentCanvas(action)) return [];
    // The flag is a REQUEST to present this as the answer, re-checked here.
    // When it is set but the action does not satisfy the checkable conditions,
    // the step still renders — it is authored content the student is meant to
    // see — but it renders as an ordinary step rather than as the reveal. That
    // is contract drift, and it is loud, because the alternative is a reveal
    // happening on a rung or a step where none was authorised.
    const reveal = answerRevealPermitted(action);
    if (action.answer_reveal_allowed === true && !reveal) {
      console.warn(
        `[rescue] ${action.action_id} asked for an answer reveal but does not satisfy `
        + 'the final-tutor-solved-step conditions. Rendered as an ordinary step.',
      );
    }
    return [{
      id: `${action.action_id}${RESCUE_SUFFIX}`,
      kind: 'text',
      x: target.at.x,
      y: target.at.y,
      text: stepText,
      color: INK,
      size: 24,
      // The reveal is the one line in a walkthrough the student is meant to
      // land on, so it is the one line set apart.
      fontStyle: reveal ? 'bold' : undefined,
    }];
  }

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

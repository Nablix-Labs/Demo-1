/**
 * Ordered canvas memory — §8 of the Phase 2 V1-Hybrid specification.
 *
 * A snapshot says what the canvas looks like NOW. It cannot say what happened
 * first. The tutor needs the second thing: §8's stated reason is that Sanya
 * "must know not only what is currently visible, but the order in which
 * mathematical thinking appeared", so the tutor can resume at the first
 * unresolved step instead of re-asking something the student already answered.
 *
 * So this is a log, not a scene graph. Two consequences follow, and they are
 * the whole design:
 *
 *  1. **Events are never deleted.** Erasing, undoing and clearing all APPEND an
 *     event and mark the earlier one SUPERSEDED/CLEARED. §11 requires exactly
 *     this — "transient tutor marks may fade/clear visually but remain in
 *     ordered memory". A student who writes `n × 5`, rubs it out and writes
 *     `n + 5` has shown a misconception and corrected it; a delete-in-place log
 *     would leave only the right answer and hide the reasoning that matters.
 *
 *  2. **`order_index` is a position in the log**, so it is the array length at
 *     append time. That only stays monotonic because of (1) — it is not an
 *     independent counter that could drift out of step with the array.
 *
 * ── What this module deliberately does NOT set ──────────────────────────────
 * `semantic_tag` (§8: `changing_part`, `final_rule`, `misconception_test`) is
 * always null here. Those are PEDAGOGICAL judgements — the frontend knows a
 * stroke was drawn, never that it was the final rule. Tagging is Sanya's, on
 * evidence the frontend cannot see. The field is carried so the shape is whole
 * and whoever does the tagging has somewhere to put it.
 *
 * Scope is one question. On a question change the log resets (see the store),
 * because §8's memory answers "where are we in THIS problem". Cross-question
 * history is session state, which Chirudeva persists — see §7.
 */

import type { DrawnItem, TutorElement, TutorElementKind } from '@/store/useNumeraStore';

export type CanvasActor = 'STUDENT' | 'TUTOR' | 'SYSTEM_SUPPORT';

export type CanvasActionType =
  | 'WRITE'
  | 'ERASE'
  | 'CLEAR'
  | 'HIGHLIGHT'
  | 'CIRCLE'
  | 'ARROW'
  | 'INSERT_MATH'
  | 'ANNOTATE'
  | 'SHOW_CUE'
  | 'HIDE_CUE'
  | 'SCAFFOLD_STEP'
  | 'GROUP'
  | 'INSERT_LABEL'
  | 'FOCUS'
  | 'SHOW_PARALLEL'
  | 'TUTOR_SOLVED_STEP';

/** ACTIVE until something replaces it (SUPERSEDED) or wipes the board (CLEARED). */
export type CanvasActiveState = 'ACTIVE' | 'SUPERSEDED' | 'CLEARED';

/** Normalised 0–1 against the live canvas, like `TutorElement` geometry. */
export interface CanvasBBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CanvasEvent {
  order_index: number;
  turn_id: string | null;
  question_id: string | null;
  actor: CanvasActor;
  action_type: CanvasActionType;
  /** Human-readable description of the action, when there is one. */
  content: string | null;
  /** Mathematical interpretation (`n + 5`). OCR fills this in; we rarely can. */
  math_text: string | null;
  /** The `DrawnItem.id` / `TutorElement.id` / cue id this event acted on. */
  target_object_id: string | null;
  bbox: CanvasBBox | null;
  semantic_tag: string | null;
  /** Hint/cue/scaffold id when the action came from DB support (§8). */
  source_id: string | null;
  active_state: CanvasActiveState;
}

/** Everything an appender must decide; the rest has a sane empty default. */
export type CanvasEventDraft =
  Pick<CanvasEvent, 'actor' | 'action_type'> &
  Partial<Omit<CanvasEvent, 'order_index' | 'actor' | 'action_type'>>;

export interface CanvasEventContext {
  turnId: string | null;
  questionId: string | null;
}

export interface CanvasSize {
  width: number;
  height: number;
}

/**
 * Append one event, stamping its position in the log.
 *
 * Pure and returns a new array: the store's `set` needs a new reference to
 * publish, and callers chain several of these in one update.
 */
export function appendCanvasEvent(
  events: CanvasEvent[],
  draft: CanvasEventDraft,
  context: CanvasEventContext,
): CanvasEvent[] {
  return [
    ...events,
    {
      order_index: events.length,
      turn_id: context.turnId,
      question_id: context.questionId,
      content: null,
      math_text: null,
      target_object_id: null,
      bbox: null,
      semantic_tag: null,
      source_id: null,
      active_state: 'ACTIVE',
      ...draft,
    },
  ];
}

/**
 * Retire the ACTIVE events that acted on `targetIds`.
 *
 * Only ACTIVE ones move: an event already CLEARED by a board wipe must not be
 * quietly downgraded to SUPERSEDED by a later erase, or the log would claim the
 * clear never happened.
 */
export function supersedeCanvasEvents(events: CanvasEvent[], targetIds: string[]): CanvasEvent[] {
  if (targetIds.length === 0) return events;
  const targets = new Set(targetIds);
  return events.map((event) =>
    event.active_state === 'ACTIVE' && event.target_object_id && targets.has(event.target_object_id)
      ? { ...event, active_state: 'SUPERSEDED' as const }
      : event,
  );
}

/** Mark every still-ACTIVE event CLEARED. The board is empty; the log is not. */
export function clearCanvasEvents(events: CanvasEvent[]): CanvasEvent[] {
  return events.map((event) =>
    event.active_state === 'ACTIVE' ? { ...event, active_state: 'CLEARED' as const } : event,
  );
}

/**
 * Bounding box of a student item, normalised against the live canvas.
 *
 * Returns null when the canvas has no measured size yet — a box computed
 * against a zero or placeholder size would be a plausible-looking lie, and §8
 * uses bbox to decide what to bring into view.
 */
export function itemBBox(item: DrawnItem, size: CanvasSize): CanvasBBox | null {
  if (size.width <= 0 || size.height <= 0) return null;

  let xs: number[];
  let ys: number[];

  if (item.kind === 'rect' || item.kind === 'ellipse') {
    // w/h may be negative — the shape was dragged up or left.
    xs = [item.x, item.x + item.w];
    ys = [item.y, item.y + item.h];
  } else {
    // Konva flat point arrays: [x0, y0, x1, y1, …].
    xs = item.points.filter((_, i) => i % 2 === 0);
    ys = item.points.filter((_, i) => i % 2 === 1);
    if (xs.length === 0 || ys.length === 0) return null;
  }

  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return {
    x: minX / size.width,
    y: minY / size.height,
    w: (Math.max(...xs) - minX) / size.width,
    h: (Math.max(...ys) - minY) / size.height,
  };
}

/** Tutor geometry is already normalised, so this only has to find the extent. */
export function tutorElementBBox(element: TutorElement): CanvasBBox | null {
  if (element.from && element.to) {
    const [x1, y1] = element.from;
    const [x2, y2] = element.to;
    return {
      x: Math.min(x1, x2), y: Math.min(y1, y2),
      w: Math.abs(x2 - x1), h: Math.abs(y2 - y1),
    };
  }

  if (element.points && element.points.length >= 2) {
    const xs = element.points.filter((_, i) => i % 2 === 0);
    const ys = element.points.filter((_, i) => i % 2 === 1);
    const minX = Math.min(...xs);
    const minY = Math.min(...ys);
    return { x: minX, y: minY, w: Math.max(...xs) - minX, h: Math.max(...ys) - minY };
  }

  if (element.x === undefined || element.y === undefined) return null;
  return { x: element.x, y: element.y, w: element.w ?? 0, h: element.h ?? 0 };
}

/**
 * §8's `action_type` for a tutor mark.
 *
 * `ellipse` maps to CIRCLE because that is what drawing one round the answer
 * MEANS to a student — the vocabulary in §8 is pedagogical, not geometric.
 * Anything with no distinct meaning is ANNOTATE rather than being forced into
 * a nearby word: a wrong verb is worse for the tutor than a vague one.
 */
export function tutorActionType(kind: TutorElementKind): CanvasActionType {
  switch (kind) {
    case 'highlight': return 'HIGHLIGHT';
    case 'ellipse': return 'CIRCLE';
    case 'arrow': return 'ARROW';
    case 'math':
    case 'text': return 'INSERT_MATH';
    default: return 'ANNOTATE';
  }
}

/** What a tutor element says, if anything — `tex` preferred, it is the maths. */
export function tutorElementText(element: TutorElement): string | null {
  return element.tex?.trim() || element.text?.trim() || null;
}

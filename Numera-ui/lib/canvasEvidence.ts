/**
 * The student's working, attached to the turn that talks about it.
 *
 * Whether the tutor can see the board is decided by one field. When
 * `canvas_state` is present on an /interaction request the backend runs OCR
 * over the snapshot and builds a `CanvasEvidence` (interaction_service.py:277);
 * that sets `has_canvas_evidence`, and `review_canvas_math` returns `None`
 * outright without it (classifier.py:4880). No evidence means no canvas review,
 * no mistake classification and nothing to point at — so the tutor answers as
 * if the board were blank.
 *
 * That is what Manjusha hit on 22 Aug: she wrote `n + 5`, said "I fully written
 * that in the Canvas. Please check the Canvas", and got the question she had
 * just answered read back to her. The board was full and the request said
 * nothing about it.
 *
 * The frontend sent `canvas_state` from exactly one of its eight /interaction
 * call sites — the REST voice turn. Typed answers, help requests and explain
 * again all omitted it, which is every turn a student takes with the keyboard.
 *
 * This module is the one place that builds the field, so "which turns carry the
 * canvas" is a question with a single answer instead of eight.
 */

import type { CanvasEvent } from '@/lib/canvasMemory';
import type { InteractionCanvasState } from '@/lib/api';
import { canvasEventsForSubmission, canvasStrokesForSubmission } from '@/lib/api';
import type { CanvasSnapshot } from '@/store/useNumeraStore';

/**
 * Server-side hard limits, mirrored so we degrade instead of being rejected.
 *
 * `validate_canvas_payload` (canvas_evidence.py) answers **413** above either
 * of these. Before this module only the voice turn sent evidence and nobody had
 * filled a canvas hard enough to trip it; attaching evidence to every typed
 * turn makes a long question genuinely capable of it, and a 413 is not a
 * degraded answer — it is the turn failing outright, which is worse than the
 * blindness this module exists to fix.
 */
export const MAX_CANVAS_STROKE_POINTS = 10_000;
export const MAX_CANVAS_EVENTS = 500;

/**
 * Keep the newest work that fits, in whole strokes.
 *
 * Newest rather than oldest because the turn is about what the student just
 * wrote. Whole strokes rather than a flat point budget because a half-sent
 * stroke is worse evidence than no stroke: `align_step_tokens` would place a
 * token on geometry that stops mid-symbol.
 *
 * The snapshot still shows everything either way — this only costs the spatial
 * precision of the oldest work, so an over-full canvas loses the ability to
 * circle a symbol in early lines, not the ability to be read.
 */
export function trimStrokes(
  strokes: CanvasSnapshot['strokes'],
  limit: number = MAX_CANVAS_STROKE_POINTS,
): CanvasSnapshot['strokes'] {
  const kept: CanvasSnapshot['strokes'] = [];
  let points = 0;
  for (let i = strokes.length - 1; i >= 0; i -= 1) {
    const stroke = strokes[i];
    if (points + stroke.points.length > limit) break;
    points += stroke.points.length;
    kept.unshift(stroke);
  }
  return kept;
}

/**
 * Keep the newest events that fit, renumbered from zero.
 *
 * The renumbering is not tidiness. `validate_canvas_event_order` requires
 * `order_index` to be contiguous from zero and raises otherwise, so a trimmed
 * log that kept its original indices is a 422 on every turn once a student
 * passes 500 events — the failure would arrive suddenly, late in a long
 * question, and look nothing like a size problem.
 *
 * Order is what these carry; the absolute numbers are not referenced anywhere.
 */
export function trimEvents(
  events: CanvasEvent[],
  limit: number = MAX_CANVAS_EVENTS,
): CanvasEvent[] {
  const kept = events.length > limit ? events.slice(events.length - limit) : events;
  return kept.map((event, index) => (
    event.order_index === index ? event : { ...event, order_index: index }
  ));
}

/**
 * The canvas evidence for this turn, or undefined when there is none to send.
 *
 * Undefined rather than an empty state: an empty `canvas_state` still sets
 * `has_canvas_evidence`, which would send an OCR pass over a blank board and
 * invite the tutor to comment on working that does not exist.
 */
export function canvasEvidenceFor(
  snapshot: CanvasSnapshot | null | undefined,
  canvasEvents: CanvasEvent[],
): InteractionCanvasState | undefined {
  if (!snapshot) return undefined;
  const strokes = canvasStrokesForSubmission(trimStrokes(snapshot.strokes));
  if (strokes.length === 0) return undefined;
  return {
    snapshot_data_url: snapshot.snapshotDataUrl,
    strokes,
    captured_at: snapshot.capturedAt,
    canvas_events: canvasEventsForSubmission(trimEvents(canvasEvents)),
  };
}

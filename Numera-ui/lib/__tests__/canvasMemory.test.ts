/**
 * Ordered canvas memory — the log's own rules (§8, V1-Hybrid spec).
 *
 * These pin the two properties everything downstream depends on: the log is
 * append-only, and `order_index` is a true position in it. If either breaks,
 * the tutor's "resume at the first unresolved step" reads the wrong step and
 * the failure is silent — the canvas still looks correct on screen.
 */

import { describe, expect, it } from 'vitest';
import {
  appendCanvasEvent,
  clearCanvasEvents,
  itemBBox,
  supersedeCanvasEvents,
  tutorActionType,
  tutorElementBBox,
  tutorElementText,
  type CanvasEvent,
} from '@/lib/canvasMemory';
import type { DrawnItem, TutorElement } from '@/store/useNumeraStore';

const CTX = { turnId: 'TURN-1', questionId: 'Q-T01-004' };

const write = (events: CanvasEvent[], id: string) =>
  appendCanvasEvent(events, { actor: 'STUDENT', action_type: 'WRITE', target_object_id: id }, CTX);

describe('appendCanvasEvent', () => {
  it('numbers events by their position in the log', () => {
    let events: CanvasEvent[] = [];
    events = write(events, 'A');
    events = write(events, 'B');
    events = write(events, 'C');
    expect(events.map((e) => e.order_index)).toEqual([0, 1, 2]);
  });

  it('stamps the turn and question the action belongs to', () => {
    const [event] = write([], 'A');
    expect(event.turn_id).toBe('TURN-1');
    expect(event.question_id).toBe('Q-T01-004');
  });

  it('starts every event ACTIVE and leaves the optional fields null', () => {
    const [event] = write([], 'A');
    expect(event.active_state).toBe('ACTIVE');
    // semantic_tag is Sanya's to fill in — the frontend cannot know that a
    // stroke was the final rule, and a guess here would be worse than a gap.
    expect(event.semantic_tag).toBeNull();
    expect(event.math_text).toBeNull();
    expect(event.source_id).toBeNull();
  });

  it('does not mutate the array it was given', () => {
    const before = write([], 'A');
    write(before, 'B');
    expect(before).toHaveLength(1);
  });
});

describe('supersedeCanvasEvents', () => {
  it('retires only the events that acted on the given objects', () => {
    let events = write(write([], 'A'), 'B');
    events = supersedeCanvasEvents(events, ['A']);
    expect(events.map((e) => e.active_state)).toEqual(['SUPERSEDED', 'ACTIVE']);
  });

  it('keeps the retired event in the log rather than deleting it', () => {
    // The whole point: a student who wrote `n x 5`, rubbed it out and wrote
    // `n + 5` has shown a misconception and corrected it. Deleting the first
    // write would leave a log that says they got it right first time.
    const events = supersedeCanvasEvents(write([], 'A'), ['A']);
    expect(events).toHaveLength(1);
    expect(events[0].target_object_id).toBe('A');
  });

  it('leaves a CLEARED event alone', () => {
    // A later erase must not quietly downgrade it to SUPERSEDED, or the log
    // would stop showing that the board was wiped.
    const events = supersedeCanvasEvents(clearCanvasEvents(write([], 'A')), ['A']);
    expect(events[0].active_state).toBe('CLEARED');
  });

  it('is a no-op for an empty target list', () => {
    const before = write([], 'A');
    expect(supersedeCanvasEvents(before, [])).toBe(before);
  });
});

describe('clearCanvasEvents', () => {
  it('marks every ACTIVE event CLEARED and keeps them all', () => {
    const events = clearCanvasEvents(write(write([], 'A'), 'B'));
    expect(events).toHaveLength(2);
    expect(events.every((e) => e.active_state === 'CLEARED')).toBe(true);
  });

  it('does not resurrect a SUPERSEDED event', () => {
    const events = clearCanvasEvents(supersedeCanvasEvents(write([], 'A'), ['A']));
    expect(events[0].active_state).toBe('SUPERSEDED');
  });
});

describe('itemBBox', () => {
  const SIZE = { width: 800, height: 400 };

  it('normalises a stroke against the live canvas', () => {
    const item: DrawnItem = {
      id: 'S1', kind: 'stroke', tool: 'pen',
      points: [80, 40, 240, 120], color: '#000', size: 3,
    };
    expect(itemBBox(item, SIZE)).toEqual({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  });

  it('handles a rectangle dragged up and to the left', () => {
    // Konva keeps the negative w/h from a backwards drag. A raw x/w bbox would
    // put the box outside the canvas and send the tutor's view somewhere blank.
    const item: DrawnItem = { id: 'R1', kind: 'rect', x: 400, y: 200, w: -80, h: -40, color: '#000', size: 2 };
    expect(itemBBox(item, SIZE)).toEqual({ x: 0.4, y: 0.4, w: 0.1, h: 0.1 });
  });

  it('returns null before the canvas has been measured', () => {
    // A box computed against a zero size is a plausible-looking lie, and §8
    // uses bbox to decide what to bring into view.
    const item: DrawnItem = { id: 'S1', kind: 'stroke', tool: 'pen', points: [10, 10, 20, 20], color: '#000', size: 3 };
    expect(itemBBox(item, { width: 0, height: 0 })).toBeNull();
  });

  it('returns null for a stroke with no points', () => {
    const item: DrawnItem = { id: 'S1', kind: 'stroke', tool: 'pen', points: [], color: '#000', size: 3 };
    expect(itemBBox(item, SIZE)).toBeNull();
  });
});

describe('tutorElementBBox', () => {
  it('spans an arrow from end to end', () => {
    const el: TutorElement = { id: 'T1', kind: 'arrow', from: [0.6, 0.5], to: [0.2, 0.1] };
    const box = tutorElementBBox(el)!;
    expect(box.x).toBeCloseTo(0.2);
    expect(box.y).toBeCloseTo(0.1);
    expect(box.w).toBeCloseTo(0.4);
    expect(box.h).toBeCloseTo(0.4);
  });

  it('spans a freehand mark', () => {
    const el: TutorElement = { id: 'T1', kind: 'freehand', points: [0.1, 0.2, 0.5, 0.4] };
    expect(tutorElementBBox(el)).toEqual({ x: 0.1, y: 0.2, w: 0.4, h: 0.2 });
  });

  it('gives a zero-size box to a positioned label', () => {
    const el: TutorElement = { id: 'T1', kind: 'text', x: 0.3, y: 0.7, text: 'try this' };
    expect(tutorElementBBox(el)).toEqual({ x: 0.3, y: 0.7, w: 0, h: 0 });
  });

  it('returns null when the element carries no geometry at all', () => {
    expect(tutorElementBBox({ id: 'T1', kind: 'text', text: 'floating' })).toBeNull();
  });
});

describe('tutorActionType', () => {
  it.each([
    ['highlight', 'HIGHLIGHT'],
    ['ellipse', 'CIRCLE'],
    ['arrow', 'ARROW'],
    ['math', 'INSERT_MATH'],
    ['text', 'INSERT_MATH'],
  ] as const)('maps %s to %s', (kind, expected) => {
    expect(tutorActionType(kind)).toBe(expected);
  });

  it('does not force a shape with no §8 verb into a nearby one', () => {
    // A wrong verb is worse for the tutor than a vague one: told the tutor
    // "circled" when it drew a box, it would narrate something the student
    // cannot see on the board.
    expect(tutorActionType('rect')).toBe('ANNOTATE');
    expect(tutorActionType('line')).toBe('ANNOTATE');
  });
});

describe('tutorElementText', () => {
  it('prefers the TeX, because that is the maths', () => {
    expect(tutorElementText({ id: 'T1', kind: 'math', tex: 'n + 5', text: 'n plus 5' })).toBe('n + 5');
  });

  it('falls back to plain text and treats blank as nothing', () => {
    expect(tutorElementText({ id: 'T1', kind: 'text', text: 'look here' })).toBe('look here');
    expect(tutorElementText({ id: 'T1', kind: 'text', text: '   ' })).toBeNull();
  });
});

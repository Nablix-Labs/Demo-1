import { describe, expect, it } from 'vitest';
import {
  MAX_CANVAS_EVENTS,
  MAX_CANVAS_STROKE_POINTS,
  canvasEvidenceFor,
  trimEvents,
  trimStrokes,
} from '@/lib/canvasEvidence';
import type { CanvasEvent } from '@/lib/canvasMemory';
import type { CanvasSnapshot } from '@/store/useNumeraStore';

const PNG = 'data:image/png;base64,c25hcHNob3Q=';

function stroke(id: string, points: number): CanvasSnapshot['strokes'][number] {
  return {
    stroke_id: id,
    tool: 'pen',
    width: 2,
    points: Array.from({ length: points }, (_, i) => ({ x: 0.1, y: i / (points * 2) })),
  };
}

function event(order: number): CanvasEvent {
  return {
    order_index: order,
    turn_id: 'TURN-1',
    question_id: 'Q-1',
    actor: 'STUDENT',
    action_type: 'WRITE',
    content: null,
    math_text: null,
    target_object_id: null,
    bbox: null,
    semantic_tag: null,
    source_id: null,
    active_state: 'ACTIVE',
  };
}

function snapshot(strokes: CanvasSnapshot['strokes']): CanvasSnapshot {
  return { snapshotDataUrl: PNG, strokes, capturedAt: '2026-08-24T10:00:00Z' };
}

describe('trimStrokes', () => {
  it('keeps everything when the board is within budget', () => {
    const strokes = [stroke('a', 10), stroke('b', 10)];
    expect(trimStrokes(strokes)).toEqual(strokes);
  });

  it('drops the oldest strokes, because the turn is about the newest work', () => {
    const strokes = [stroke('old', 6), stroke('mid', 6), stroke('new', 6)];
    expect(trimStrokes(strokes, 12).map((s) => s.stroke_id)).toEqual(['mid', 'new']);
  });

  it('never emits a half-sent stroke', () => {
    // A truncated stroke would put a spatial token on geometry that stops
    // mid-symbol — worse evidence than omitting the stroke entirely.
    const kept = trimStrokes([stroke('a', 8), stroke('b', 8)], 10);
    expect(kept).toHaveLength(1);
    expect(kept[0].points).toHaveLength(8);
  });

  it('stays under the limit the server enforces', () => {
    const strokes = Array.from({ length: 40 }, (_, i) => stroke(`s${i}`, 500));
    const total = trimStrokes(strokes).reduce((n, s) => n + s.points.length, 0);
    expect(total).toBeLessThanOrEqual(MAX_CANVAS_STROKE_POINTS);
  });
});

describe('trimEvents', () => {
  it('leaves a short log alone', () => {
    const events = [event(0), event(1)];
    expect(trimEvents(events)).toEqual(events);
  });

  it('renumbers from zero after trimming', () => {
    // validate_canvas_event_order requires contiguity from zero and raises
    // otherwise, so keeping the original indices would 422 the whole turn.
    const events = Array.from({ length: 6 }, (_, i) => event(i));
    expect(trimEvents(events, 3).map((e) => e.order_index)).toEqual([0, 1, 2]);
  });

  it('keeps the most recent events', () => {
    const events = Array.from({ length: 5 }, (_, i) => ({ ...event(i), turn_id: `T${i}` }));
    expect(trimEvents(events, 2).map((e) => e.turn_id)).toEqual(['T3', 'T4']);
  });

  it('stays under the limit the server enforces', () => {
    const events = Array.from({ length: MAX_CANVAS_EVENTS + 120 }, (_, i) => event(i));
    const kept = trimEvents(events);
    expect(kept).toHaveLength(MAX_CANVAS_EVENTS);
    expect(kept[0].order_index).toBe(0);
  });
});

describe('canvasEvidenceFor', () => {
  it('sends nothing when there is no snapshot', () => {
    expect(canvasEvidenceFor(null, [])).toBeUndefined();
  });

  it('sends nothing for a blank board', () => {
    // An empty canvas_state still sets has_canvas_evidence, which would run OCR
    // over nothing and invite the tutor to comment on absent working.
    expect(canvasEvidenceFor(snapshot([]), [event(0)])).toBeUndefined();
  });

  it('carries the snapshot, strokes and ordered memory together', () => {
    const state = canvasEvidenceFor(snapshot([stroke('a', 3)]), [event(0), event(1)]);
    expect(state?.snapshot_data_url).toBe(PNG);
    expect(state?.strokes).toHaveLength(1);
    expect(state?.canvas_events).toHaveLength(2);
    expect(state?.captured_at).toBe('2026-08-24T10:00:00Z');
  });

  it('drops off-stage points rather than the whole submission', () => {
    const offStage = {
      stroke_id: 'x',
      tool: 'pen' as const,
      width: 2,
      points: [{ x: 0.2, y: 0.2 }, { x: 4.5, y: 0.3 }],
    };
    const state = canvasEvidenceFor(snapshot([offStage]), []);
    expect(state?.strokes[0].points).toEqual([{ x: 0.2, y: 0.2 }]);
  });

  it('omits itself when every point was off-stage', () => {
    const offStage = {
      stroke_id: 'x',
      tool: 'pen' as const,
      width: 2,
      points: [{ x: 9, y: 9 }],
    };
    expect(canvasEvidenceFor(snapshot([offStage]), [])).toBeUndefined();
  });
});

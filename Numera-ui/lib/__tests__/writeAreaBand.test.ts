/**
 * The yellow band the student writes their answer in.
 *
 * Manjusha, row 56 / 26 Aug: "Phase 2 yellow writing area to write the answer
 * is not shown."
 *
 * There are two spellings of the same request. The backend's older one sends
 * three hand-positioned ELEMENTS — `:write-highlight`, `:write-prompt`,
 * `:write-arrow` — which relocateWriteRequest moves off the right-hand column
 * onto the client's own geometry. The semantic one sends a single action with
 * `target_kind: 'WRITE_AREA'`, and it used to draw nothing: it raised the rose
 * "write it down" note and stopped. So the migration kept the ASK and dropped
 * the PLACE, and the yellow area disappeared from Phase 2.
 *
 * The band is drawn now. What must never be drawn is anything the action
 * CARRIES: a WRITE_AREA action may arrive with `text`, and that text can be the
 * rule itself, which is the one thing the student is being asked to produce.
 */

import { describe, it, expect } from 'vitest';
import { actionMarks, WRITE_AREA } from '@/lib/tutorCanvasActions';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

const WRITE_TARGET = { kind: 'write-area' } as Parameters<typeof actionMarks>[1];

const writeAction = (over: Partial<TutorCanvasAction> = {}) => ({
  action_id: 'A1',
  type: 'HIGHLIGHT',
  target_kind: 'WRITE_AREA',
  ...over,
}) as TutorCanvasAction;

const marks = (over?: Partial<TutorCanvasAction>) => actionMarks(writeAction(over), WRITE_TARGET);

describe('the write-area band', () => {
  it('draws the band and an arrow into it', () => {
    const kinds = marks().map((m) => m.kind);
    expect(kinds).toContain('highlight');
    expect(kinds).toContain('arrow');
  });

  it('sits on the same geometry as the relocated backend block', () => {
    const band = marks().find((m) => m.kind === 'highlight')!;
    const xs = band.points!.filter((_, i) => i % 2 === 0);
    const ys = band.points!.filter((_, i) => i % 2 === 1);
    expect(Math.min(...xs)).toBe(WRITE_AREA.x);
    expect(Math.max(...xs)).toBe(WRITE_AREA.x + WRITE_AREA.w);
    expect(Math.min(...ys)).toBe(WRITE_AREA.y);
    expect(Math.max(...ys)).toBe(WRITE_AREA.y + WRITE_AREA.h);
  });

  it('closes the box, so it reads as a region and not an abandoned mark', () => {
    const band = marks().find((m) => m.kind === 'highlight')!;
    const pts = band.points!;
    expect([pts[0], pts[1]]).toEqual([pts[pts.length - 2], pts[pts.length - 1]]);
  });

  it('points the arrow down into the band, never past it', () => {
    const arrow = marks().find((m) => m.kind === 'arrow')!;
    expect(arrow.from![1]).toBeLessThan(arrow.to![1]);
    expect(arrow.to![1]).toBe(WRITE_AREA.y);
  });

  it('stays out of the right-hand column, where the cards live', () => {
    for (const mark of marks()) {
      const xs = [
        ...(mark.points ?? []).filter((_, i) => i % 2 === 0),
        ...(mark.from ? [mark.from[0]] : []),
        ...(mark.to ? [mark.to[0]] : []),
      ];
      for (const x of xs) expect(x, `${mark.id} at x=${x}`).toBeLessThan(0.5);
    }
  });

  it('NEVER writes the action’s text — that text can be the answer', () => {
    const drawn = marks({ text: 'n + 4' });
    expect(drawn.every((m) => m.text === undefined)).toBe(true);
    expect(JSON.stringify(drawn)).not.toContain('n + 4');
  });
});

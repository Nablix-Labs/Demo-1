/**
 * The write area draws nothing (19 Sep).
 *
 * It used to draw a yellow band and an arrow (row 56). The team has since asked
 * for the box to go — "it's just a placeholder" — so a WRITE_AREA action now
 * leaves the canvas alone. What must STILL never be drawn is anything the
 * action carries: its `text` can be the rule the student is being asked for.
 */

import { describe, it, expect } from 'vitest';
import { actionMarks } from '@/lib/tutorCanvasActions';
import type { TutorCanvasAction } from '@/store/useNumeraStore';

const WRITE_TARGET = { kind: 'write-area' } as Parameters<typeof actionMarks>[1];

const writeAction = (over: Partial<TutorCanvasAction> = {}) => ({
  action_id: 'A1',
  type: 'HIGHLIGHT',
  target_kind: 'WRITE_AREA',
  ...over,
}) as TutorCanvasAction;

describe('the write area', () => {
  it('draws no band, prompt or arrow', () => {
    expect(actionMarks(writeAction(), WRITE_TARGET)).toEqual([]);
  });

  it('NEVER writes the action’s text — that text can be the answer', () => {
    expect(actionMarks(writeAction({ text: 'n + 4' }), WRITE_TARGET)).toEqual([]);
  });
});

/**
 * The Check button sends the strokes, not just the picture.
 *
 * Sanya, 13 Aug 2026 (TUTOR WRITING FUNCTIONALITY): the frontend's remaining
 * work for tutor writing is that "Normal Check currently calls submitCanvas(...)
 * without strokes". The image says WHAT was written; the strokes are what let
 * `canvas_service` build spatial tokens and say WHERE — and without tokens the
 * tutor can identify a wrong answer but can only mark the whole line, never the
 * specific handwritten symbol.
 *
 * This went unnoticed for weeks because the field existed on both sides and
 * every submission validated cleanly without it. So the test asserts on the
 * REQUEST BODY: a missing `strokes` is not an error anywhere else in the stack.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
vi.mock('axios', () => ({
  default: {
    create: () => ({
      post: (...args: unknown[]) => post(...args),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    }),
  },
}));

import { submitCanvas } from '@/lib/api';
import type { CanvasStrokeSnapshot } from '@/store/useNumeraStore';

const PNG = 'data:image/png;base64,aGVsbG8=';

const STROKES: CanvasStrokeSnapshot[] = [
  { stroke_id: 'S1', tool: 'pen', points: [{ x: 0.1, y: 0.2 }, { x: 0.3, y: 0.2 }], width: 2 },
  { stroke_id: 'S2', tool: 'pencil', points: [{ x: 0.5, y: 0.6 }], width: 1.5 },
];

describe('submitCanvas', () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = '/api';
    post.mockReset();
    post.mockResolvedValue({ data: { status: 'processed' } });
  });

  afterEach(() => vi.clearAllMocks());

  it('sends the strokes in the request body', async () => {
    await submitCanvas('SESSION001', PNG, 'STANDALONE_ATTEMPT', 'TURN-1', STROKES, 'ST015');
    const [url, body] = post.mock.calls[0];
    expect(url).toBe('/canvas/submit');
    expect(body.strokes).toEqual(STROKES);
  });

  it('sends the stroke shape the backend validates', async () => {
    // Mirrors CanvasStroke in nablix-backend/app/models/canvas.py:94 —
    // stroke_id, tool, points[{x,y}], width. A shape drift here is a 422.
    await submitCanvas('SESSION001', PNG, 'STANDALONE_ATTEMPT', 'TURN-1', STROKES, 'ST015');
    const stroke = post.mock.calls[0][1].strokes[0];
    expect(Object.keys(stroke).sort()).toEqual(['points', 'stroke_id', 'tool', 'width']);
    expect(Object.keys(stroke.points[0]).sort()).toEqual(['x', 'y']);
  });

  it('still sends an empty list when the board has no strokes', async () => {
    // An empty array is a real answer — "nothing was drawn" — and is not the
    // same as omitting the field, which is what the bug did.
    await submitCanvas('SESSION001', PNG, 'STANDALONE_ATTEMPT', 'TURN-1', [], 'ST015');
    expect(post.mock.calls[0][1].strokes).toEqual([]);
  });

  it('keeps sending the fields it already sent', async () => {
    await submitCanvas('SESSION001', PNG, 'STANDALONE_ATTEMPT', 'TURN-9', STROKES, 'ST015');
    expect(post.mock.calls[0][1]).toMatchObject({
      session_id: 'SESSION001',
      student_id: 'ST015',
      turn_id: 'TURN-9',
      snapshot_data_url: PNG,
      submission_role: 'STANDALONE_ATTEMPT',
    });
  });
});

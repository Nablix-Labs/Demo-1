/**
 * The student's working has to reach the tutor on a voice turn.
 *
 * The gap: `sendCanvasSubmission` existed, was returned from useWebSocket, and
 * was called by nothing. The canvas reached the backend by exactly one route —
 * tapping "Check", over REST — so a student who wrote `n + 5` and then SAID
 * "I fully written that in the Canvas" had submitted nothing, and the tutor
 * re-asked the question they had just answered (Manjusha, 22 Aug).
 *
 * These cover the decision rules the frame depends on rather than the socket
 * plumbing: send only when there is working to send, and only once per turn.
 * A PNG export per frame is not free on a tablet, and a blank canvas is worth
 * nothing to the tutor or the OCR behind it.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

/** Mirrors the guard order in useWebSocket's sendCanvasForTurn. */
function wouldSend(sentForTurn: string | null): { send: boolean; turnId: string | null } {
  const s = useNumeraStore.getState();
  const turnId = s.currentTurnId;
  if (!turnId || sentForTurn === turnId) return { send: false, turnId };
  if (s.items.length === 0) return { send: false, turnId };
  const snapshot = s.canvasExporter?.();
  if (!snapshot?.snapshotDataUrl) return { send: false, turnId };
  return { send: true, turnId };
}

const snapshot = () => ({
  snapshotDataUrl: 'data:image/png;base64,AAAA',
  strokes: [],
  capturedAt: '2026-08-24T00:00:00.000Z',
});

beforeEach(() => {
  useNumeraStore.setState({
    currentTurnId: 'TURN-1',
    items: [{ id: 'ITEM-1', kind: 'stroke', points: [0.1, 0.1] }] as never,
    canvasExporter: snapshot,
  });
});

describe('sending the canvas on a voice turn', () => {
  it('sends when the student has drawn', () => {
    expect(wouldSend(null).send).toBe(true);
  });

  it('sends once per turn, not once per frame', () => {
    // student_speaking and transcript_final both call it; the second is a
    // fallback for when StartOfTurn never arrived, not a second submission.
    const first = wouldSend(null);
    expect(first.send).toBe(true);
    expect(wouldSend(first.turnId).send).toBe(false);
  });

  it('sends again on the next turn', () => {
    useNumeraStore.setState({ currentTurnId: 'TURN-2' });
    expect(wouldSend('TURN-1').send).toBe(true);
  });

  it('does not send a blank canvas', () => {
    useNumeraStore.setState({ items: [] });
    expect(wouldSend(null).send).toBe(false);
  });

  it('does not send before a turn exists', () => {
    useNumeraStore.setState({ currentTurnId: null });
    expect(wouldSend(null).send).toBe(false);
  });

  it('degrades when the canvas cannot be exported', () => {
    useNumeraStore.setState({ canvasExporter: () => null });
    expect(wouldSend(null).send).toBe(false);
  });
});

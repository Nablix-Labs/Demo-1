/**
 * TEACH_BACK adapter — the mock conversation drives the Teacher Mode screen
 * until the real backend contract lands. These lock in the two things the UI
 * depends on: the opening is an invite, and a full run reaches GUIDED_PRACTICE
 * (and only there does next_phase become non-null).
 */

import { describe, it, expect } from 'vitest';
import { submitTeachTurn, teachOpening, type TeachTurnRequest } from '@/lib/teachback/teachApi';

function req(turn_number: number): TeachTurnRequest {
  return {
    session_id: null,
    student_id: 'ST001',
    current_phase: 'TEACH_BACK',
    input_source: 'TEXT',
    text_input: 'explanation',
    turn_number,
  };
}

describe('teachApi mock', () => {
  it('opens with an invite and no phase change', () => {
    const opening = teachOpening();
    expect(opening.action).toBe('INVITE_EXPLANATION');
    expect(opening.next_phase).toBeNull();
  });

  it('stays in TEACH_BACK until the final turn', async () => {
    for (const n of [1, 2, 3, 4]) {
      const res = await submitTeachTurn(req(n));
      expect(res.next_phase).toBeNull();
    }
  });

  it('surfaces a controlled misconception mid-conversation', async () => {
    const res = await submitTeachTurn(req(3));
    expect(res.action).toBe('PRESENT_MISCONCEPTION');
  });

  it('routes to GUIDED_PRACTICE once the concept is taught', async () => {
    const res = await submitTeachTurn(req(5));
    expect(res.action).toBe('MOVE_TO_GUIDED_PRACTICE');
    expect(res.next_phase).toBe('GUIDED_PRACTICE');
    expect(res.status).toBe('MASTERED');
  });
});

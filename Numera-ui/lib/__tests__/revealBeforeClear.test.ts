import { describe, expect, it } from 'vitest';
import { revealDecision, REVEAL_MS } from '@/lib/revealBeforeClear';

describe('holding the board before a phase change', () => {
  it('holds when a completing turn carries marks', () => {
    expect(revealDecision(2, 'Q1', 'Q2')).toEqual({ reveal: true, holdMs: REVEAL_MS });
  });

  it('does not hold when the turn carries no marks — a pause with nothing in it', () => {
    expect(revealDecision(0, 'Q1', 'Q2')).toEqual({ reveal: false, holdMs: 0 });
  });

  it('does not hold when the question is not changing', () => {
    // Nothing is about to be cleared, so there is nothing to outrun.
    expect(revealDecision(3, 'Q1', 'Q1')).toEqual({ reveal: false, holdMs: 0 });
  });

  it('does not hold on the first question of a session', () => {
    // No previous question means no board to preserve.
    expect(revealDecision(3, null, 'Q1').reveal).toBe(false);
  });

  it('does not hold when the reply names no next question', () => {
    // A null question id does not mean "move on" — applyBackendPhase decides
    // what that means per phase, and delaying it here would guess.
    expect(revealDecision(3, 'Q1', null).reveal).toBe(false);
    expect(revealDecision(3, 'Q1', undefined).reveal).toBe(false);
    expect(revealDecision(3, 'Q1', '').reveal).toBe(false);
  });
});

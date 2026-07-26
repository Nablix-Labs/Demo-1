import { describe, it, expect } from 'vitest';
import { isBareEquation } from '@/lib/questionText';

describe('isBareEquation', () => {
  it('treats a bare equation as one, so the "Solve for x:" lead-in is supplied', () => {
    expect(isBareEquation('x + 4 = 9')).toBe(true);
    expect(isBareEquation('2x + 5 = 13')).toBe(true);
    expect(isBareEquation('4x − 3 = 17')).toBe(true); // unicode minus, as in demo content
    expect(isBareEquation('  x = 5  ')).toBe(true);
    expect(isBareEquation('3y ≥ 12')).toBe(true);
  });

  it('treats a word problem as prose, shown verbatim and allowed to wrap', () => {
    expect(
      isBareEquation(
        'a box starts with four fixed counters and receives 5 additional counters, then how would you write it as an equation'
      )
    ).toBe(false);
    expect(isBareEquation('What is the value of x when x + 4 = 9?')).toBe(false);
  });

  it('does not re-add a lead-in the backend already wrote', () => {
    // The old code stripped this prefix and the header re-added it; a question
    // carrying its own instruction must now pass through untouched.
    expect(isBareEquation('Solve for x: x + 4 = 9')).toBe(false);
  });

  it('needs a relation — a bare expression is not an equation to solve', () => {
    expect(isBareEquation('x + 4')).toBe(false);
    expect(isBareEquation('')).toBe(false);
    expect(isBareEquation('   ')).toBe(false);
  });
});

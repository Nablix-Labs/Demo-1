/**
 * The wording of the option a student picked.
 *
 * Revised integration handoff, frontend §1: send the selected option ID AND the
 * exact option text. Acceptance test 9 is what it is for — "wrong option
 * receives a focused explanation request, not generic fallback wording". Given
 * only "B" the tutor can say no more than that B is wrong; given "n + 4" it can
 * address the belief the student actually holds.
 */

import { describe, expect, it } from 'vitest';
import { selectedOptionText } from '@/lib/selectedOption';

const OPTIONS = [
  { option_id: 'A', text: 'n + 3' },
  { option_id: 'B', text: 'n + 4' },
  { option_id: 'C', text: '4n' },
];

describe('the selected option text', () => {
  it('is the authored wording of the chosen option', () => {
    expect(selectedOptionText(OPTIONS, 'B')).toBe('n + 4');
  });

  it('is null when nothing is selected', () => {
    expect(selectedOptionText(OPTIONS, null)).toBeNull();
  });

  it('is null when the selection is not in the list', () => {
    // A selection left over from a question whose options have moved on. The id
    // stays authoritative and travels regardless; sending text from the wrong
    // question would put words in the student's mouth.
    expect(selectedOptionText(OPTIONS, 'Z')).toBeNull();
  });

  it('never substitutes the id for missing text', () => {
    // An id dressed as text is worse than an absent field: it reads as the
    // student having literally said "B".
    expect(selectedOptionText([{ option_id: 'B', text: '   ' }], 'B')).toBeNull();
  });

  it('is null when the question carries no options', () => {
    expect(selectedOptionText([], 'B')).toBeNull();
    expect(selectedOptionText(null, 'B')).toBeNull();
  });
});

/**
 * Key Notes at a Glance — revision-card content.
 *
 * Generated after a session from the topics covered and the student's own
 * mistakes. Short, practical, scannable — a smart revision card, not a
 * textbook. In production the backend personalises these; here they are mocked
 * for the linear-equations session, with `flagged` marking cards that target a
 * mistake the student actually made (e.g. expanding brackets).
 */

export interface KeyNote {
  id: string;
  topic: string;
  meaning: string;        // simple meaning
  howToStart: string;
  steps: string[];        // main steps to follow
  beCareful: string[];    // common mistakes / warning points
  tips: string[];         // tips & tricks
  formula: string;        // formula or rule
  example: string[];      // one short worked example, line by line
  examTip: string;
  flagged?: boolean;      // surfaced because of a mistake this session
}

export const KEY_NOTES: KeyNote[] = [
  {
    id: 'linear-equations',
    topic: 'Solving Linear Equations',
    meaning: 'An equation where the unknown has a power of 1, like 2x + 3 = 9. The goal is to find the value of x.',
    howToStart: 'Look at what is happening to the unknown — what is added, subtracted, multiplied or divided with x — then undo it step by step.',
    steps: [
      'Keep the equation balanced.',
      'Move numbers carefully from one side to the other.',
      'When a number crosses the equal sign, its sign changes.',
      'Simplify both sides.',
      'Find the value of the unknown.',
      'Substitute the answer back to check it.',
    ],
    beCareful: [
      'Sign changes when moving terms',
      'Skipping steps too quickly',
      'Forgetting to check the final answer',
    ],
    tips: [
      'Always ask: “Did I do the opposite operation?”',
      'If +3 is added, subtract 3. If x is times 2, divide by 2.',
    ],
    formula: 'Do the same operation on both sides of the equation.',
    example: ['2x + 3 = 9', '2x = 9 − 3', '2x = 6', 'x = 3'],
    examTip: 'Don’t jump straight to the answer — write the important steps clearly so small mistakes show up.',
  },
  {
    id: 'sign-change',
    topic: 'Sign Change Rule',
    meaning: 'When a number or term moves across the equal sign, its operation flips to the opposite.',
    howToStart: 'Before writing the next line, pause and check which way the term is moving.',
    steps: [
      '+ becomes −',
      '− becomes +',
      '× becomes ÷',
      '÷ becomes ×',
    ],
    beCareful: [
      'Moving a number without changing its sign',
    ],
    tips: [
      'Pause and ask: “Did the sign change correctly?”',
    ],
    formula: 'Cross the equal sign → flip the operation.',
    example: ['x + 5 = 12', 'x = 12 − 5', 'x = 7'],
    examTip: 'A flipped sign is the most common slip — double-check every move across the =.',
  },
  {
    id: 'expanding-brackets',
    topic: 'Expanding Brackets',
    meaning: 'Multiply the number outside the bracket by every term inside it before you solve.',
    howToStart: 'Multiply the outside number into each term inside — don’t drop the second term.',
    steps: [
      'Multiply the outside value by the first term.',
      'Multiply the outside value by the second term.',
      'Then solve the equation as normal.',
    ],
    beCareful: [
      'Only multiplying the first term (e.g. 3(x − 2) → 3x − 2)',
      'Losing the sign on the second term',
    ],
    tips: [
      'Draw two arrows from the number to each term so you don’t forget one.',
    ],
    formula: 'a(b + c) = ab + ac',
    example: ['3(x − 2) = 9', '3x − 6 = 9', '3x = 15', 'x = 5'],
    examTip: 'Expand fully first, then solve — never solve through a bracket.',
    flagged: true,
  },
];

/** Build the spoken version of a card for the Read Out Loud button. */
export function noteToSpeech(n: KeyNote): string {
  return [
    `${n.topic}.`,
    n.meaning,
    `How to start: ${n.howToStart}`,
    `Main steps: ${n.steps.join('. ')}.`,
    `Be careful with: ${n.beCareful.join('. ')}.`,
    `Tip: ${n.tips.join('. ')}.`,
    `The rule: ${n.formula}.`,
    `Exam tip: ${n.examTip}`,
  ].join(' ');
}

/**
 * Files — worksheets, saved canvas working and notes from past sessions.
 *
 * Mock content, like the rest of the pre-backend screens: a real file store
 * would return these from the session record. The shape is what matters — each
 * file carries its own sheets so it can be opened and read rather than only
 * listed, and `kind` drives both the cover colour and how a sheet is set.
 */

export type FileKind = 'worksheet' | 'canvas' | 'notes';

export interface FileSheet {
  /** Small heading at the top of the sheet, if it has one. */
  heading?: string;
  lines: string[];
}

export interface FileItem {
  id: string;
  name: string;
  kind: FileKind;
  meta: string;
  sheets: FileSheet[];
}

export const FILES: FileItem[] = [
  {
    id: 'linear-worksheet',
    name: 'Linear equations — worksheet',
    kind: 'worksheet',
    meta: 'PDF · 240 KB · 12 Jun',
    sheets: [
      {
        heading: 'Solve for x',
        lines: ['1.  x + 7 = 12', '2.  3x = 21', '3.  2x + 5 = 13', '4.  5x − 4 = 26', '5.  4x + 3 = 3x + 9'],
      },
      {
        heading: 'Show your working',
        lines: ['6.  2(x + 3) = 14', '7.  3(x − 1) = 2x + 4', '8.  x/2 + 6 = 10', '9.  7 − x = 2', '10. 4(2x − 1) = 20'],
      },
      {
        heading: 'Word problems',
        lines: [
          'A number is multiplied by 3, then 5 is added.',
          'The result is 26. What is the number?',
          '',
          'Two consecutive numbers add to 37.',
          'What are they?',
        ],
      },
    ],
  },
  {
    id: 'session-3-working',
    name: 'Session 3 — my working',
    kind: 'canvas',
    meta: 'PNG · 88 KB · 13 Jun',
    sheets: [
      {
        heading: 'What I wrote',
        lines: ['2x + 3 = 9', '2x = 9 − 3', '2x = 6', 'x = 3', '', '✓ checked by substituting back'],
      },
      {
        heading: "Numi's note",
        lines: [
          'Good — you undid the +3 before the ×2.',
          'That order is what keeps the equation balanced.',
        ],
      },
    ],
  },
  {
    id: 'fractions-practice',
    name: 'Fractions practice',
    kind: 'worksheet',
    meta: 'PDF · 196 KB · 10 Jun',
    sheets: [
      {
        heading: 'Simplify',
        lines: ['1.  6/8', '2.  9/12', '3.  15/25', '4.  14/21', '5.  30/45'],
      },
      {
        heading: 'Add and subtract',
        lines: ['6.  1/3 + 1/6', '7.  3/4 − 1/8', '8.  2/5 + 3/10', '9.  5/6 − 1/3', '10. 7/8 + 1/4'],
      },
    ],
  },
  {
    id: 'solving-for-x-notes',
    name: 'Solving for x — notes',
    kind: 'notes',
    meta: 'Note · 9 Jun',
    sheets: [
      {
        heading: 'Remember',
        lines: [
          'Whatever you do to one side,',
          'do to the other.',
          '',
          'Undo in reverse order:',
          'add/subtract first, then multiply/divide.',
        ],
      },
      {
        heading: 'My mistake today',
        lines: [
          'I moved the 3 across but kept it +.',
          'Crossing the = flips the sign.',
          '',
          '2x + 3 = 9  →  2x = 9 − 3',
        ],
      },
    ],
  },
  {
    id: 'session-2-working',
    name: 'Session 2 — my working',
    kind: 'canvas',
    meta: 'PNG · 102 KB · 9 Jun',
    sheets: [
      {
        heading: 'What I wrote',
        lines: ['x + 5 = 12', 'x = 12 − 5', 'x = 7'],
      },
    ],
  },
  {
    id: 'angles-cheat-sheet',
    name: 'Angles cheat sheet',
    kind: 'notes',
    meta: 'Note · 6 Jun',
    sheets: [
      {
        heading: 'Straight and round',
        lines: [
          'Angles on a straight line add to 180°.',
          'Angles around a point add to 360°.',
          'Vertically opposite angles are equal.',
        ],
      },
      {
        heading: 'In shapes',
        lines: [
          'Triangle: angles add to 180°.',
          'Quadrilateral: angles add to 360°.',
          '',
          'Equilateral triangle: every angle is 60°.',
        ],
      },
    ],
  },
];

/** Cover colour and the ink that stays legible on it. */
export const KIND = {
  worksheet: { label: 'Worksheet', color: '#3E5FD4', textColor: '#FFFFFF' },
  canvas: { label: 'Canvas', color: '#0E93B4', textColor: '#FFFFFF' },
  notes: { label: 'Notes', color: '#F0C14B', textColor: '#4A3208' },
} as const;

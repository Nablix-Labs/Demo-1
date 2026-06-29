/**
 * Demo content — per-topic mock content so the whole journey reads coherently
 * for whichever topic the student is placed at. One source for the guided
 * lesson, independent practice and the review worksheets.
 *
 * Frontend-only demo data. In production all of this is backend-served.
 * Every problem is framed as "solve for x" so the shared lesson heading and
 * bar-model stay consistent across subjects.
 */

export interface DemoLine {
  text: string;
  mark?: 'tick' | 'cross';
  circle?: boolean;
  label?: string;
}

export interface DemoWorksheet {
  question: string;
  correct: boolean;
  student: DemoLine[];
  corrections?: string[];
  voice: string;
}

export interface DemoTurn {
  role: 'ai' | 'student';
  text: string;
}

export interface TopicDemo {
  label: string; // subject label, e.g. "Linear equations"
  questionNumber: number; // shown in the lesson question badge
  lessonQuestion: string; // the equation in the lesson heading
  showBarModel: boolean; // the bar-model visual is algebra-only
  transcript: DemoTurn[]; // opening lesson exchange
  practiceQuestion: string;
  practiceHints: string[];
  reviewSummary: string;
  worksheets: DemoWorksheet[];
}

const ALGEBRA: TopicDemo = {
  label: 'Linear equations',
  questionNumber: 3,
  lessonQuestion: '2x + 5 = 13',
  showBarModel: true,
  transcript: [
    { role: 'ai', text: 'What do we do first to get the x term on its own?' },
    { role: 'student', text: 'Subtract 5 from both sides?' },
    { role: 'ai', text: 'Exactly. So what does the left side become?' },
  ],
  practiceQuestion: '4x − 3 = 17',
  practiceHints: [
    'Start by getting the x term on its own — what undoes the − 3?',
    'Add 3 to both sides first. What does the left side become?',
    'Now you have 4x = 20. How do you get x by itself?',
  ],
  reviewSummary:
    'You completed five questions. Three were correct and two need improvement. You understand the method well — just be more careful when expanding brackets before solving.',
  worksheets: [
    {
      question: '2x + 5 = 13',
      correct: true,
      student: [
        { text: '2x + 5 = 13', mark: 'tick' },
        { text: '2x = 13 − 5', mark: 'tick' },
        { text: '2x = 8', mark: 'tick' },
        { text: 'x = 4', mark: 'tick' },
      ],
      voice:
        'Clean working here. You subtracted five from both sides, then divided by two. The answer x equals four is correct.',
    },
    {
      question: '3(x − 2) = 9',
      correct: false,
      student: [
        { text: '3(x − 2) = 9', mark: 'tick' },
        { text: '3x − 2 = 9', mark: 'cross', circle: true, label: 'expand error' },
        { text: '3x = 11', mark: 'cross' },
        { text: 'x = 11/3', mark: 'cross' },
      ],
      corrections: ['3x − 6 = 9', '3x = 15', 'x = 5'],
      voice:
        'Your method is right, but look at this step. When you expand three times the bracket, the minus two becomes minus six, not minus two. So it should be three x minus six. That gives x equals five.',
    },
    {
      question: '4x − 3 = 17',
      correct: true,
      student: [
        { text: '4x − 3 = 17', mark: 'tick' },
        { text: '4x = 17 + 3', mark: 'tick' },
        { text: '4x = 20', mark: 'tick' },
        { text: 'x = 5', mark: 'tick' },
      ],
      voice:
        'Good work. You added three to both sides first, then divided by four. x equals five is correct.',
    },
    {
      question: '5(x + 1) = 20',
      correct: false,
      student: [
        { text: '5(x + 1) = 20', mark: 'tick' },
        { text: '5x + 1 = 20', mark: 'cross', circle: true, label: 'expand' },
        { text: '5x = 19', mark: 'cross' },
        { text: 'x = 19/5', mark: 'cross' },
      ],
      corrections: ['5x + 5 = 20', '5x = 15', 'x = 3'],
      voice:
        'Here you forgot to expand the bracket. Five times x plus one is five x plus five, not five x plus one. Once you fix that, x equals three.',
    },
    {
      question: '2x − 7 = 9',
      correct: true,
      student: [
        { text: '2x − 7 = 9', mark: 'tick' },
        { text: '2x = 9 + 7', mark: 'tick' },
        { text: '2x = 16', mark: 'tick' },
        { text: 'x = 8', mark: 'tick' },
      ],
      voice:
        'Solved confidently. You moved the seven across correctly and divided by two. x equals eight is right.',
    },
  ],
};

const NUMBER: TopicDemo = {
  label: 'Fractions',
  questionNumber: 2,
  lessonQuestion: 'x/2 + 1/4 = 3/4',
  showBarModel: false,
  transcript: [
    { role: 'ai', text: 'To get x on its own, what do we do with the one-quarter first?' },
    { role: 'student', text: 'Subtract a quarter from both sides?' },
    { role: 'ai', text: 'Exactly. So what does the right side become?' },
  ],
  practiceQuestion: 'x/3 − 1/6 = 1/2',
  practiceHints: [
    'Move the number term across first — what undoes the − 1/6?',
    'Add 1/6 to both sides. Make the denominators match before you add.',
    'Now you have x/3 = 2/3. How do you get x on its own?',
  ],
  reviewSummary:
    'You completed five questions. Three were correct and two need improvement. Your method is solid — just line up the denominators before adding or subtracting fractions.',
  worksheets: [
    {
      question: 'x/2 + 1/4 = 3/4',
      correct: true,
      student: [
        { text: 'x/2 + 1/4 = 3/4', mark: 'tick' },
        { text: 'x/2 = 3/4 − 1/4', mark: 'tick' },
        { text: 'x/2 = 1/2', mark: 'tick' },
        { text: 'x = 1', mark: 'tick' },
      ],
      voice:
        'Clean working. You subtracted a quarter from both sides, then doubled to undo the half. x equals one is correct.',
    },
    {
      question: 'x/3 − 1/6 = 1/2',
      correct: false,
      student: [
        { text: 'x/3 − 1/6 = 1/2', mark: 'tick' },
        { text: 'x/3 = 1/2 + 1/6', mark: 'tick' },
        { text: 'x/3 = 2/8', mark: 'cross', circle: true, label: 'denominators' },
        { text: 'x = 6/8', mark: 'cross' },
      ],
      corrections: ['x/3 = 3/6 + 1/6', 'x/3 = 4/6 = 2/3', 'x = 2'],
      voice:
        'Your method is right, but here you added the denominators. One half plus one sixth is four sixths, not two eighths. Match the denominators first and you get x equals two.',
    },
    {
      question: '3x/4 = 9/4',
      correct: true,
      student: [
        { text: '3x/4 = 9/4', mark: 'tick' },
        { text: 'x = 9/4 × 4/3', mark: 'tick' },
        { text: 'x = 3', mark: 'tick' },
      ],
      voice:
        'Good work. You multiplied by the reciprocal to undo the fraction. x equals three is correct.',
    },
    {
      question: '2/3 + x/3 = 5/3',
      correct: false,
      student: [
        { text: '2/3 + x/3 = 5/3', mark: 'tick' },
        { text: 'x/3 = 5/3 − 2/3', mark: 'tick' },
        { text: 'x/3 = 1', mark: 'tick' },
        { text: 'x = 1', mark: 'cross', circle: true, label: 'undo ÷3' },
      ],
      corrections: ['x = 1 × 3', 'x = 3'],
      voice:
        'So close. You reached x over three equals one, but then forgot to multiply by three. x equals three, not one.',
    },
    {
      question: 'x/4 − 1/4 = 1/2',
      correct: true,
      student: [
        { text: 'x/4 − 1/4 = 1/2', mark: 'tick' },
        { text: 'x/4 = 1/2 + 1/4', mark: 'tick' },
        { text: 'x/4 = 3/4', mark: 'tick' },
        { text: 'x = 3', mark: 'tick' },
      ],
      voice:
        'Solved confidently. You matched the denominators, then multiplied by four. x equals three is right.',
    },
  ],
};

const GEOMETRY: TopicDemo = {
  label: 'Angles',
  questionNumber: 1,
  lessonQuestion: 'x + 50 = 180',
  showBarModel: false,
  transcript: [
    { role: 'ai', text: 'These two angles sit on a straight line — what must they add up to?' },
    { role: 'student', text: '180 degrees?' },
    { role: 'ai', text: 'Right. So how do we find x from there?' },
  ],
  practiceQuestion: '2x + 30 = 180',
  practiceHints: [
    'The angles are on a straight line, so they add to 180. Move the 30 across first.',
    'Subtract 30 from both sides. What does that leave?',
    'Now you have 2x = 150. How do you get x on its own?',
  ],
  reviewSummary:
    'You completed five questions. Three were correct and two need improvement. You know the angle rules well — just watch the sign when you move a number across the equals.',
  worksheets: [
    {
      question: 'x + 50 = 180',
      correct: true,
      student: [
        { text: 'x + 50 = 180', mark: 'tick' },
        { text: 'x = 180 − 50', mark: 'tick' },
        { text: 'x = 130', mark: 'tick' },
      ],
      voice:
        'Clean working. Angles on a straight line add to 180, so you subtracted fifty. x equals 130 degrees is correct.',
    },
    {
      question: 'x + 90 + 40 = 180',
      correct: false,
      student: [
        { text: 'x + 90 + 40 = 180', mark: 'tick' },
        { text: 'x + 130 = 180', mark: 'tick' },
        { text: 'x = 180 + 130', mark: 'cross', circle: true, label: 'sign' },
        { text: 'x = 310', mark: 'cross' },
      ],
      corrections: ['x = 180 − 130', 'x = 50'],
      voice:
        'The angles in a triangle add to 180, so this is set up right. But when you move 130 across, it becomes minus, not plus. x equals fifty degrees.',
    },
    {
      question: '2x + 30 = 180',
      correct: true,
      student: [
        { text: '2x + 30 = 180', mark: 'tick' },
        { text: '2x = 150', mark: 'tick' },
        { text: 'x = 75', mark: 'tick' },
      ],
      voice:
        'Good work. You subtracted thirty, then halved to find one angle. x equals 75 degrees is correct.',
    },
    {
      question: 'x + 25 = 90',
      correct: false,
      student: [
        { text: 'x + 25 = 90', mark: 'tick' },
        { text: 'x = 90 + 25', mark: 'cross', circle: true, label: 'sign' },
        { text: 'x = 115', mark: 'cross' },
      ],
      corrections: ['x = 90 − 25', 'x = 65'],
      voice:
        'These angles are complementary, adding to ninety. But moving 25 across makes it minus. x equals 65 degrees.',
    },
    {
      question: '3x = 180',
      correct: true,
      student: [
        { text: '3x = 180', mark: 'tick' },
        { text: 'x = 180 ÷ 3', mark: 'tick' },
        { text: 'x = 60', mark: 'tick' },
      ],
      voice:
        'Solved confidently. Three equal angles on a straight line, so you divided 180 by three. x equals 60 degrees is right.',
    },
  ],
};

export const DEMO_CONTENT: Record<string, TopicDemo> = {
  algebra: ALGEBRA,
  number: NUMBER,
  geometry: GEOMETRY,
};

/** Content for a topic, falling back to algebra so the lesson is never blank. */
export const demoFor = (topicId: string): TopicDemo =>
  DEMO_CONTENT[topicId] ?? ALGEBRA;

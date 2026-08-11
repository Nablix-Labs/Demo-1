/**
 * Demo content — per-topic mock content so the whole journey reads coherently
 * for whichever topic the student is placed at. One source for the guided
 * lesson, independent practice and the review worksheets.
 *
 * Frontend-only demo data. In production all of this is backend-served.
 * Every problem is framed as "solve for x" so the shared lesson heading and
 * bar-model stay consistent across subjects.
 */

import type { ConceptArtName } from '@/components/ConceptArt';
import type { TutorElement } from '@/store/useNumeraStore';

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
  /** Supporting picture shown as a visual cue during guided practice. */
  visualCue: { art: ConceptArtName; caption: string };
}

/**
 * Concept-orientation media shown before the workbook. One of three modes the
 * tutor can open a topic with (Manjusha's ask): a short video, a single
 * picture, or a "micro-content" card of illustrated key points.
 */
export type OrientationMedia =
  // `src` is a real MP4 (see ORIENTATION_VIDEOS). Without it the player falls
  // back to the poster + simulated playback used before any file existed.
  | { kind: 'video'; title: string; duration: string; summary: string; src?: string }
  | { kind: 'image'; title: string; summary: string; art: ConceptArtName; caption: string }
  | { kind: 'micro'; title: string; summary: string; art: ConceptArtName; points: string[] };

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
  visualCue: {
    art: 'balance',
    caption: 'Think of the equation as a balance — whatever you do to one side, do to the other.',
  },
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
  visualCue: {
    art: 'fractionBar',
    caption: 'Match the denominators first — here 3 of 4 equal parts make three-quarters.',
  },
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
  visualCue: {
    art: 'anglePair',
    caption: 'Angles on a straight line add up to 180° — subtract the known angle to find x.',
  },
};

export const DEMO_CONTENT: Record<string, TopicDemo> = {
  algebra: ALGEBRA,
  number: NUMBER,
  geometry: GEOMETRY,
};

/** Content for a topic, falling back to algebra so the lesson is never blank. */
export const demoFor = (topicId: string): TopicDemo =>
  DEMO_CONTENT[topicId] ?? ALGEBRA;

/**
 * The real concept-orientation videos Manjusha uploaded (2026-07-26), served
 * public from Azure blob storage. Six exist (01–06); 07 is a 404.
 *
 * The file number is the Algebra subtopic's `sequence_no` in the backend's
 * `learning.topics`, NOT its `topic_code` — the codes there are inconsistent
 * (subtopic 1 is `ALG-KS3-01`, 4 is `ALG-04`), so matching on the code would
 * silently miss files. Titles below are that table's `subtopic` column.
 *
 * The container has no CORS headers, which is fine: a <video src> loads
 * cross-origin without them. Do NOT set crossOrigin on the element — that opts
 * into a CORS check the container would fail.
 */
const ORIENTATION_VIDEO_BASE = 'https://nablixmathvideos.blob.core.windows.net/numeradev';

/**
 * YouTube ids for the same orientation videos, uploaded unlisted by Manjusha
 * (2026-07-28) because the blob MP4s are ~163 MB each and made the whole app
 * feel slow while one was on screen. Preferred over the blob file: YouTube
 * serves an adaptive stream from a CDN.
 *
 * Only 1-3 have been uploaded so far; 4-6 still fall back to the blob.
 */
const ORIENTATION_YOUTUBE_IDS: Record<number, string> = {
  1: '-hKO8z_hHfM',
  2: 'Yl-uS9s4xM0',
  3: 'awY94qzVObA',
};

/** YouTube id for a backend topic code, or null when there isn't one. */
export function orientationYouTubeIdForTopicCode(topicCode: string | null | undefined): string | null {
  const match = /(\d+)\s*$/.exec(topicCode ?? '');
  return match ? ORIENTATION_YOUTUBE_IDS[Number(match[1])] ?? null : null;
}

export const ORIENTATION_VIDEOS: { sequence: number; title: string; src: string }[] = [
  'What Is Algebra?',
  'Algebraic Notation',
  'Variables and Constants',
  'Expressions',
  'Terms, Coefficients and Factors',
  'Substitution',
].map((title, i) => ({
  sequence: i + 1,
  title,
  src: `${ORIENTATION_VIDEO_BASE}/ALG-ORI-0${i + 1}.mp4`,
}));

/**
 * The blob URL for a backend topic code, or null when there's no file for it.
 *
 * The Student Model serves an orientation video record per topic but leaves
 * `asset_url` null — verified live on 2026-07-28, topic ALG-ORI-02 returns
 * video VID-KS3-T02-ORI with no URL. Manjusha's uploads are named after the
 * topic code itself, so the code resolves the file the backend is missing.
 *
 * Matched on the trailing number rather than the whole code: the codes in
 * `learning.topics` are inconsistent (`ALG-KS3-01`, `ALG-ORI-02`, `ALG-04`)
 * while the files are uniformly `ALG-ORI-0N`. Only 1–6 exist.
 */
export function orientationVideoForTopicCode(topicCode: string | null | undefined): string | null {
  const match = /(\d+)\s*$/.exec(topicCode ?? '');
  if (!match) return null;
  return ORIENTATION_VIDEOS.find((v) => v.sequence === Number(match[1]))?.src ?? null;
}

/**
 * Per-topic orientation media — one of each mode so all three are demonstrable:
 * algebra → the real video, number → picture, geometry → video (still the
 * simulated player, no file for it yet), statistics → key points.
 *
 * Only the FIRST algebra video is reachable today. The other five belong to
 * algebra subtopics, and orientation routes by topic (`/orientation/algebra`),
 * not subtopic — so serving 02–06 needs subtopic-level routing that doesn't
 * exist yet.
 */
export const ORIENTATION_MEDIA: Record<string, OrientationMedia> = {
  algebra: {
    kind: 'video',
    title: ORIENTATION_VIDEOS[0].title,
    duration: '',
    summary: 'Start here — what algebra is for, before you solve anything with it.',
    src: ORIENTATION_VIDEOS[0].src,
  },
  number: {
    kind: 'image',
    title: 'Working with fractions',
    summary: 'A fraction is parts of a whole — match the denominators before adding or subtracting.',
    art: 'fractionBar',
    caption: 'Three of four equal parts shaded = 3⁄4.',
  },
  geometry: {
    kind: 'video',
    title: 'Angle rules',
    duration: '4:30',
    summary: 'Angles measure turn; the rules on lines and in shapes let you find the missing one.',
  },
  statistics: {
    kind: 'micro',
    title: 'Reading a bar chart',
    summary: 'Bar charts show how often each value comes up — read the heights to compare.',
    art: 'barChart',
    points: [
      "Each bar's height is the frequency — how many times a value occurs.",
      'Compare heights to see which values are common or rare.',
      'The tallest bar is the mode: the most frequent value.',
    ],
  },
};

/** Orientation media for a topic, or null when none exists yet (→ empty state). */
export const orientationFor = (topicId: string): OrientationMedia | null =>
  ORIENTATION_MEDIA[topicId] ?? null;

/**
 * The concept check that follows the orientation content, still inside Phase 1.
 *
 * Once the video (or picture / key points) is done, the tutor poses one question
 * about the idea and works it through on the canvas. **Only the tutor writes
 * here** (Manjusha, 2026-07-26) — the student watches, then teaches it back in
 * Phase 2. So `elements` is a tutor draw batch in the normal `canvas_draw`
 * contract (normalised 0–1, `text`/`math` anchored at their LEFT edge — see
 * docs/TUTOR-CANVAS-WRITE-SPEC.md §3.3).
 *
 * This is demo content: the backend will serve the question and emit the draw
 * commands once its producer exists, at which point this becomes the mock-mode
 * fallback like every other entry in this file.
 */
export interface OrientationCheck {
  question: string;
  elements: Array<Omit<TutorElement, 'id'>>;
}

export const ORIENTATION_CHECK: Record<string, OrientationCheck> = {
  algebra: {
    question: 'A box holds an unknown number of counters. You add 4 more and end up with 9. How would you write that as an equation?',
    elements: [
      { kind: 'text', x: 0.08, y: 0.18, text: 'unknown counters in the box:', size: 17, color: '#5A6478' },
      { kind: 'math', x: 0.08, y: 0.32, tex: 'x', size: 30 },
      { kind: 'text', x: 0.18, y: 0.32, text: 'add 4 more  →', size: 17, color: '#5A6478' },
      { kind: 'math', x: 0.45, y: 0.32, tex: 'x + 4', size: 30 },
      { kind: 'text', x: 0.08, y: 0.52, text: 'ends up as 9, so both sides balance:', size: 17, color: '#5A6478' },
      { kind: 'math', x: 0.08, y: 0.66, tex: 'x + 4 = 9', size: 34 },
      { kind: 'line', from: [0.08, 0.74], to: [0.30, 0.74], color: '#F77F00', strokeWidth: 3 },
    ],
  },
  number: {
    question: 'Three of four equal parts of a bar are shaded. How would you write that as a fraction?',
    elements: [
      { kind: 'text', x: 0.08, y: 0.20, text: 'parts shaded', size: 17, color: '#5A6478' },
      { kind: 'text', x: 0.08, y: 0.42, text: 'equal parts in total', size: 17, color: '#5A6478' },
      { kind: 'math', x: 0.55, y: 0.31, tex: '\\frac{3}{4}', size: 40 },
      { kind: 'arrow', from: [0.34, 0.20], to: [0.52, 0.26], color: '#00B4D8', strokeWidth: 2 },
      { kind: 'arrow', from: [0.34, 0.42], to: [0.52, 0.37], color: '#00B4D8', strokeWidth: 2 },
      { kind: 'text', x: 0.08, y: 0.66, text: 'the bottom number says how many parts make a whole', size: 16, color: '#5A6478' },
    ],
  },
  geometry: {
    question: 'Two angles sit on a straight line and one of them is 130°. How would you find the other?',
    elements: [
      { kind: 'line', from: [0.08, 0.34], to: [0.52, 0.34], color: '#1B2A4A', strokeWidth: 3 },
      { kind: 'line', from: [0.30, 0.34], to: [0.38, 0.14], color: '#1B2A4A', strokeWidth: 3 },
      { kind: 'text', x: 0.17, y: 0.28, text: '130°', size: 18 },
      { kind: 'text', x: 0.40, y: 0.28, text: '?', size: 20, color: '#F77F00' },
      { kind: 'text', x: 0.08, y: 0.54, text: 'angles on a straight line add to 180°', size: 17, color: '#5A6478' },
      { kind: 'math', x: 0.08, y: 0.70, tex: '180 - 130 = 50', size: 32 },
    ],
  },
  statistics: {
    question: 'On a bar chart, one bar is taller than all the others. What does that tell you?',
    elements: [
      { kind: 'rect', x: 0.10, y: 0.40, w: 0.06, h: 0.22, color: '#1B2A4A', strokeWidth: 2 },
      { kind: 'rect', x: 0.20, y: 0.26, w: 0.06, h: 0.36, color: '#F77F00', strokeWidth: 3 },
      { kind: 'rect', x: 0.30, y: 0.48, w: 0.06, h: 0.14, color: '#1B2A4A', strokeWidth: 2 },
      { kind: 'text', x: 0.42, y: 0.30, text: 'tallest bar = most frequent value', size: 17, color: '#5A6478' },
      { kind: 'text', x: 0.42, y: 0.44, text: 'that value is the mode', size: 18 },
    ],
  },
};

/** The Phase-1 concept check for a topic, or null when none exists yet. */
export const orientationCheckFor = (topicId: string): OrientationCheck | null =>
  ORIENTATION_CHECK[topicId] ?? null;

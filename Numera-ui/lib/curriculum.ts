/**
 * Curriculum mock data for the learning library (frontend-only).
 *
 * Shape: topic → subtopic → lesson, each lesson carrying a learning status and
 * each subtopic a UK Key Stage. In production this comes from the backend; the
 * UI only reads it. Kept here behind small accessors so swapping to a real
 * source is a one-file change.
 *
 * Key Stages (UK, A-Level aligned):
 *   KS3 = ages 11–13 · KS4 = ages 14–16 (GCSE) · KS5 = ages 17–18 (A-Level)
 */

export type LessonStatus = 'mastered' | 'in-progress' | 'not-started';
export type KeyStage = 'KS3' | 'KS4' | 'KS5';

export const KEY_STAGES: { id: KeyStage; label: string; ages: string }[] = [
  { id: 'KS3', label: 'KS3', ages: 'Ages 11–13' },
  { id: 'KS4', label: 'KS4', ages: 'Ages 14–16 · GCSE' },
  { id: 'KS5', label: 'KS5', ages: 'Ages 17–18 · A-Level' },
];

export interface Lesson {
  id: string;
  title: string;
  status: LessonStatus;
}

export interface Subtopic {
  id: string;
  title: string;
  keyStage: KeyStage;
  lessons: Lesson[];
}

export interface Topic {
  id: string;
  title: string;
  blurb: string;
  subtopics: Subtopic[];
}

export const CURRICULUM: Topic[] = [
  {
    id: 'algebra',
    title: 'Algebra',
    blurb: 'Equations, expressions and graphs.',
    subtopics: [
      {
        id: 'linear-equations',
        title: 'Linear equations',
        keyStage: 'KS3',
        lessons: [
          { id: 'one-step', title: 'One-step equations', status: 'mastered' },
          { id: 'two-step', title: 'Two-step equations', status: 'mastered' },
          { id: 'solving-for-x', title: 'Solving for x', status: 'in-progress' },
          { id: 'both-sides', title: 'Variables on both sides', status: 'not-started' },
        ],
      },
      {
        id: 'expressions',
        title: 'Expressions',
        keyStage: 'KS4',
        lessons: [
          { id: 'simplifying', title: 'Simplifying expressions', status: 'mastered' },
          { id: 'expanding', title: 'Expanding brackets', status: 'in-progress' },
          { id: 'factorising', title: 'Factorising', status: 'not-started' },
        ],
      },
      {
        id: 'calculus',
        title: 'Intro to calculus',
        keyStage: 'KS5',
        lessons: [
          { id: 'differentiation', title: 'Differentiation basics', status: 'not-started' },
          { id: 'gradients', title: 'Gradients of curves', status: 'not-started' },
        ],
      },
    ],
  },
  {
    id: 'number',
    title: 'Number',
    blurb: 'Fractions, ratio and percentages.',
    subtopics: [
      {
        id: 'fractions',
        title: 'Fractions',
        keyStage: 'KS3',
        lessons: [
          { id: 'equivalent', title: 'Equivalent fractions', status: 'mastered' },
          { id: 'add-subtract', title: 'Adding & subtracting', status: 'in-progress' },
          { id: 'multiply-divide', title: 'Multiplying & dividing', status: 'not-started' },
        ],
      },
      {
        id: 'ratio',
        title: 'Ratio & proportion',
        keyStage: 'KS4',
        lessons: [
          { id: 'simplify-ratio', title: 'Simplifying ratios', status: 'not-started' },
          { id: 'sharing', title: 'Sharing in a ratio', status: 'not-started' },
        ],
      },
    ],
  },
  {
    id: 'geometry',
    title: 'Geometry',
    blurb: 'Shapes, angles and measures.',
    subtopics: [
      {
        id: 'angles',
        title: 'Angles',
        keyStage: 'KS3',
        lessons: [
          { id: 'angle-rules', title: 'Angle rules', status: 'not-started' },
          { id: 'polygons', title: 'Angles in polygons', status: 'not-started' },
        ],
      },
      {
        id: 'area',
        title: 'Area & perimeter',
        keyStage: 'KS4',
        lessons: [
          { id: 'rectangles', title: 'Rectangles & triangles', status: 'not-started' },
          { id: 'circles', title: 'Circles', status: 'not-started' },
        ],
      },
    ],
  },
  {
    id: 'statistics',
    title: 'Statistics',
    blurb: 'Data, averages and charts.',
    subtopics: [
      {
        id: 'averages',
        title: 'Averages',
        keyStage: 'KS3',
        lessons: [
          { id: 'mean-median-mode', title: 'Mean, median & mode', status: 'not-started' },
          { id: 'range', title: 'Range', status: 'not-started' },
        ],
      },
    ],
  },
];

/** All lessons in a topic, flattened. */
export function topicLessons(t: Topic): Lesson[] {
  return t.subtopics.flatMap((s) => s.lessons);
}

/** Percentage of a topic's lessons that are mastered. */
export function topicProgress(t: Topic): number {
  const all = topicLessons(t);
  if (all.length === 0) return 0;
  const done = all.filter((l) => l.status === 'mastered').length;
  return Math.round((done / all.length) * 100);
}

export function getTopic(id: string): Topic | undefined {
  return CURRICULUM.find((t) => t.id === id);
}

/** Status with the student's persisted completions applied as overrides. */
export function effectiveStatus(lesson: Lesson, completed: string[]): LessonStatus {
  return completed.includes(lesson.id) ? 'mastered' : lesson.status;
}

/** Topic progress %, counting persisted completions. */
export function topicProgressWith(t: Topic, completed: string[]): number {
  const all = topicLessons(t);
  if (all.length === 0) return 0;
  const done = all.filter((l) => effectiveStatus(l, completed) === 'mastered').length;
  return Math.round((done / all.length) * 100);
}

/** Distinct Key Stages a topic spans. */
export function topicKeyStages(t: Topic): KeyStage[] {
  return Array.from(new Set(t.subtopics.map((s) => s.keyStage)));
}

/**
 * Age → Key Stage. A student only ever sees content for their own stage, so
 * placement and the workbook are driven by age, not free browsing.
 * KS3 = 11–13 · KS4 = 14–16 (GCSE) · KS5 = 17–18 (A-Level).
 */
export function keyStageForAge(age: number): KeyStage {
  if (age <= 13) return 'KS3';
  if (age <= 16) return 'KS4';
  return 'KS5';
}

/** A topic's subtopics limited to one Key Stage (age-gated view). */
export function subtopicsForStage(t: Topic, ks: KeyStage): Subtopic[] {
  return t.subtopics.filter((s) => s.keyStage === ks);
}

/** Topic progress %, counting only the lessons visible at a Key Stage. */
export function topicProgressForStage(t: Topic, ks: KeyStage, completed: string[]): number {
  const all = subtopicsForStage(t, ks).flatMap((s) => s.lessons);
  if (all.length === 0) return 0;
  const done = all.filter((l) => effectiveStatus(l, completed) === 'mastered').length;
  return Math.round((done / all.length) * 100);
}

/**
 * Every number on the dashboard, worked out from the raw sessions.
 *
 * Pure functions over ChildData so they are tested (derive.test.ts) and give
 * the same answers on sample and live data. The backend sends raw records; the
 * parent-facing wording and the sums live here, in one place.
 */
import type { Attempt, ChildData, Misconception, Phase, Session, SkillStatus, TopicProgress } from './types';

const DAY = 86_400_000;

export interface Range {
  days: number;
  /** Midnight at the start of the first day in the range. */
  from: Date;
  /** Midnight after the last day (today). */
  to: Date;
}

export function rangeEndingToday(days: number, today = new Date()): Range {
  const to = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  return { days, from: new Date(to.getTime() - days * DAY), to };
}

/** The same-length range immediately before `r`. */
export function previousRange(r: Range): Range {
  return { days: r.days, from: new Date(r.from.getTime() - r.days * DAY), to: r.from };
}

export const inRange = (iso: string, r: Range) => {
  const t = new Date(iso).getTime();
  return t >= r.from.getTime() && t < r.to.getTime();
};

export const sessionsIn = (d: ChildData, r: Range) => d.sessions.filter((s) => inRange(s.session_date, r));
export const attemptsIn = (d: ChildData, r: Range) => sessionsIn(d, r).flatMap((s) => s.attempts);

const pct = (n: number, of: number) => (of === 0 ? 0 : Math.round((n / of) * 100));

export interface OutcomeSplit {
  total: number;
  correct: number;
  partial: number;
  incorrect: number;
  correctPct: number;
  partialPct: number;
  incorrectPct: number;
  /** Correct counts in full, partly correct counts half. */
  score: number;
}

export function outcomes(attempts: Attempt[]): OutcomeSplit {
  const correct = attempts.filter((a) => a.evaluation === 'CORRECT').length;
  const partial = attempts.filter((a) => a.evaluation === 'PARTIALLY_CORRECT').length;
  const incorrect = attempts.length - correct - partial;
  const total = attempts.length;
  // Rounded shares can sum to 99 or 101; the remainder goes to the largest.
  const c = pct(correct, total), p = pct(partial, total);
  return {
    total, correct, partial, incorrect,
    correctPct: c, partialPct: p, incorrectPct: total ? 100 - c - p : 0,
    score: total ? Math.round(((correct + partial * 0.5) / total) * 100) : 0,
  };
}

/** Questions answered on each day of the range, oldest first. */
export function questionsPerDay(d: ChildData, r: Range): { date: Date; count: number }[] {
  const out = Array.from({ length: r.days }, (_, i) => ({ date: new Date(r.from.getTime() + i * DAY), count: 0 }));
  for (const a of attemptsIn(d, r)) {
    const i = Math.floor((new Date(a.attempted_at).getTime() - r.from.getTime()) / DAY);
    if (out[i]) out[i].count++;
  }
  return out;
}

export function avgSecondsPerQuestion(attempts: Attempt[]): number {
  if (!attempts.length) return 0;
  return Math.round(attempts.reduce((s, a) => s + a.time_taken_seconds, 0) / attempts.length);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60), s = seconds % 60;
  if (m < 60) return s ? `${m}m ${s}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Weekly score, one point per 7 days ending today, oldest first. */
export function weeklyScores(d: ChildData, weeks: number, today = new Date()): { weekEnding: Date; score: number | null }[] {
  return Array.from({ length: weeks }, (_, i) => {
    const r = rangeEndingToday(7, new Date(today.getTime() - (weeks - 1 - i) * 7 * DAY));
    const a = attemptsIn(d, r);
    return { weekEnding: new Date(r.to.getTime() - DAY), score: a.length ? outcomes(a).score : null };
  });
}

export interface SkillRow {
  topic: TopicProgress;
  skill: TopicProgress['micro_skills'][number];
}

const allSkills = (d: ChildData): SkillRow[] =>
  d.topics.flatMap((topic) => topic.micro_skills.map((skill) => ({ topic, skill })));

export const strengths = (d: ChildData) => allSkills(d).filter((r) => r.skill.status === 'INDEPENDENTLY_VERIFIED');
export const developing = (d: ChildData) =>
  allSkills(d).filter((r) => r.skill.status === 'RESCUE_REQUIRED' || r.skill.status === 'VERIFIED_WITH_SUPPORT')
    .sort((a, b) => (a.skill.status === 'RESCUE_REQUIRED' ? -1 : 0) - (b.skill.status === 'RESCUE_REQUIRED' ? -1 : 0));

export const SKILL_LABEL: Record<SkillStatus, string> = {
  INDEPENDENTLY_VERIFIED: 'Strong',
  VERIFIED_WITH_SUPPORT: 'Developing',
  RESCUE_REQUIRED: 'Needs practice',
  UNKNOWN: 'Not started',
};

export interface MisconceptionCount { misconception: Misconception; count: number }

export function misconceptionCounts(d: ChildData, attempts: Attempt[]): MisconceptionCount[] {
  const counts = new Map<string, number>();
  for (const a of attempts) if (a.misconception_id) counts.set(a.misconception_id, (counts.get(a.misconception_id) ?? 0) + 1);
  return d.misconceptions
    .map((m) => ({ misconception: m, count: counts.get(m.id) ?? 0 }))
    .filter((x) => x.count > 0)
    .sort((a, b) => b.count - a.count);
}

export interface LearnsBest {
  /** Success rate when a picture/visual cue was shown vs not. */
  visualRate: number;
  plainRate: number;
  /** The hint rung that most often came before a correct answer (0 = none). */
  commonHintLevel: number;
  independentPct: number;
}

export function learnsBest(attempts: Attempt[]): LearnsBest {
  const rate = (xs: Attempt[]) => pct(xs.filter((a) => a.evaluation === 'CORRECT').length, xs.length);
  const helped = attempts.filter((a) => a.evaluation === 'CORRECT' && a.hint_level_used > 0);
  const byLevel = [1, 2, 3].map((l) => helped.filter((a) => a.hint_level_used === l).length);
  const max = Math.max(...byLevel);
  return {
    visualRate: rate(attempts.filter((a) => a.visual_cue_shown)),
    plainRate: rate(attempts.filter((a) => !a.visual_cue_shown)),
    commonHintLevel: max === 0 ? 0 : byLevel.indexOf(max) + 1,
    independentPct: pct(attempts.filter((a) => a.independent).length, attempts.length),
  };
}

export interface Snapshot {
  topicsStudied: number;
  questions: number;
  correct: number;
  hints: number;
  scaffolds: number;
  interventions: number;
  minutes: number;
  sessions: number;
}

export function snapshot(sessions: Session[]): Snapshot {
  const a = sessions.flatMap((s) => s.attempts);
  return {
    topicsStudied: new Set(sessions.map((s) => s.topic_id)).size,
    questions: a.length,
    correct: a.filter((x) => x.evaluation === 'CORRECT').length,
    hints: a.filter((x) => x.hint_level_used > 0).length,
    scaffolds: a.filter((x) => x.scaffold_used).length,
    interventions: sessions.reduce((s, x) => s + x.tutor_interventions, 0),
    minutes: Math.round(sessions.reduce((s, x) => s + x.session_duration_seconds, 0) / 60),
    sessions: sessions.length,
  };
}

/** Days in a row with a session, counting back from today (or yesterday if today has none yet). */
export function streak(d: ChildData, today = new Date()): number {
  const days = new Set(d.sessions.map((s) => new Date(s.session_date).toDateString()));
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  let cursor = days.has(start.toDateString()) ? start : new Date(start.getTime() - DAY);
  let n = 0;
  while (days.has(cursor.toDateString())) {
    n++;
    cursor = new Date(cursor.getTime() - DAY);
  }
  return n;
}

/** Monday→Sunday of the current week: was there a session? `null` = still to come. */
export function thisWeek(d: ChildData, today = new Date()): { label: string; done: boolean | null }[] {
  const days = new Set(d.sessions.map((s) => new Date(s.session_date).toDateString()));
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const monday = new Date(start.getTime() - ((start.getDay() + 6) % 7) * DAY);
  return ['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label, i) => {
    const day = new Date(monday.getTime() + i * DAY);
    if (day.getTime() > start.getTime()) return { label, done: null };
    return { label, done: days.has(day.toDateString()) };
  });
}

export const PHASES: { id: Phase; label: string; parent: string }[] = [
  { id: 'PHASE_0_DIAGNOSTIC', label: 'Check-in', parent: 'A short quiz to find the right starting point.' },
  { id: 'PHASE_1_ORIENTATION', label: 'Introduction', parent: 'The big idea, explained with a worked example.' },
  { id: 'PHASE_2_GUIDED_LEARNING', label: 'Guided practice', parent: 'Questions with the tutor helping step by step.' },
  { id: 'PHASE_3_INDEPENDENT_PRACTICE', label: 'Practice alone', parent: 'Questions on their own, help only if needed.' },
  { id: 'PHASE_4_REVIEW', label: 'Review', parent: 'A look back at mistakes and what was learned.' },
];

export const phaseLabel = (p: Phase | null) => PHASES.find((x) => x.id === p)?.label ?? '—';

export const MASTERY_LABEL: Record<TopicProgress['mastery_status'], string> = {
  NOT_STARTED: 'Not started',
  IN_PROGRESS: 'In progress',
  MASTERED: 'Mastered',
  REVIEW: 'In review',
};

/** How far through the five phases a topic is, 0–100. */
export const topicPercent = (t: TopicProgress) =>
  t.mastery_status === 'MASTERED' ? 100 : Math.round((t.phases_completed.length / PHASES.length) * 100);

export interface NextStep { title: string; detail: string; topicId: string }

/** What to do next: the open topic's recommended action, then the weakest skills. */
export function nextSteps(d: ChildData): NextStep[] {
  const steps: NextStep[] = [];
  for (const t of d.topics.filter((x) => x.mastery_status === 'IN_PROGRESS' && x.recommended_next_action)) {
    steps.push({ title: `${phaseLabel(t.current_phase)}: ${t.title}`, detail: t.recommended_next_action!, topicId: t.topic_id });
  }
  for (const r of developing(d).filter((x) => x.skill.status === 'RESCUE_REQUIRED')) {
    steps.push({ title: `Practise: ${r.skill.label}`, detail: r.skill.description, topicId: r.topic.topic_id });
  }
  const upcoming = d.topics.find((x) => x.mastery_status === 'NOT_STARTED');
  if (upcoming) steps.push({ title: `Coming up: ${upcoming.title}`, detail: upcoming.recommended_next_action ?? 'The next topic in the plan.', topicId: upcoming.topic_id });
  return steps;
}

export const change = (now: number, before: number) => now - before;

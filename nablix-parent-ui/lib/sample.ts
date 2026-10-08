/**
 * Sample data for the portal while no parent API exists.
 *
 * Shaped exactly like the HTTP responses (lib/types.ts) so every screen, sum
 * and chart runs the same code it will run on live data. Generated from a fixed
 * seed and anchored to today, so it is stable between reloads and never looks
 * stale. Every page shows a "Sample data" banner while this is the source.
 */
import type {
  Attempt, ChildData, ConsentRecord, Evaluation, Misconception, Phase, Session, TopicProgress,
} from './types';

/** Mulberry32 — small, fast, deterministic. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const DAY = 86_400_000;

const TOPICS: TopicProgress[] = [
  {
    topic_id: 'ALG-KS3-01',
    title: 'One-step equations',
    strand: 'algebra',
    mastery_status: 'MASTERED',
    current_phase: null,
    phases_completed: ['PHASE_0_DIAGNOSTIC', 'PHASE_1_ORIENTATION', 'PHASE_2_GUIDED_LEARNING', 'PHASE_3_INDEPENDENT_PRACTICE', 'PHASE_4_REVIEW'],
    micro_skills: [
      { id: 'T01.M1', label: 'Spotting the unknown', description: 'Finds the letter that stands for the missing number.', status: 'INDEPENDENTLY_VERIFIED' },
      { id: 'T01.M2', label: 'Undoing addition', description: 'Subtracts from both sides to undo a +.', status: 'INDEPENDENTLY_VERIFIED' },
      { id: 'T01.M3', label: 'Undoing multiplication', description: 'Divides both sides to undo a ×.', status: 'INDEPENDENTLY_VERIFIED' },
      { id: 'T01.M4', label: 'Checking the answer', description: 'Puts the answer back in to check it works.', status: 'VERIFIED_WITH_SUPPORT' },
    ],
    recommended_next_action: null,
    started_at: null,
    last_activity_at: null,
  },
  {
    topic_id: 'ALG-ORI-02',
    title: 'Reading algebraic notation',
    strand: 'algebra',
    mastery_status: 'IN_PROGRESS',
    current_phase: 'PHASE_3_INDEPENDENT_PRACTICE',
    phases_completed: ['PHASE_0_DIAGNOSTIC', 'PHASE_1_ORIENTATION', 'PHASE_2_GUIDED_LEARNING'],
    micro_skills: [
      { id: 'T02.M1', label: 'Hidden multiplication', description: 'Reads 3x as 3 × x.', status: 'INDEPENDENTLY_VERIFIED' },
      { id: 'T02.M2', label: 'Powers and brackets', description: 'Reads x² and 2(x + 1) correctly.', status: 'VERIFIED_WITH_SUPPORT' },
      { id: 'T02.M3', label: 'Division as a fraction', description: 'Reads x/4 as x ÷ 4.', status: 'RESCUE_REQUIRED' },
      { id: 'T02.M4', label: 'Writing expressions', description: 'Turns words into a short expression.', status: 'VERIFIED_WITH_SUPPORT' },
    ],
    recommended_next_action: 'Practise reading division written as a fraction, like x/4.',
    started_at: null,
    last_activity_at: null,
  },
  {
    topic_id: 'ALG-ORI-03',
    title: 'Two-step equations',
    strand: 'algebra',
    mastery_status: 'IN_PROGRESS',
    current_phase: 'PHASE_2_GUIDED_LEARNING',
    phases_completed: ['PHASE_0_DIAGNOSTIC', 'PHASE_1_ORIENTATION'],
    micro_skills: [
      { id: 'T03.M1', label: 'Choosing the first step', description: 'Undoes the + or − before the ×.', status: 'RESCUE_REQUIRED' },
      { id: 'T03.M2', label: 'Keeping both sides balanced', description: 'Does the same thing to both sides.', status: 'VERIFIED_WITH_SUPPORT' },
      { id: 'T03.M3', label: 'Word problems', description: 'Sets up an equation from a real-life story.', status: 'UNKNOWN' },
    ],
    recommended_next_action: 'Keep going with guided practice on which step to undo first.',
    started_at: null,
    last_activity_at: null,
  },
  {
    topic_id: 'NUM-KS3-01',
    title: 'Equivalent fractions',
    strand: 'number',
    mastery_status: 'NOT_STARTED',
    current_phase: null,
    phases_completed: [],
    micro_skills: [
      { id: 'N01.M1', label: 'Same value, different look', description: 'Sees that 1/2 and 2/4 are equal.', status: 'UNKNOWN' },
      { id: 'N01.M2', label: 'Simplifying', description: 'Divides top and bottom by the same number.', status: 'UNKNOWN' },
    ],
    recommended_next_action: 'Starts after Two-step equations.',
    started_at: null,
    last_activity_at: null,
  },
];

const MISCONCEPTIONS: Misconception[] = [
  { id: 'MC-WRONG-INVERSE', label: 'Uses the wrong opposite operation', description: 'Adds when it should subtract, or multiplies when it should divide, to undo a step.', topic_id: 'ALG-ORI-03' },
  { id: 'MC-3X-AS-SUM', label: 'Reads 3x as 3 + x', description: 'Treats a number next to a letter as adding instead of multiplying.', topic_id: 'ALG-ORI-02' },
  { id: 'MC-ORDER-OF-UNDO', label: 'Undoes steps in the wrong order', description: 'Divides first in 2x + 3 = 11 instead of subtracting 3 first.', topic_id: 'ALG-ORI-03' },
  { id: 'MC-ONE-SIDE', label: 'Changes only one side', description: 'Does an operation to one side of the equation but not the other.', topic_id: 'ALG-KS3-01' },
];

const QUESTIONS: Record<string, string[]> = {
  'ALG-KS3-01': ['x + 7 = 12', 'y − 4 = 9', '5x = 35', 'n / 3 = 6', 'a + 13 = 20'],
  'ALG-ORI-02': ['What does 4y mean?', 'Write "x times 6" in algebra', 'What does x/4 mean?', 'Read 2(x + 1) aloud', 'What is x² when x = 3?'],
  'ALG-ORI-03': ['2x + 3 = 11', '3y − 5 = 10', '4n + 1 = 21', '5a − 2 = 18', 'A taxi costs £3 plus £2 a mile. The fare is £13. How many miles?'],
};

const MC_BY_TOPIC: Record<string, string[]> = {
  'ALG-KS3-01': ['MC-ONE-SIDE', 'MC-WRONG-INVERSE'],
  'ALG-ORI-02': ['MC-3X-AS-SUM'],
  'ALG-ORI-03': ['MC-WRONG-INVERSE', 'MC-ORDER-OF-UNDO', 'MC-ORDER-OF-UNDO'],
};

/** Which topic was being studied N days ago — finished topics come first. */
function topicForDay(daysAgo: number): string {
  if (daysAgo > 28) return 'ALG-KS3-01';
  if (daysAgo > 12) return 'ALG-ORI-02';
  return daysAgo % 3 === 0 ? 'ALG-ORI-02' : 'ALG-ORI-03';
}

function phaseFor(topicId: string, r: () => number): Phase {
  const t = TOPICS.find((x) => x.topic_id === topicId)!;
  if (t.mastery_status === 'MASTERED') return r() < 0.5 ? 'PHASE_3_INDEPENDENT_PRACTICE' : 'PHASE_2_GUIDED_LEARNING';
  return t.current_phase ?? 'PHASE_2_GUIDED_LEARNING';
}

function buildSessions(today: Date): Session[] {
  const r = rng(20261009);
  const sessions: Session[] = [];
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();

  for (let daysAgo = 41; daysAgo >= 0; daysAgo--) {
    // A six-day run up to yesterday, a rest today, gaps further back.
    const studied = daysAgo === 0 ? false : daysAgo <= 6 ? true : r() < 0.62;
    if (!studied) continue;

    const day = end - daysAgo * DAY;
    const start = day + (16 + Math.floor(r() * 4)) * 3_600_000 + Math.floor(r() * 50) * 60_000;
    const topicId = topicForDay(daysAgo);
    // Accuracy and independence grow over the six weeks; hints fall.
    const progress = 1 - daysAgo / 41;
    const pCorrect = 0.5 + 0.3 * progress;
    const pPartial = 0.2 - 0.06 * progress;
    const qs = QUESTIONS[topicId];
    const n = 6 + Math.floor(r() * 7);
    const attempts: Attempt[] = [];
    let t = start;
    for (let i = 0; i < n; i++) {
      const x = r();
      const evaluation: Evaluation = x < pCorrect ? 'CORRECT' : x < pCorrect + pPartial ? 'PARTIALLY_CORRECT' : 'INCORRECT';
      const visual = r() < 0.35;
      const hint = evaluation === 'CORRECT' && r() < 0.55 + 0.3 * progress ? 0 : 1 + Math.floor(r() * (progress > 0.6 ? 1.6 : 3));
      const scaffold = hint >= 2 && r() < 0.5;
      const t0 = Math.round(105 - 30 * progress + (r() - 0.5) * 40);
      const skills = TOPICS.find((s) => s.topic_id === topicId)!.micro_skills;
      const mcs = MC_BY_TOPIC[topicId];
      attempts.push({
        question_text: qs[Math.floor(r() * qs.length)],
        phase: phaseFor(topicId, r),
        // Visual cues help: a wrong answer is sometimes rescued into a right one.
        evaluation: visual && evaluation === 'INCORRECT' && r() < 0.5 ? 'CORRECT' : evaluation,
        topic_id: topicId,
        micro_skill_id: skills[Math.floor(r() * skills.length)].id,
        hint_level_used: hint,
        scaffold_used: scaffold,
        visual_cue_shown: visual,
        independent: hint === 0 && !scaffold,
        time_taken_seconds: Math.max(25, t0),
        misconception_id: evaluation === 'CORRECT' ? null : mcs[Math.floor(r() * mcs.length)],
        attempted_at: new Date(t).toISOString(),
      });
      t += t0 * 1000 + 20_000;
    }
    sessions.push({
      session_id: `SES-${new Date(day).toISOString().slice(0, 10)}`,
      topic_id: topicId,
      session_date: new Date(start).toISOString(),
      session_duration_seconds: Math.round((t - start) / 1000) + 120,
      phases_completed: [],
      tutor_interventions: attempts.filter((a) => a.evaluation === 'INCORRECT' && a.hint_level_used >= 3).length,
      attempts,
    });
  }
  return sessions;
}

function buildConsents(today: Date): ConsentRecord[] {
  const signed = new Date(today.getTime() - 60 * DAY).toISOString();
  return [
    'account_creation', 'ai_tutor_usage', 'canvas_processing', 'voice_processing',
    'learning_analytics', 'safety_monitoring',
  ].map((purpose) => ({ purpose, accepted_at: signed, withdrawn_at: null }) as ConsentRecord)
    .concat([{ purpose: 'marketing', accepted_at: null, withdrawn_at: null }]);
}

export function sampleChildData(today = new Date()): ChildData {
  const sessions = buildSessions(today);
  const topics = TOPICS.map((t) => {
    const mine = sessions.filter((s) => s.topic_id === t.topic_id);
    return {
      ...t,
      started_at: mine[0]?.session_date ?? null,
      last_activity_at: mine[mine.length - 1]?.session_date ?? null,
    };
  });
  return {
    child: { student_code: 'SAMPLE-01', name: 'Riya Sharma', year_group: 'Year 8' },
    topics,
    sessions,
    misconceptions: MISCONCEPTIONS,
    consents: buildConsents(today),
  };
}

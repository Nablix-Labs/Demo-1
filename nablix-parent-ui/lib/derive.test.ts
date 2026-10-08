import { describe, expect, it } from 'vitest';
import {
  outcomes, rangeEndingToday, previousRange, questionsPerDay, streak, thisWeek, weeklyScores,
  learnsBest, misconceptionCounts, nextSteps, formatDuration, topicPercent,
} from './derive';
import { sampleChildData } from './sample';
import type { Attempt, ChildData } from './types';

const TODAY = new Date(2026, 9, 9, 12); // Fri 9 Oct 2026, noon

function attempt(over: Partial<Attempt> = {}): Attempt {
  return {
    question_text: 'x + 1 = 2', phase: 'PHASE_2_GUIDED_LEARNING', evaluation: 'CORRECT', topic_id: 'T',
    micro_skill_id: 'M', hint_level_used: 0, scaffold_used: false, visual_cue_shown: false, independent: true,
    time_taken_seconds: 60, misconception_id: null, attempted_at: TODAY.toISOString(), ...over,
  };
}

function withSessions(dates: Date[]): ChildData {
  const d = sampleChildData(TODAY);
  return {
    ...d,
    sessions: dates.map((date, i) => ({
      session_id: `S${i}`, topic_id: 'T', session_date: date.toISOString(), session_duration_seconds: 600,
      phases_completed: [], tutor_interventions: 0, attempts: [attempt({ attempted_at: date.toISOString() })],
    })),
  };
}

const daysAgo = (n: number) => new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() - n, 17);

describe('outcomes', () => {
  it('splits answers and scores partial as half', () => {
    const o = outcomes([attempt(), attempt(), attempt({ evaluation: 'PARTIALLY_CORRECT' }), attempt({ evaluation: 'INCORRECT' })]);
    expect(o).toMatchObject({ total: 4, correct: 2, partial: 1, incorrect: 1, score: 63 });
    expect(o.correctPct + o.partialPct + o.incorrectPct).toBe(100);
  });

  it('is all zeros with no answers', () => {
    expect(outcomes([])).toMatchObject({ total: 0, score: 0, incorrectPct: 0 });
  });
});

describe('ranges', () => {
  it('covers whole days ending tonight, and the previous range touches it', () => {
    const r = rangeEndingToday(7, TODAY);
    expect(r.to.getDate()).toBe(10);
    expect(r.from.getDate()).toBe(3);
    expect(previousRange(r).to.getTime()).toBe(r.from.getTime());
  });

  it('counts questions on the right day', () => {
    const d = withSessions([daysAgo(0), daysAgo(0), daysAgo(2)]);
    const days = questionsPerDay(d, rangeEndingToday(7, TODAY));
    expect(days).toHaveLength(7);
    expect(days[6].count).toBe(2);
    expect(days[4].count).toBe(1);
  });
});

describe('streak', () => {
  it('counts back from yesterday when today has no session yet', () => {
    expect(streak(withSessions([daysAgo(1), daysAgo(2), daysAgo(3), daysAgo(5)]), TODAY)).toBe(3);
  });

  it('includes today when there is a session today', () => {
    expect(streak(withSessions([daysAgo(0), daysAgo(1)]), TODAY)).toBe(2);
  });

  it('is zero after a missed day', () => {
    expect(streak(withSessions([daysAgo(2)]), TODAY)).toBe(0);
  });

  it('marks this week Monday to Sunday, future days as null', () => {
    const w = thisWeek(withSessions([daysAgo(4)]), TODAY); // Monday 5 Oct
    expect(w.map((x) => x.done)).toEqual([true, false, false, false, false, null, null]);
  });
});

describe('weekly scores', () => {
  it('leaves weeks with no sessions empty rather than zero', () => {
    const w = weeklyScores(withSessions([daysAgo(0)]), 3, TODAY);
    expect(w.map((x) => x.score)).toEqual([null, null, 100]);
  });
});

describe('learns best', () => {
  it('compares pictures against none and finds the common hint level', () => {
    const lb = learnsBest([
      attempt({ visual_cue_shown: true }),
      attempt({ visual_cue_shown: false, evaluation: 'INCORRECT', independent: false }),
      attempt({ hint_level_used: 1, independent: false }),
      attempt({ hint_level_used: 1, independent: false }),
      attempt({ hint_level_used: 2, independent: false }),
    ]);
    expect(lb.visualRate).toBe(100);
    expect(lb.plainRate).toBe(75);
    expect(lb.commonHintLevel).toBe(1);
    expect(lb.independentPct).toBe(20);
  });
});

describe('misconceptions and next steps on the sample', () => {
  const d = sampleChildData(TODAY);

  it('ranks mistakes by count and drops ones that never happened', () => {
    const all = d.sessions.flatMap((s) => s.attempts);
    const m = misconceptionCounts(d, all);
    expect(m.length).toBeGreaterThan(0);
    for (let i = 1; i < m.length; i++) expect(m[i - 1].count).toBeGreaterThanOrEqual(m[i].count);
    expect(m.every((x) => x.count > 0)).toBe(true);
  });

  it('puts the open topic first and the next topic last', () => {
    const s = nextSteps(d);
    expect(s[0].topicId).toBe('ALG-ORI-02');
    expect(s[s.length - 1].title).toMatch(/^Coming up/);
  });

  it('is the same every time for the same day', () => {
    expect(sampleChildData(TODAY)).toEqual(sampleChildData(TODAY));
  });
});

describe('formatting', () => {
  it('formats durations', () => {
    expect(formatDuration(42)).toBe('42s');
    expect(formatDuration(84)).toBe('1m 24s');
    expect(formatDuration(3660)).toBe('1h 1m');
  });

  it('a mastered topic is 100%', () => {
    expect(topicPercent(sampleChildData(TODAY).topics[0])).toBe(100);
  });
});

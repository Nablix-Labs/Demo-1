/**
 * The Learning Summary, and the sections it must NOT render.
 *
 * §7.6C makes the engine return null rather than assert a pattern from one
 * occurrence; §8.9 then says hide the section. Printing the heading anyway puts
 * the claim back on the page that the engine deliberately declined to make.
 */

import { describe, expect, it } from 'vitest';
import { insightSections, keyTakeaways, humanLabel } from '@/lib/phase4Insights';
import type { Phase4Review, Phase4StudentInsights } from '@/lib/api';

function insights(over: Partial<Phase4StudentInsights> = {}): Phase4StudentInsights {
  return {
    strength_summary: 'You kept the fixed operation across several questions.',
    development_summary: 'Choosing the operation from words like "falls".',
    learning_pattern_summary: null,
    recent_improvement_summary: null,
    next_practice_focus: 'Check whether the quantity increases or decreases first.',
    personalised_notes: ['note one', 'note two', 'note three'],
    ...over,
  };
}

function review(over: Partial<Phase4Review> = {}): Phase4Review {
  return {
    student_id: 'ST003',
    topic_id: 'ALG-KS3-01',
    topic_title: 'What Is Algebra?',
    topic_outcome: { mastery_status: 'MASTERED', recommended_next_action: 'START_NEXT_TOPIC' },
    question_journey: [],
    tutor_replays: [],
    student_insights: insights(),
    ...over,
  };
}

describe('which sections the summary shows', () => {
  it('always shows strength, development and next practice', () => {
    // §7.9 "One next-practice focus only" — these three are never nullable.
    expect(insightSections(insights()).map((s) => s.key))
      .toEqual(['strength', 'development', 'next']);
  });

  it('hides "Pattern to watch" when the evidence was one isolated occurrence', () => {
    // §7.6C: "one isolated occurrence → null". §8.9: "Hide the section if null."
    expect(insightSections(insights({ learning_pattern_summary: null })).map((s) => s.key))
      .not.toContain('pattern');
  });

  it('shows "Pattern to watch" when the evidence genuinely repeats', () => {
    const sections = insightSections(insights({
      learning_pattern_summary: 'You used n x 4 in three different questions.',
    }));
    expect(sections.find((s) => s.key === 'pattern')?.body)
      .toBe('You used n x 4 in three different questions.');
  });

  it('hides "How you improved" when the student never repaired anything', () => {
    expect(insightSections(insights({ recent_improvement_summary: null })).map((s) => s.key))
      .not.toContain('improvement');
  });

  it('treats a whitespace-only field as absent', () => {
    // "No meaningful improvement statement exists" (§8.9) arrives as null or as
    // an empty string depending on who assembled the payload; a heading over a
    // blank box is the same failure either way.
    expect(insightSections(insights({ recent_improvement_summary: '   ' })).map((s) => s.key))
      .not.toContain('improvement');
  });

  it('keeps the spec order when every section is present', () => {
    const sections = insightSections(insights({
      learning_pattern_summary: 'p',
      recent_improvement_summary: 'i',
    }));
    expect(sections.map((s) => s.key))
      .toEqual(['strength', 'development', 'pattern', 'improvement', 'next']);
  });

  it('titles sections in the student\'s words, not the field names', () => {
    const titles = insightSections(insights()).map((s) => s.title);
    expect(titles).toEqual(['What you did well', 'What to work on', 'Next practice']);
    expect(titles.join(' ')).not.toContain('_');
  });
});

describe('key takeaways', () => {
  it('renders key_takeaways when the backend sends that name', () => {
    expect(keyTakeaways(review({ key_takeaways: ['takeaway one', 'takeaway two'] })))
      .toEqual(['takeaway one', 'takeaway two']);
  });

  it('falls back to personalised_notes, which is the engine\'s own name for it', () => {
    // §7.8 emits personalised_notes, §5.8 stores key_takeaways_json, §8.9 renders
    // key_takeaways[]. Accepting either costs a line and avoids an empty section
    // if the name changes during Chiru's merge.
    expect(keyTakeaways(review({ key_takeaways: undefined })))
      .toEqual(['note one', 'note two', 'note three']);
  });

  it('falls back when key_takeaways arrives empty rather than absent', () => {
    expect(keyTakeaways(review({ key_takeaways: [] }))).toHaveLength(3);
  });

  it('drops blank notes instead of rendering empty bullets', () => {
    expect(keyTakeaways(review({ key_takeaways: ['real', '  ', ''] }))).toEqual(['real']);
  });
});

describe('showing a backend enum to a student', () => {
  it('reads the status as words', () => {
    expect(humanLabel('MASTERED')).toBe('Mastered');
    expect(humanLabel('NEARLY_MASTERED')).toBe('Nearly mastered');
    expect(humanLabel('START_NEXT_TOPIC')).toBe('Start next topic');
  });

  it('passes through a value nobody anticipated rather than blanking it', () => {
    // The rule that has to survive Sanya renaming an enum mid-sprint: an
    // unmapped value still comes out readable instead of empty.
    expect(humanLabel('SOME_BRAND_NEW_STATUS')).toBe('Some brand new status');
  });

  it('leaves prose alone', () => {
    // If the backend starts sending a sentence, that sentence is already what
    // we want on screen — title-casing it would mangle it.
    expect(humanLabel('Ready for the next topic')).toBe('Ready for the next topic');
  });

  it('returns nothing for an empty value', () => {
    expect(humanLabel('   ')).toBe('');
  });
});

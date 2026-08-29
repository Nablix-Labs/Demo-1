/**
 * Knowing that independent practice is OVER, as opposed to one attempt.
 *
 * Manjusha, 29 Aug: "It doesn't take me to review page automatically when the
 * inde practice is completed, so I have to click on review with tutor and that
 * gives me this question then it takes to review page."
 *
 * The trap these guard is that a WRONG last attempt closes exactly like a right
 * one — same terminal outcome, same lock — and is then answered with a fresh
 * question (FRESH_INDEPENDENT_QUESTION_REQUESTED, interaction_service.py:792).
 * So "the attempt closed" can never mean "practice is done", and acting on it
 * alone would end a session the student is still working in.
 */

import { describe, expect, it } from 'vitest';
import { reviewIsNext, servedNextQuestion } from '@/lib/phase3';

describe('reviewIsNext', () => {
  it('is true when the backend recommends REVIEW', () => {
    expect(reviewIsNext({ recommended_entry_phase: 'REVIEW' })).toBe(true);
  });

  it('is false while the student still belongs in practice', () => {
    expect(reviewIsNext({ recommended_entry_phase: 'INDEPENDENT_PRACTICE' })).toBe(false);
  });

  it('is false when the backend said nothing', () => {
    // Degrade quiet: a build that omits the field leaves the student on the
    // manual "Review with tutor" button rather than ending their session.
    expect(reviewIsNext({})).toBe(false);
    expect(reviewIsNext({ recommended_entry_phase: null })).toBe(false);
    expect(reviewIsNext(null)).toBe(false);
  });

  it('is not fooled by casing or padding', () => {
    expect(reviewIsNext({ recommended_entry_phase: ' review ' })).toBe(true);
  });
});

describe('servedNextQuestion', () => {
  it('is true when the reply hands over a different question', () => {
    // The fresh-question case. The attempt closed AND there is more to do.
    expect(servedNextQuestion({ question_id: 'Q-T01-007' }, 'Q-T01-005')).toBe(true);
  });

  it('is false when the reply names the question just answered', () => {
    expect(servedNextQuestion({ question_id: 'Q-T01-005' }, 'Q-T01-005')).toBe(false);
  });

  it('is false when the reply names no question at all', () => {
    // Absence is not a new question. Treating it as one would keep the student
    // on a locked canvas forever.
    expect(servedNextQuestion({}, 'Q-T01-005')).toBe(false);
    expect(servedNextQuestion({ question_id: null }, 'Q-T01-005')).toBe(false);
  });
});

describe('the two together', () => {
  const closingReply = (over: Record<string, unknown> = {}) => ({
    independent_outcome: 'INDEPENDENTLY_VERIFIED',
    question_id: 'Q-T01-005',
    recommended_entry_phase: 'REVIEW',
    ...over,
  });

  it('sends the student to review on the last question', () => {
    const res = closingReply();
    expect(reviewIsNext(res) && !servedNextQuestion(res, 'Q-T01-005')).toBe(true);
  });

  it('does NOT send them to review when a fresh question came with it', () => {
    // This is the one that must not fire: REVIEW is recommended for the topic
    // overall while a rescue question is on its way to the screen.
    const res = closingReply({ question_id: 'Q-T01-007' });
    expect(reviewIsNext(res) && !servedNextQuestion(res, 'Q-T01-005')).toBe(false);
  });
});

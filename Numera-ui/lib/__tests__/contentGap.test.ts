import { describe, it, expect } from 'vitest';
import {
  isContentGapError,
  contentGapPaused,
  prerequisiteRemediationPaused,
  lessonPaused,
} from '@/lib/contentGap';
import type { SessionRecord } from '@/lib/api';

const err = (status: number, error_code: string) => ({
  response: { status, data: { error_code, message: '' } },
});

/**
 * A content gap means the authored question does not exist.
 *
 * It is not mastery, not an intervention, and not a transient error — and it
 * has been mistaken for all three. The ST017 run asked for a fresh question
 * twice (journey versions 12 then 13) because nothing here said "stop asking".
 */
describe('isContentGapError', () => {
  it('recognises the refusal of a submission into a gap', () => {
    // The backend raises {"code": "CONTENT_GAP"}, which the app's exception
    // handler lifts into error_code before it reaches us.
    expect(isContentGapError(err(409, 'CONTENT_GAP'))).toBe(true);
  });

  it('is not an intervention pause', () => {
    // That one expects learner input and has its own screen.
    expect(isContentGapError(err(409, 'INTERVENTION_REQUIRED'))).toBe(false);
  });

  it('is not a journey conflict', () => {
    expect(isContentGapError(err(409, 'JOURNEY_VERSION_CONFLICT'))).toBe(false);
  });

  it('is not the same code on another status', () => {
    expect(isContentGapError(err(500, 'CONTENT_GAP'))).toBe(false);
  });

  it('is false when nothing arrived', () => {
    expect(isContentGapError(new Error('Network Error'))).toBe(false);
  });
});

const record = (over: Record<string, unknown> = {}) => ({
  session_id: 'S1',
  concept_id: 'T01',
  question_id: null,
  student_model_event: { routing: { content_gap_detected: true } },
  ...over,
} as unknown as SessionRecord);

/**
 * The gap as a state to render, not an error to catch.
 *
 * GET /session answers 200 with the paused session — the backend persists the
 * pause on the first authoritative gap response specifically so that nothing
 * asks again. Reading it is how the screen knows to stop.
 */
describe('contentGapPaused', () => {
  it('is true when the backend reports a gap and serves no question', () => {
    expect(contentGapPaused(record())).toBe(true);
  });

  it('is false when a question is being served', () => {
    // A gap flag alongside a live question is not a pause — the student has
    // something to answer, and blanking the screen would take it away.
    expect(contentGapPaused(record({ question_id: 'Q-T01-009' }))).toBe(false);
  });

  it('is false when the backend reports no gap', () => {
    expect(contentGapPaused(record({
      student_model_event: { routing: { content_gap_detected: false } },
    }))).toBe(false);
  });

  it('is false when the routing block is missing entirely', () => {
    // Degrade, do not throw. A missing field must never manufacture a pause —
    // that would strand a student whose lesson is fine.
    expect(contentGapPaused(record({ student_model_event: {} }))).toBe(false);
    expect(contentGapPaused(record({ student_model_event: null }))).toBe(false);
  });

  it('is false for an empty record', () => {
    expect(contentGapPaused(undefined)).toBe(false);
  });
});

const remediation = (over: Record<string, unknown> = {}) => ({
  session_id: 'S1',
  concept_id: 'T01',
  question_id: null,
  student_model_event: { routing: { reason_code: 'PREREQUISITE_REMEDIATION_REQUIRED' } },
  ...over,
} as unknown as SessionRecord);

/**
 * A checkpoint that used both Guided repair cycles.
 *
 * Student Model routes it to an earlier topic (TC-31); the return leg (TC-32)
 * does not exist yet, so the backend stops with an explanation. From the
 * screen's side that is the same shape as a gap — no question, nothing to
 * retry — but a different cause, so it is matched on its own reason_code
 * rather than by pretending content_gap_detected is set.
 */
describe('prerequisiteRemediationPaused', () => {
  it('is true when the route resolved and no question is served', () => {
    expect(prerequisiteRemediationPaused(remediation())).toBe(true);
  });

  it('is not a pause while a question is still answerable', () => {
    // Blanking the screen here would take a live question off the student.
    expect(prerequisiteRemediationPaused(remediation({ question_id: 'Q-T01-010' }))).toBe(false);
  });

  it('is not the escalation that precedes it', () => {
    // MAX_GUIDED_REPAIRS_EXHAUSTED is answered by the backend within the same
    // turn; it is never a state the client should render.
    expect(prerequisiteRemediationPaused(remediation({
      student_model_event: { routing: { reason_code: 'MAX_GUIDED_REPAIRS_EXHAUSTED' } },
    }))).toBe(false);
  });

  it('is false on a missing or empty routing block', () => {
    expect(prerequisiteRemediationPaused(remediation({ student_model_event: {} }))).toBe(false);
    expect(prerequisiteRemediationPaused(remediation({ student_model_event: null }))).toBe(false);
    expect(prerequisiteRemediationPaused(undefined)).toBe(false);
  });
});

describe('lessonPaused', () => {
  it('covers both causes', () => {
    expect(lessonPaused(record())).toBe(true);
    expect(lessonPaused(remediation())).toBe(true);
  });

  it('is false for a lesson that still has a question', () => {
    expect(lessonPaused(record({ question_id: 'Q-T01-009' }))).toBe(false);
    expect(lessonPaused(remediation({ question_id: 'Q-T01-010' }))).toBe(false);
  });
});

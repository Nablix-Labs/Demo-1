/**
 * A paused topic 409s every learning route (Chirudeva, 7 Sep). So does a stale
 * turn, a journey-version conflict and a service contract failure — and each
 * means something different to the student, which is why the code and not the
 * status decides.
 */
import { describe, it, expect } from 'vitest';
import { isInterventionPausedError, studentFacingError } from '@/lib/api';

const conflict = (data: Record<string, unknown>) => ({ response: { status: 409, data } });

describe('isInterventionPausedError', () => {
  it('recognises the paused topic', () => {
    expect(isInterventionPausedError(conflict({ error_code: 'INTERVENTION_REQUIRED' }))).toBe(true);
  });

  it('is not every 409', () => {
    expect(isInterventionPausedError(conflict({ error_code: 'JOURNEY_VERSION_CONFLICT' }))).toBe(false);
    expect(isInterventionPausedError(conflict({ message: 'already in progress' }))).toBe(false);
  });

  it('is not a 409-shaped nothing', () => {
    expect(isInterventionPausedError(new Error('offline'))).toBe(false);
    expect(isInterventionPausedError(null)).toBe(false);
  });
});

describe('studentFacingError on a paused topic', () => {
  const copy = studentFacingError(conflict({ error_code: 'INTERVENTION_REQUIRED', message: 'topic paused' }));

  it('does not tell them to ask for a reset — someone is already looking', () => {
    // The generic 409 copy says exactly that, and it was what a paused student
    // used to be shown.
    expect(copy).not.toMatch(/reset/i);
  });

  it('does not describe it as something going wrong', () => {
    expect(copy).not.toMatch(/wrong|problem|error/i);
    expect(copy).toMatch(/teacher/i);
  });
});

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { studentFacingError } from '@/lib/api';

const err = (status: number, message: string, error_code = 'DOWNSTREAM_REQUEST_REJECTED') =>
  ({ response: { status, data: { error_code, message } } });

describe('studentFacingError never shows a diagnostic to a learner', () => {
  it('hides a message carrying adapter URLs and payloads', () => {
    const out = studentFacingError(err(404,
      "student_model rejected request url=https://nablix.ai:8080/session/event status=404 body={\"error_code\":\"UNKNOWN_TOPIC\"} payload={'request_id': 'X', 'student_id': 'ST015'}"));
    expect(out).toBe('The tutor could not process that request.');
    expect(out).not.toMatch(/url=|payload|ST015/);
  });
  it('still passes a plain backend sentence through', () => {
    expect(studentFacingError(err(400, 'That answer needs a number.', 'VALIDATION')))
      .toBe('The tutor could not process that. That answer needs a number.');
  });
});

describe('topic routes refuse a local mock topic id in live mode', () => {
  for (const f of ['app/topic-diagnostic/DiagnosticClient.tsx', 'app/orientation/OrientationClient.tsx']) {
    it(`${f} sends the student to the lesson instead`, () => {
      const src = readFileSync(join(process.cwd(), f), 'utf8');
      expect(src).toMatch(/if \(topicById\(topicId\)\) \{ router\.replace\('\/'\); return; \}/);
    });
  }
});

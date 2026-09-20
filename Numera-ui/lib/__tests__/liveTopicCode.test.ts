import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { liveTopicCode } from '@/lib/topics';

describe('liveTopicCode', () => {
  it('passes a backend topic code through', () => {
    expect(liveTopicCode('ALG-ORI-03')).toBe('ALG-ORI-03');
  });
  it('never sends a local mock id (the Student Model rejects it as UNKNOWN_TOPIC)', () => {
    expect(liveTopicCode('algebra')).toBeUndefined();
    expect(liveTopicCode('number')).toBeUndefined();
  });
  it('sends nothing for an empty id, so the backend chooses', () => {
    expect(liveTopicCode('')).toBeUndefined();
    expect(liveTopicCode(null)).toBeUndefined();
  });
  it('is what the Lesson and Practice tabs start with', () => {
    const lesson = readFileSync(join(process.cwd(), 'app/page.tsx'), 'utf8');
    const practice = readFileSync(join(process.cwd(), 'app/practice/page.tsx'), 'utf8');
    expect(lesson).toMatch(/startSession\(activeConceptId, 'VOICE', liveTopicCode\(currentTopicId\)\)/);
    expect(practice).toMatch(/tutor\.start\(DEMO_CONCEPT_ID, 'TEXT', liveTopicCode\(currentTopicId\)\)/);
  });
});

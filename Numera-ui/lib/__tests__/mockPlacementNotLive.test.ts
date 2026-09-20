/**
 * The mock placement wizard never hands a local topic id to the live flow.
 *
 * /diagnostic is the one-time "quick diagnostic" wizard with a hard-coded
 * placement (algebra / number / geometry). With a backend, those ids reach
 * /session/start as topic_code and the Student Model answers UNKNOWN_TOPIC.
 * Live mode ends the wizard on the student's real lesson instead.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const src = readFileSync(join(process.cwd(), 'app/diagnostic/page.tsx'), 'utf8');

describe('mock placement in live mode', () => {
  it('routes to the lesson rather than placing at a mock topic', () => {
    expect(src).toMatch(/live \? router\.push\('\/'\) : placeAtTopic\(placement\.id\)/);
  });
  it('does not claim a made-up starting topic', () => {
    expect(src).toMatch(/\{!live && \([\s\S]{0,120}We&apos;ll start you at/);
  });
});

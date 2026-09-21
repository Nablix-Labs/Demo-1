/**
 * "Start over" on the completion screen is the MOCK curriculum's restart: it
 * wipes the local journey and opens sign-up. A live student's journey is the
 * backend's, and the button sent a signed-in student to "Create your account"
 * (ST030, 21 Sep 2026). It must be gated on the API being absent.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(join(process.cwd(), 'app/complete/page.tsx'), 'utf8');

describe('Start over on the completion screen', () => {
  it('is offered only without a backend', () => {
    expect(source).toContain("const canStartOver = !process.env.NEXT_PUBLIC_API_BASE_URL;");
    expect(source).toMatch(/\{canStartOver && \([\s\S]*Start over[\s\S]*\)\}/);
  });

  it('keeps Browse topics for everyone', () => {
    expect(source).toContain("router.push('/workbook')");
  });
});

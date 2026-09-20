/**
 * The Help page's contact cards do something.
 *
 * 21 Sep 2026: "Chat with support", "Email us" and "Browse guides" were
 * <button>s with no handler. A student asking for help got a click that did
 * nothing, on the one screen whose job is to get them help.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const src = readFileSync(join(process.cwd(), 'app/help/page.tsx'), 'utf8');

describe('help contacts', () => {
  it('open Nablix Assist for chat', () => {
    expect(src).toMatch(/action === 'chat'\) \{ openSupport\(\)/);
  });
  it('open a mail draft for email', () => {
    expect(src).toMatch(/mailto:support@nablix\.com/);
  });
  it('wire every card to the action', () => {
    expect(src).toMatch(/onClick=\{\(\) => act\(c\.action\)\}/);
  });
});

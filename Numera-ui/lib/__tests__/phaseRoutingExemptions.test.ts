/**
 * Which routes the backend's phase is allowed to move.
 *
 * The fixture screens under /dev-screens seed the store — support-deck writes a
 * GUIDED_PRACTICE phase because the deck is hidden in Phase 3 — and the routing
 * hook used to read that seed as a real phase and push the page away. The bug
 * was invisible locally: the hook no-ops without an API base URL, so it only
 * appeared on a deployed build.
 */

import { describe, expect, it } from 'vitest';
import { followsBackendPhase, flowScreen } from '@/lib/usePhaseRouting';

describe('routes the backend phase may move', () => {
  it('moves the ordinary flow screens', () => {
    for (const path of ['/', '/practice', '/review', '/diagnostic/statistics', '/orientation/statistics']) {
      expect(followsBackendPhase(path), path).toBe(true);
    }
  });

  it('leaves every fixture screen where it is', () => {
    for (const path of [
      '/dev-screens',
      '/dev-screens/support-deck',
      '/dev-screens/phase4',
      '/dev-screens/intervention',
      '/dev-screens/anchors',
    ]) {
      expect(followsBackendPhase(path), path).toBe(false);
    }
  });

  it('does not exempt a real route that merely starts with the same letters', () => {
    // Prefix matching on '/dev-screens' alone would also catch this.
    expect(followsBackendPhase('/dev-screenshots')).toBe(true);
  });
});

describe('which screens the phase may pull a student off', () => {
  it('corrects a student on the wrong flow screen', () => {
    for (const path of ['/', '/practice', '/review', '/topic-diagnostic', '/orientation', '/teach', '/diagnostic', '/orientation/statistics']) {
      expect(flowScreen(path), path).toBe(true);
    }
  });

  it('leaves the dock pages alone during a lesson', () => {
    // ST030, 21 Sep: every dock link bounced back to the lesson before it painted.
    for (const path of ['/workbook', '/help', '/profile', '/history', '/keynotes', '/files', '/flagged', '/notifications', '/people', '/challenge', '/complete', '/login']) {
      expect(flowScreen(path), path).toBe(false);
    }
  });
});

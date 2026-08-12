import { describe, it, expect } from 'vitest';
import {
  availableSupport,
  nextSupport,
  SUPPORT_ORDER,
  hintFailureMessage,
  LADDER_EXHAUSTED,
  HINT_UNAVAILABLE,
} from '@/lib/supportLadder';

describe('availableSupport', () => {
  it('is empty when the turn authorised nothing', () => {
    expect(availableSupport({})).toEqual([]);
  });

  it('reads a hint off the turn message', () => {
    expect(availableSupport({ hintText: 'Is it addition or multiplication?' })).toEqual(['HINT']);
  });

  it('ignores an empty hint string', () => {
    expect(availableSupport({ hintText: '' })).toEqual([]);
  });

  it('offers the scaffold only when a step actually arrived', () => {
    // show_scaffold_panel true with no step would open an empty panel, which
    // reads as the tutor breaking rather than the tutor withholding.
    expect(availableSupport({ showScaffoldPanel: true, hasScaffoldStep: false })).toEqual([]);
    expect(availableSupport({ showScaffoldPanel: true, hasScaffoldStep: true })).toEqual(['SCAFFOLD']);
  });

  it('returns rungs in ladder order regardless of field order', () => {
    expect(
      availableSupport({
        showScaffoldPanel: true,
        hasScaffoldStep: true,
        hintText: 'a hint',
        showVisualCue: true,
      }),
    ).toEqual(['HINT', 'VISUAL_CUE', 'SCAFFOLD']);
  });

  it('never offers rungs the backend has no field for', () => {
    const all = availableSupport({
      hintText: 'h',
      showVisualCue: true,
      showScaffoldPanel: true,
      hasScaffoldStep: true,
    });
    expect(all).not.toContain('PARALLEL_EXAMPLE');
    expect(all).not.toContain('TUTOR_SOLVED');
  });
});

describe('nextSupport', () => {
  const available = ['HINT', 'VISUAL_CUE', 'SCAFFOLD'] as const;

  it('starts at the lowest available rung', () => {
    expect(nextSupport(null, [...available])).toBe('HINT');
  });

  it('climbs one rung at a time', () => {
    expect(nextSupport('HINT', [...available])).toBe('VISUAL_CUE');
    expect(nextSupport('VISUAL_CUE', [...available])).toBe('SCAFFOLD');
  });

  it('returns null once the ladder is exhausted', () => {
    expect(nextSupport('SCAFFOLD', [...available])).toBeNull();
  });

  it('skips rungs the backend did not authorise', () => {
    expect(nextSupport(null, ['SCAFFOLD'])).toBe('SCAFFOLD');
    expect(nextSupport('HINT', ['SCAFFOLD'])).toBe('SCAFFOLD');
  });

  it('never walks back down', () => {
    // A student who has seen the scaffold is not returned to the hint just
    // because a later turn re-authorised one.
    expect(nextSupport('SCAFFOLD', ['HINT', 'VISUAL_CUE'])).toBeNull();
  });

  it('is null when nothing is available at all', () => {
    expect(nextSupport(null, [])).toBeNull();
  });

  it('keeps the spec ladder order', () => {
    expect(SUPPORT_ORDER).toEqual([
      'HINT',
      'VISUAL_CUE',
      'SCAFFOLD',
      'PARALLEL_EXAMPLE',
      'TUTOR_SOLVED',
    ]);
  });
});

/**
 * A hint request that FAILS must still resolve the card.
 *
 * On 11 Aug 2026 the backend rewrote HELP_REQUEST to replay only support it had
 * already authorised, answering 409 NO_ACTIVE_SUPPORT otherwise. That 409 is not
 * STALE_TURN, so sendInteraction rethrows it, and the hint card — which had no
 * catch — was left blank indefinitely. A blank card is the single worst outcome
 * here: it is indistinguishable from a frozen app, so the student waits instead
 * of doing the one thing that unblocks them.
 */
describe('hintFailureMessage', () => {
  const err = (status: number, detail?: string) => ({ response: { status, data: { detail } } });

  it('reads an empty ladder as an empty ladder, not an outage', () => {
    expect(hintFailureMessage(err(409, 'NO_ACTIVE_SUPPORT: this session has no support to replay.')))
      .toBe(LADDER_EXHAUSTED);
  });

  it('does not claim the ladder is empty when the server actually broke', () => {
    for (const status of [400, 401, 403, 404, 422, 500, 502, 504]) {
      expect(hintFailureMessage(err(status))).toBe(HINT_UNAVAILABLE);
    }
  });

  it('does not mistake an unrelated 409 for an empty ladder', () => {
    // Turn-ordering conflicts also arrive as 409 and mean "retry", not "no more help".
    expect(hintFailureMessage(err(409, 'STALE_TURN'))).toBe(HINT_UNAVAILABLE);
    expect(hintFailureMessage(err(409))).toBe(HINT_UNAVAILABLE);
  });

  it('always returns something to show, whatever was thrown', () => {
    // A dropped connection has no response at all. The card must never stay blank.
    for (const thrown of [new Error('Network Error'), undefined, null, 'boom', {}]) {
      expect(hintFailureMessage(thrown)).toBeTruthy();
    }
  });
});

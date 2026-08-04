import { describe, it, expect } from 'vitest';
import {
  shouldApply,
  noteApplied,
  scaffoldVisible,
  servedNewSupportThisTurn,
  EMPTY_APPLIED,
} from '@/lib/responseGate';

describe('version ordering (handoff item 2)', () => {
  it('applies the first response it ever sees', () => {
    expect(shouldApply({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED)).toBe(true);
  });

  it('applies a newer version', () => {
    const applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    expect(shouldApply({ interaction_state_version: 8, accepted_turn_id: 'b' }, applied)).toBe(true);
  });

  it('rejects an older version arriving late', () => {
    // The case the version exists for: out-of-order delivery silently
    // overwriting newer state with older state.
    const applied = noteApplied({ interaction_state_version: 8, accepted_turn_id: 'b' }, EMPTY_APPLIED);
    expect(shouldApply({ interaction_state_version: 7, accepted_turn_id: 'a' }, applied)).toBe(false);
  });

  it('applies an equal-version replay once', () => {
    // A retried Explain Again returns the same wording AND the same version.
    const applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    expect(shouldApply({ interaction_state_version: 7, accepted_turn_id: 'b' }, applied)).toBe(true);
  });

  it('does not apply the same equal-version turn twice', () => {
    const applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    expect(shouldApply({ interaction_state_version: 7, accepted_turn_id: 'a' }, applied)).toBe(false);
  });

  it('rejects an equal-version response with no turn id', () => {
    // Nothing identifies it, so it cannot be shown to be a distinct replay.
    const applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    expect(shouldApply({ interaction_state_version: 7 }, applied)).toBe(false);
  });

  it('still works against a backend that does not send the field yet', () => {
    // Refusing everything until the contract ships would freeze the UI.
    expect(shouldApply({}, EMPTY_APPLIED)).toBe(true);
    expect(shouldApply({ interaction_state_version: null }, EMPTY_APPLIED)).toBe(true);
  });

  it('drops stale turn ids when the version advances', () => {
    let applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    applied = noteApplied({ interaction_state_version: 8, accepted_turn_id: 'b' }, applied);
    expect(applied.appliedTurnIds.has('a')).toBe(false);
    expect(applied.appliedTurnIds.has('b')).toBe(true);
  });

  it('accumulates turn ids within one version', () => {
    let applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, EMPTY_APPLIED);
    applied = noteApplied({ interaction_state_version: 7, accepted_turn_id: 'b' }, applied);
    expect(applied.appliedTurnIds.has('a')).toBe(true);
    expect(applied.appliedTurnIds.has('b')).toBe(true);
  });

  it('an older response never rewrites what was applied', () => {
    const applied = noteApplied({ interaction_state_version: 8, accepted_turn_id: 'b' }, EMPTY_APPLIED);
    expect(noteApplied({ interaction_state_version: 7, accepted_turn_id: 'a' }, applied)).toEqual(applied);
  });
});

describe('scaffold visibility comes from persisted state (handoff item 3)', () => {
  it('is visible whenever a scaffold is open', () => {
    expect(scaffoldVisible({ active_scaffold: { scaffold_id: 'SCF-1' } })).toBe(true);
  });

  it('is hidden when no scaffold is open', () => {
    expect(scaffoldVisible({ active_scaffold: null })).toBe(false);
  });

  it('stays open on a turn that served no new support', () => {
    // The bug this guards: rendering from support_served_this_turn made the
    // panel vanish on the next reply even though the scaffold was still open.
    expect(
      scaffoldVisible({ active_scaffold: { scaffold_id: 'SCF-1' } }),
    ).toBe(true);
  });

  it('falls back to the boolean the backend sends today', () => {
    expect(scaffoldVisible({ show_scaffold_panel: true })).toBe(true);
    expect(scaffoldVisible({ show_scaffold_panel: false })).toBe(false);
  });
});

describe('one-time support effects (handoff item 4)', () => {
  it('fires when support was newly served', () => {
    expect(servedNewSupportThisTurn({ support_served_this_turn: { level: 'HINT' } })).toBe(true);
  });

  it('does not fire when nothing new was served', () => {
    expect(servedNewSupportThisTurn({ support_served_this_turn: null })).toBe(false);
    expect(servedNewSupportThisTurn({})).toBe(false);
  });
});

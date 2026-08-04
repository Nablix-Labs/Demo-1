/**
 * Which interaction responses get applied to the UI.
 *
 * From the Guided Practice Phase 2 handoff (Manav — Frontend, "Response
 * application and rendering", items 2–5).
 *
 * The backend now stamps every newly accepted response with a monotonically
 * increasing `interaction_state_version`, including non-pedagogical ones
 * (Explain Again, nudge delivery) where the pedagogical state has not moved.
 * That is what makes ordering deterministic: without it, two responses that
 * leave guided state identical are indistinguishable, and a late-arriving older
 * one silently overwrites a newer one.
 *
 * Cached replays keep their ORIGINAL version — a retried Explain Again returns
 * the same wording and the same version it had the first time. So equal-version
 * is not automatically stale: it is a replay, and it should be applied exactly
 * once per accepted turn.
 */

export interface VersionedResponse {
  interaction_state_version?: number | null;
  accepted_turn_id?: string | null;
}

/** What the client remembers about what it has already rendered. */
export interface AppliedState {
  version: number | null;
  /** accepted_turn_ids already applied at the current version. */
  appliedTurnIds: ReadonlySet<string>;
}

export const EMPTY_APPLIED: AppliedState = { version: null, appliedTurnIds: new Set() };

/**
 * Should this response be applied?
 *
 * Newer version → yes. Equal version → only if this accepted_turn_id has not
 * already been applied (the cached-replay case). Older → never.
 *
 * A response with no version at all is applied: the field does not exist on the
 * backend yet, and refusing everything until it ships would freeze the UI.
 * Once it ships, ordering becomes exact.
 */
export function shouldApply(response: VersionedResponse, applied: AppliedState): boolean {
  const version = response.interaction_state_version;
  if (version === undefined || version === null) return true; // pre-contract backend

  if (applied.version === null) return true;
  if (version > applied.version) return true;
  if (version < applied.version) return false;

  // Equal version — either a cached replay, or a turn that did not advance
  // pedagogical state (the backend only increments on mutating turns, and
  // `accepted_turn_id` is nullable).
  //
  // With a turn id we can tell those apart: apply once per accepted turn.
  // Without one there is nothing to match on, so we cannot PROVE it is a
  // replay — and this fails open deliberately. Rejecting an unidentifiable
  // response means a student sends an answer and the UI never updates, with no
  // error and no way out. Applying a duplicate is visible and recoverable;
  // freezing the lesson is neither.
  const turnId = response.accepted_turn_id;
  if (!turnId) return true;
  return !applied.appliedTurnIds.has(turnId);
}

/** Record that a response was applied. */
export function noteApplied(
  response: VersionedResponse,
  applied: AppliedState,
): AppliedState {
  const version = response.interaction_state_version;
  if (version === undefined || version === null) return applied;

  const turnId = response.accepted_turn_id ?? null;

  // A newer version starts a fresh set — turn ids from an older version can
  // never be replayed against it, so keeping them would only leak memory.
  if (applied.version === null || version > applied.version) {
    return { version, appliedTurnIds: new Set(turnId ? [turnId] : []) };
  }
  if (version < applied.version) return applied;

  const next = new Set(applied.appliedTurnIds);
  if (turnId) next.add(turnId);
  return { version, appliedTurnIds: next };
}

/**
 * Whether the scaffold panel should be visible.
 *
 * Item 3 of the handoff, and the distinction is the whole point:
 *
 *   `active_scaffold`          persisted state — what IS open
 *   `support_served_this_turn` an event — what was newly served on THIS turn
 *
 * Rendering visibility from the event is the bug the handoff is guarding
 * against: the panel would appear on the turn the scaffold was served and then
 * vanish on the next reply, because that reply served nothing new even though
 * the scaffold is still open. Visibility follows persisted state; the event is
 * only ever used for one-time presentation effects (item 4).
 */
export function scaffoldVisible(response: {
  active_scaffold?: unknown | null;
  show_scaffold_panel?: boolean;
}): boolean {
  if (response.active_scaffold !== undefined)
    return response.active_scaffold !== null;
  // Pre-contract backend: fall back to the boolean it does send today.
  return Boolean(response.show_scaffold_panel);
}

/**
 * Should this turn play a one-time support effect (chime, highlight, focus)?
 *
 * Only when support was NEWLY served. An Explain Again or a nudge that returns
 * the same still-open scaffold must not re-announce it.
 */
export function servedNewSupportThisTurn(response: {
  support_served_this_turn?: unknown | null;
}): boolean {
  return (
    response.support_served_this_turn !== undefined &&
    response.support_served_this_turn !== null
  );
}

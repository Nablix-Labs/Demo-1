/**
 * The support deck — one answer to "what support is on screen".
 *
 * Before this, nothing owned that question. SupportLane enforced one rule (a
 * rescue takes the lane), the store enforced two more in two different reducers
 * (a cue clears the hint; a rescue step clears the rungs above it), the canvas
 * enforced a fourth for the scaffold, and rescueMode a fifth between the two
 * rescue implementations. None of them consulted each other, and the gaps
 * between them are the clutter: the write instruction, the hint and the cue had
 * no mutual exclusion at all, so all three could stand at once. With a worked
 * example beside them the lane measured 918px in a 900px window and the bottom
 * card's controls sat below the fold (SupportLane, 18 Aug).
 *
 * `lib/rescueMode.ts` already proved the cure for rescue alone. This is the
 * same move for the whole ladder, and Manjusha's 5 Sep ask is its shape: show
 * only the latest, keep the rest one click away.
 *
 * ── Two tiers, because two different things are being shown ────────────────
 *
 * INSTRUCTIONS are what the student must do NOW — the guided step and the write
 * instruction. They are never collapsed and are not in this module. SupportLane
 * already had the argument for the write note: "above the ladder, not part of
 * it […] Below a hint it would read as the least urgent thing on screen when it
 * is the only one that unblocks them." The guided step is the same kind of
 * object, and Manjusha's own list leaves scaffolding out of the stack.
 *
 * OFFERS are help that has been made available — hint, cue, parallel example,
 * tutor-solved. Those are the deck: one visible, the rest as chips.
 *
 * ── The deck indexes rungs; it never holds their content ───────────────────
 *
 * Content stays exactly where it already lives (`visibleHint`, `visualCue*`,
 * `guidedRescue`, `rescueSteps`). Copying it here would create a second thing
 * to keep in step and a fresh way for a cleared rung to linger.
 *
 * So ORDER is stored and MEMBERSHIP is derived. `supportDeck` remembers the
 * sequence rungs arrived in; `deckRungs` filters that against what is actually
 * live. A rung the backend clears drops out on the next read, with nothing
 * having to remember to remove it — which is the failure mode a parallel copy
 * would have introduced.
 */

import { isPhase3 } from '@/lib/phase3';
import { rescueActive, legacyRescueVisible, type RescueModeState } from '@/lib/rescueMode';

/**
 * The tier-2 rungs: `SUPPORT_ORDER` without `SCAFFOLD`.
 *
 * Not derived from `SUPPORT_ORDER` by subtraction, because the two lists mean
 * different things — that one is the order the backend escalates through, this
 * one is what may be collapsed behind a chip — and a scaffold must never end up
 * in the deck because someone edited the other list.
 */
export type DeckRung = 'HINT' | 'VISUAL_CUE' | 'PARALLEL_EXAMPLE' | 'TUTOR_SOLVED';

/** Ladder rank, used only to break ties between rungs that arrive together. */
const RANK: Record<DeckRung, number> = {
  HINT: 0,
  VISUAL_CUE: 1,
  PARALLEL_EXAMPLE: 2,
  TUTOR_SOLVED: 3,
};

/** What the student sees on a chip. Short — these sit in a row. */
const LABEL: Record<DeckRung, string> = {
  HINT: 'Hint',
  VISUAL_CUE: 'Visual cue',
  PARALLEL_EXAMPLE: 'A similar one',
  TUTOR_SOLVED: 'Let me show you',
};

export function rungLabel(rung: DeckRung): string {
  return LABEL[rung];
}

/**
 * The store fields the deck is derived from.
 *
 * Structural rather than the store type, matching `RescueModeState` — so the
 * rules are testable on plain objects, and so a call site cannot quietly widen
 * what the deck depends on.
 */
export interface DeckState extends RescueModeState {
  visibleHint: string | null;
  visualCueVisible: boolean;
  visualCueDescription: string | null;
  visualCueAssetUrl: string | null;
  visualCueId: string | null;
  /** Arrival order. May name rungs whose content has since gone. */
  supportDeck: readonly DeckRung[];
  /** Which chip the student opened. Null means "show the latest". */
  openedRung: DeckRung | null;
  /**
   * The student put the card away.
   *
   * The X used to delete the rung's content, which is why a dismissed hint
   * could never be read again. Now it only closes the card: the strip keeps the
   * chip and one click brings it back.
   */
  deckCollapsed: boolean;
}

/**
 * Which rung the rescue payloads currently represent, if any.
 *
 * Both implementations are the SAME rung as far as the deck is concerned — the
 * student was offered one worked example, not two — so this collapses them and
 * lets `rescueMode` keep deciding which component renders it. That precedence
 * is load-bearing and deliberately not re-litigated here: the legacy payload
 * carries every step including the answer, so putting it on screen beside a
 * stepwise walkthrough hands over the answer the walkthrough is releasing a
 * step at a time.
 */
function rescueRung(state: DeckState): DeckRung | null {
  if (rescueActive(state)) {
    const step = state.rescueSteps[state.rescueSteps.length - 1];
    if (!step) return null;
    return step.mode === 'PARALLEL' ? 'PARALLEL_EXAMPLE' : 'TUTOR_SOLVED';
  }
  if (legacyRescueVisible(state) && state.guidedRescue) {
    return state.guidedRescue.rescue_type === 'PARALLEL_EXAMPLE' ? 'PARALLEL_EXAMPLE' : 'TUTOR_SOLVED';
  }
  return null;
}

/**
 * Does this rung have something to show right now?
 *
 * The cue's test matches VisualCue's own: visible AND with either a description
 * or an image, because a cue with neither renders nothing and a chip leading to
 * an empty card is worse than no chip.
 */
function isLive(rung: DeckRung, state: DeckState): boolean {
  switch (rung) {
    case 'HINT':
      return Boolean(state.visibleHint);
    case 'VISUAL_CUE':
      return state.visualCueVisible
        && Boolean(state.visualCueDescription || state.visualCueAssetUrl || state.visualCueId);
    case 'PARALLEL_EXAMPLE':
    case 'TUTOR_SOLVED':
      return rescueRung(state) === rung;
  }
}

/**
 * The rungs currently held, oldest first.
 *
 * Phase 3 is answered alone (spec §3.2), so the deck is empty there whatever
 * arrived — agreeing with the render-time gates in each component rather than
 * trusting that one of them ran first.
 *
 * A live rung missing from `supportDeck` is kept rather than dropped — content
 * can be set by a path that did not record the arrival, and dropping it would
 * hide support that is genuinely on screen.
 *
 * It goes BEFORE the recorded ones, ordered among itself by ladder rank. Its
 * age is unknown, and only a rung we actually watched arrive should be able to
 * claim "latest": appending it instead let a hint of unknown age outrank a
 * walkthrough that had just opened, which is the one thing the deck exists to
 * get right.
 */
export function deckRungs(state: DeckState): DeckRung[] {
  if (isPhase3(state.currentPhase)) return [];
  const ordered = state.supportDeck.filter((rung) => isLive(rung, state));
  const unrecorded = (Object.keys(RANK) as DeckRung[])
    .filter((rung) => isLive(rung, state) && !ordered.includes(rung))
    .sort((a, b) => RANK[a] - RANK[b]);
  return [...unrecorded, ...ordered];
}

/**
 * The one rung to render: the chip the student opened, else the latest.
 *
 * An `openedRung` whose content has gone falls back to the latest rather than
 * rendering nothing — the student asked to see something, and an empty lane is
 * not an answer.
 */
export function visibleRung(state: DeckState): DeckRung | null {
  const rungs = deckRungs(state);
  if (rungs.length === 0) return null;
  // Put away by the student. The chips stay — `collapsedRungs` derives from
  // this, so every held rung falls into the strip with nothing to special-case.
  if (state.deckCollapsed) return null;
  const opened = state.openedRung;
  if (opened && rungs.includes(opened)) return opened;
  return rungs[rungs.length - 1];
}

/** The rest, for the "Earlier help" strip, in the order they were offered. */
export function collapsedRungs(state: DeckState): DeckRung[] {
  const showing = visibleRung(state);
  return deckRungs(state).filter((rung) => rung !== showing);
}

/**
 * Where a newly arrived rung goes in the stored order.
 *
 * Appended, and removed from wherever it was: a rung that arrives again has
 * just been offered, so it is the latest. Keeping the first position would mean
 * a re-sent hint stayed buried behind the cue that superseded it.
 *
 * Pure, so the store reducer stays a one-liner and the rule is tested here.
 */
export function withRung(deck: readonly DeckRung[], rung: DeckRung): DeckRung[] {
  return [...deck.filter((r) => r !== rung), rung];
}

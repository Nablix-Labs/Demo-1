/**
 * Laying out a replay board (PR #257).
 *
 * The elements arrive as a flat list and are rendered in order, but two of them
 * are not independent: a `brace` spans whatever is above it, so it needs to
 * know how many columns that thing had. That lookback is the only real logic on
 * this screen, and it lives here rather than in JSX so it can be tested — the
 * failure it prevents is silent, a brace whose labels drift out of line with
 * the values they belong to.
 */

import type { Phase4BoardElement } from '@/lib/api';

/** How a brace's labels sit under the row above it. */
export type BraceFit =
  /** One label per column, aligned to the values above. */
  | { mode: 'columns'; labels: string[]; columns: number }
  /** A single caption spanning the whole brace. */
  | { mode: 'span'; label: string };

/**
 * Where a brace's labels go.
 *
 * Aligned when there is exactly one label per column — that is the design's
 * "+4  +4  +4" sitting under 2, 5, 8. Anything else spans, because a partial
 * alignment is worse than none: three labels under four values would put each
 * one under the wrong number while looking deliberate.
 *
 * Several labels that cannot align are joined rather than dropped. They were
 * authored and the student should see them; the join is visibly one caption.
 */
export function braceFit(labels: readonly string[], columns: number): BraceFit {
  const kept = labels.map((l) => l.trim()).filter(Boolean);
  if (kept.length === 0) return { mode: 'span', label: '' };
  if (columns > 0 && kept.length === columns) {
    return { mode: 'columns', labels: kept, columns };
  }
  return { mode: 'span', label: kept.join('  ') };
}

/**
 * How many columns the thing a brace sits `over` has.
 *
 * Walks BACK from the brace rather than tracking state forward, because `over`
 * is a claim about what precedes it and the honest way to check a claim is to
 * look. `over: "brace"` resolves through to the value row that brace was itself
 * under, so a stacked pair keeps one column count between them.
 *
 * Zero when there is nothing above to align to — a brace authored first, or one
 * naming a row that is not there. The caller then spans, which is what a brace
 * with nothing to measure against should do.
 */
export function columnsAbove(
  elements: readonly Phase4BoardElement[],
  braceIndex: number,
): number {
  for (let i = braceIndex - 1; i >= 0; i -= 1) {
    const element = elements[i];
    if (element.kind === 'value_row') return element.values.length;
    // Keep walking past a brace: it has no columns of its own, it inherits the
    // row's. Anything else between them breaks the association, because the
    // brace is no longer under the row.
    if (element.kind !== 'brace') return 0;
  }
  return 0;
}

/**
 * Does this replay use structured boards at all?
 *
 * Decided per REPLAY, not per step. Switching between the structured board and
 * the handwriting canvas partway through one explanation would swap the whole
 * centre panel mid-sentence; a replay commits to one surface and stays on it.
 * A step inside a boarded replay that carries no board of its own falls back to
 * its `tutor_write` line within that surface, which is a heading, not a
 * different screen.
 */
export function usesBoards(
  steps: readonly { board?: { elements: unknown[] } | null }[],
): boolean {
  return steps.some((step) => (step.board?.elements?.length ?? 0) > 0);
}

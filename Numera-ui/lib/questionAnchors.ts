/**
 * Pointing at part of the question text (Chirudeva handoff, 18 Aug 2026, §1).
 *
 * The tutor can now say "think about what changes" AND point at the `n` it
 * means. The backend sends a character span into `current_question` and never
 * coordinates — we lay the question out, so the geometry is ours.
 *
 * The one rule that matters: SLICE, NEVER SEARCH. `indexOf(anchor.text)` looks
 * equivalent and is not — "n" and "4" occur many times in an ordinary word
 * problem, so a search highlights the wrong one and does it silently, teaching
 * the student about the wrong symbol. The span is exact and slices back to
 * `text` character for character; that is a backend invariant with tests behind
 * it, and `usableAnchors` checks it here rather than trusting it.
 *
 * The awkward part is that we do not render `current_question` verbatim.
 * `questionLayout` splits a comma-separated run of cases into a grid and gives
 * a bare equation a "Solve for x:" lead-in, so the string on screen is several
 * fragments of the original rather than the whole of it. The offsets are into
 * the original, so each fragment has to know where it came from — see
 * `locateFragment`, which resolves that WITHOUT searching for anchor text.
 */

export interface QuestionAnchor {
  /** Stable for a given question. The de-duplication key. */
  token_id: string;
  /** The token's own text. Used to verify the slice, never to find it. */
  text: string;
  char_start: number;
  char_end: number;
  /** e.g. "changes" / "stays fixed". Null means highlight with no label. */
  label?: string | null;
  /** Set locally after a validated tutor highlight action resolves to this token. */
  highlighted?: boolean;
  /**
   * This anchor's `highlighted`/`label` were written by a resolved tutor
   * action, not sent as part of the question. It is what `mergeQuestionAnchors`
   * keeps across a turn — see the note there.
   */
  confirmed?: boolean;
}

export interface AnchorSegment {
  text: string;
  /** Set when this segment is an anchored span; null for plain text between. */
  anchor: QuestionAnchor | null;
}

/**
 * The anchors that can actually be rendered against this question.
 *
 * Dropped, in order: duplicates by `token_id`, spans outside the string, spans
 * that do not slice back to their own `text`, and anchors that overlap one
 * already kept.
 *
 * A mismatch means the string we rendered differs from `current_question`,
 * which breaks the contract — Chiru asked to be told when it happens. It is
 * reported to the console rather than thrown: a wrong highlight is a teaching
 * error, but refusing to render the question at all over one bad span would
 * turn a cosmetic fault into a blocked lesson.
 */
export function usableAnchors(
  question: string,
  anchors: QuestionAnchor[] | null | undefined,
): QuestionAnchor[] {
  const seen = new Set<string>();
  const kept: QuestionAnchor[] = [];

  const candidates = (anchors ?? [])
    .filter((a) => {
      if (!a || typeof a.token_id !== 'string' || !a.token_id) return false;
      if (seen.has(a.token_id)) return false;
      seen.add(a.token_id);
      return true;
    })
    // Ordered by position so segmentation is a single left-to-right pass and
    // "overlaps one already kept" is well defined.
    .sort((a, b) => a.char_start - b.char_start);

  for (const a of candidates) {
    const { char_start: start, char_end: end } = a;
    if (!Number.isInteger(start) || !Number.isInteger(end)) continue;
    if (start < 0 || end > question.length || end <= start) continue;
    if (question.slice(start, end) !== a.text) {
      console.warn(
        `[anchors] span ${start}-${end} slices to "${question.slice(start, end)}" ` +
        `but the backend called it "${a.text}" — the rendered question differs ` +
        `from current_question. Anchor ${a.token_id} dropped.`,
      );
      continue;
    }
    // Overlapping spans cannot both be rendered as one flat run of segments,
    // and nesting them would highlight the same character twice.
    if (kept.length && start < kept[kept.length - 1].char_end) continue;
    kept.push(a);
  }

  return kept;
}

/**
 * Split `question[from, to)` into ordered segments, anchored and plain.
 *
 * `from`/`to` exist because the renderer draws fragments of the question, not
 * the whole string: an anchor outside the fragment belongs to a different part
 * of the layout and must not appear in this one.
 */
export function anchorSegments(
  question: string,
  anchors: QuestionAnchor[] | null | undefined,
  from = 0,
  to = question.length,
): AnchorSegment[] {
  const within = usableAnchors(question, anchors)
    .filter((a) => a.char_start >= from && a.char_end <= to);

  const segments: AnchorSegment[] = [];
  let cursor = from;
  for (const anchor of within) {
    if (anchor.char_start > cursor) {
      segments.push({ text: question.slice(cursor, anchor.char_start), anchor: null });
    }
    segments.push({ text: question.slice(anchor.char_start, anchor.char_end), anchor });
    cursor = anchor.char_end;
  }
  if (cursor < to) segments.push({ text: question.slice(cursor, to), anchor: null });

  // An empty fragment would render an empty <span>; one plain segment is the
  // shape the caller expects for "nothing to point at".
  return segments.length ? segments : [{ text: question.slice(from, to), anchor: null }];
}

/**
 * Where a rendered fragment sits in the original question.
 *
 * This is NOT the search the header forbids. That rule is about anchor TEXT —
 * looking for "n" finds the wrong "n". Here the needle is a fragment the layout
 * itself derived from this very string, and the fragments are consumed strictly
 * left to right through a moving cursor, so each one resolves to the occurrence
 * that produced it.
 *
 * Returns -1 when the fragment is not found, which happens when the layout
 * rewrote rather than sliced (the "Solve for x:" lead-in is added text, not a
 * fragment of the question). The caller then renders it unanchored.
 */
export function locateFragment(
  question: string,
  fragment: string,
  fromIndex = 0,
): number {
  if (!fragment) return -1;
  return question.indexOf(fragment, fromIndex);
}

export interface FragmentRange {
  /** Offset into the question, or null when the fragment is not a slice of it. */
  from: number | null;
  to: number | null;
}

/**
 * Where each rendered fragment sits in the original question.
 *
 * `questionLayout` hands the renderer pieces rather than the whole string — a
 * grid of cases split out of a comma-separated run, then the instruction after
 * it — and the anchor offsets index the original. This walks the fragments in
 * render order through a single moving cursor, so a fragment that appears more
 * than once ("+ 5", three times in a stack of cases) resolves to the occurrence
 * that produced it rather than all three claiming the first.
 *
 * A fragment the layout invented rather than sliced — the "Solve for x:"
 * lead-in — resolves to null, and the caller renders it with no anchors, which
 * is correct: it is not part of the question the backend measured.
 */
export function fragmentRanges(question: string, fragments: string[]): FragmentRange[] {
  let cursor = 0;
  return fragments.map((fragment) => {
    const at = locateFragment(question, fragment, cursor);
    if (at === -1) return { from: null, to: null };
    cursor = at + fragment.length;
    return { from: at, to: cursor };
  });
}

/**
 * Fold a turn's anchors into what is already on screen (#321).
 *
 * Two different facts ride on this one array, and replacing it wholesale
 * treated them as one:
 *
 *   - What the tutor is POINTING at. That is about this turn. It goes stale
 *     the moment the turn ends, and leaving it up reads as "this is still the
 *     thing to look at" for the rest of the question.
 *   - What the tutor has CONFIRMED — `m → changes`, written onto the token
 *     because the student said so and a HIGHLIGHT/INSERT_LABEL action resolved
 *     onto it. That is about the QUESTION, and the student is still working on
 *     it.
 *
 * So the second survives a turn and the first does not. Before this, a
 * confirmed label lasted exactly one reply: the next turn's base anchors
 * replaced the array and the local state went with it (Sanya, 15 Sep 2026).
 *
 * Geometry is never preserved. `char_start`/`char_end`/`text` always come from
 * `incoming`, because a question can be re-served reworded under the same id
 * and a kept offset would then point at the wrong character — the failure this
 * whole module exists to prevent. Only `highlighted`, `label` and `confirmed`
 * carry over.
 *
 * `previous` must belong to the SAME question. Anchors are raw offsets into one
 * question's text, so the caller clears them on a question change rather than
 * merging across it (`applyBackendPhase`).
 *
 * Note for the backend: the contract asks for confirmed state to clear when an
 * action "explicitly withdraws" it, and `TutorCanvasActionType` has no verb
 * that can say so. Until one exists, a question change is the only thing that
 * clears a confirmation.
 */
export function mergeQuestionAnchors(
  previous: QuestionAnchor[] | null | undefined,
  incoming: QuestionAnchor[] | null | undefined,
): QuestionAnchor[] {
  // Every token already on screen is remembered, not only the confirmed ones.
  // The reply that confirms `m` is the same reply that moves the step on to
  // `+`, so its base anchors no longer contain `m` — and the HIGHLIGHT that
  // confirms `m` is applied AFTER them. Forgotten, that action had nothing to
  // resolve against and was dropped, so `m` was never confirmed and lost its
  // highlight on the next turn (#321, Sanya 18 Sep). An unconfirmed anchor is
  // kept as bare geometry: no highlight, no label, so it still stops pointing.
  const confirmed = new Map(
    (previous ?? []).filter((a) => a?.token_id).map((a) => [
      a.token_id,
      a.confirmed ? a : { ...a, highlighted: false, label: null },
    ]),
  );

  const merged = (incoming ?? []).map((anchor) => {
    const held = confirmed.get(anchor.token_id);
    if (!held?.confirmed) {
      confirmed.delete(anchor.token_id);
      return anchor;
    }
    confirmed.delete(anchor.token_id);
    return {
      ...anchor,
      // The confirmed label is the student's own idea. A base label shipped
      // with the question must not overwrite it.
      label: held.label ?? anchor.label ?? null,
      highlighted: held.highlighted,
      confirmed: true,
    };
  });

  // Whatever is left was on screen on an earlier turn and simply not repeated,
  // which is the ordinary case: most replies carry no anchors at all. Confirmed
  // ones keep their marks; the rest are bare geometry for later actions.
  return [...merged, ...confirmed.values()].sort((a, b) => a.char_start - b.char_start);
}

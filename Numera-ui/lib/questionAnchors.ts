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

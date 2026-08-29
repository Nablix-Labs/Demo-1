/**
 * Which content the Review screen is allowed to show.
 *
 * The screen has three possible sources and they must not be confused: the
 * backend's own graded outcomes, the demo worksheets, and nothing at all.
 *
 * This decision used to live inline as `const live = outcomes.length > 0`,
 * which reads as "did we get real results" and behaves as "fall back to the
 * mock when we didn't". A REAL session that ends with nothing graded — row 17's
 * zero `per_question_history` is exactly that state — then rendered the demo
 * worksheets, the demo topic label and the demo summary as the student's own
 * work. It is also the tail of row 42: that fix keyed on the same count, so a
 * live session with no outcomes still printed "Linear equations · today" over
 * a lesson about something else.
 *
 * The question is which MODE we are in, not whether this session happened to
 * produce results. In API mode an empty result is truthful and gets said
 * plainly; only mock mode may invent.
 *
 * A named function rather than two lines in the component, for the reason
 * lib/sessionEnd.ts already gives about itself: a guard inside a component
 * cannot be tested, so nothing fails when it becomes wrong.
 */
export type ReviewSource =
  /** Real graded outcomes from /session/end. */
  | 'backend'
  /** No backend at all — the demo worksheets are the point. */
  | 'demo'
  /** Live session, nothing graded. Say so; never substitute the demo. */
  | 'none';

export function reviewSource(apiEnabled: boolean, gradedCount: number): ReviewSource {
  if (!apiEnabled) return 'demo';
  return gradedCount > 0 ? 'backend' : 'none';
}

/**
 * What /session/end must carry for the Review screen to open.
 *
 * Exactly one thing: a usable summary. This is a named function rather than two
 * lines inside the hook because the list of things it insists on is the list
 * that broke — and a guard inside a hook cannot be tested, so nothing failed
 * when it became wrong.
 *
 * It insisted on `session_review` until 18 Aug 2026. That field was deleted
 * from the backend outright (Sanya PR #155, "remove legacy session review
 * flow") because Phase 4 replaces it. Every /session/end after that merge threw
 * here, the Review screen read the throw as a failed end, and students who had
 * just finished a topic were told their review could not be loaded — for work
 * that had completed perfectly well.
 *
 * The rule this leaves behind: a field the backend stops sending must degrade
 * to "that part is not shown", never to "the screen failed". Only data the
 * screen genuinely cannot open without belongs in here.
 */

import { toSessionSummary, type SessionEndResponse, type SessionSummary } from '@/lib/api';

export function sessionEndSummary(
  res: SessionEndResponse | null | undefined,
): SessionSummary {
  const summary = toSessionSummary(res);
  // No summary means no session came back at all — there is nothing to review
  // and the backend has left the session open, so this genuinely is a failure.
  if (!summary) throw new Error('Session ended but no summary was returned.');
  return summary;
}

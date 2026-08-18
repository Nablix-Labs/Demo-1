/**
 * The student-facing Learning Summary (§8.9) — which sections exist, and in
 * what order.
 *
 * The whole point of this module is the hiding. §7.6C makes
 * `learning_pattern_summary` null when the evidence is a single isolated
 * occurrence, and §7.6D makes `recent_improvement_summary` null when the
 * student never repaired anything; §8.9 then says "Hide the section if null".
 *
 * That is a real instruction and not a tidiness one. "Pattern to Watch" over an
 * empty box tells a student there is a pattern and the app has forgotten it,
 * and "How You Improved" over nothing reads as a verdict on whether they did.
 * The tutor engine is explicitly forbidden from inventing either (§7.6C "Never
 * say: You always get signs wrong"), and a screen that prints the heading
 * anyway puts the claim back on the page the engine refused to make.
 */

import type { Phase4Review, Phase4StudentInsights } from '@/lib/api';

export interface InsightSection {
  key: string;
  title: string;
  body: string;
}

/**
 * §8.9's headings, in the order the spec lists them. Titles are the student's
 * words from the spec, not the field names.
 */
export function insightSections(insights: Phase4StudentInsights): InsightSection[] {
  const candidates: Array<[string, string, string | null | undefined]> = [
    ['strength', 'What you did well', insights.strength_summary],
    ['development', 'What to work on', insights.development_summary],
    ['pattern', 'Pattern to watch', insights.learning_pattern_summary],
    ['improvement', 'How you improved', insights.recent_improvement_summary],
    ['next', 'Next practice', insights.next_practice_focus],
  ];

  // Whitespace counts as absent. A field trimmed to nothing is the same
  // "no meaningful statement exists" case as null, and the two arrive
  // interchangeably from a generated payload.
  return candidates.flatMap(([key, title, value]) => {
    const body = value?.trim();
    return body ? [{ key, title, body }] : [];
  });
}

/**
 * §8.9 "Render key_takeaways[]".
 *
 * Read from `key_takeaways` with `personalised_notes` as the fallback, because
 * the specification names both for the same content and never reconciles them:
 * §7.8 has the engine emit `personalised_notes`, §5.8 has it stored as
 * `key_takeaways_json`, and §8.9 has the screen render `key_takeaways[]`. Which
 * name survives the merge in §6.10 is Chiru's choice and not one worth blocking
 * on — accepting either costs one line here and avoids a release that renders
 * an empty section because the field was renamed in transit.
 */
/**
 * A backend enum as a student should read it: `NEARLY_MASTERED` → "Nearly
 * mastered". Used for `mastery_status` and `recommended_next_action`, the two
 * §9.2 fields that are both saved internally AND shown to the student.
 *
 * Deliberately a transformation and not a lookup table. A map would have to
 * name every value the backend might send, and an unmapped one would render as
 * a blank or as the raw token; Sanya has renamed enums mid-sprint before
 * (JOURNEY status, 12 Aug), so the rule that has to hold is that a value nobody
 * anticipated still comes out readable.
 *
 * Anything that is not an ALL_CAPS token is passed through untouched — if the
 * backend starts sending prose, that prose is already what we want to show.
 */
export function humanLabel(value: string): string {
  const token = value.trim();
  if (!token) return '';
  if (!/^[A-Z0-9_]+$/.test(token)) return token;
  const words = token.toLowerCase().split('_').filter(Boolean).join(' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function keyTakeaways(review: Phase4Review): string[] {
  const source = review.key_takeaways?.length
    ? review.key_takeaways
    : review.student_insights.personalised_notes;
  return (source ?? []).map((note) => note.trim()).filter(Boolean);
}

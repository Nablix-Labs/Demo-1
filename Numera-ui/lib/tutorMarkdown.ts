/**
 * The tutor writes markdown; nothing downstream of it speaks markdown.
 *
 * Observed live on 26 Aug 2026, Phase 2: the tutor replied "can you explain
 * why **n + 4** works for any starting value?" and the student read the
 * asterisks. The backend emphasises the mathematical object it wants looked
 * at, which is exactly the part that must not arrive looking like syntax.
 *
 * Only `**bold**` is handled. That is not a shortcut — it is the only marker
 * the tutor emits, and shipping a markdown parser into a live chat bubble
 * would be solving a problem nobody has. `components/TutorProse` renders it;
 * this module owns the pattern and the string form speech is given.
 */

/**
 * `a **b** c`.split() → ['a ', 'b', ' c'] — odd indices are the emphasised runs.
 * A single capture group is what makes that split shape hold, so the renderer
 * and the stripper cannot drift apart.
 */
export const TUTOR_EMPHASIS = /\*\*([^*]+)\*\*/g;

/**
 * The same text with the markers removed, for anything that is not HTML.
 *
 * Speech is why this exists: a reply is voiced with the exact string shown in
 * chat, so the markers would otherwise reach the TTS engine. Engines differ on
 * whether they read them aloud, and "asterisk asterisk n plus four" is not a
 * risk worth leaving open.
 */
export function stripTutorMarkdown(text: string): string {
  return text.replace(TUTOR_EMPHASIS, '$1');
}

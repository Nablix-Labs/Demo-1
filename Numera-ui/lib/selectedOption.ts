/**
 * The exact wording of the option a student picked.
 *
 * The revised integration handoff asks the frontend to send "selected option ID
 * and exact option text", and the backend to reach the tutor with "selected
 * option ID and text" — so that a wrong option "receives a focused explanation
 * request, not generic fallback wording".
 *
 * We were sending the id alone. The id names a slot; only the text says what the
 * student actually believes. Given "B" the tutor can say no more than that B is
 * wrong; given "n + 4" it can address the mistake in front of it. Recovering the
 * text backend-side is possible but means re-reading the authored question to
 * answer a question the client already knows, and it silently produces nothing
 * when the option list has moved on.
 *
 * Null rather than the id as a stand-in when the option cannot be found: the
 * text is meant to be the option's exact authored wording, and an id dressed up
 * as text would be worse than an absent field — it reads as the student having
 * said "B".
 */

export interface OptionLike {
  option_id: string;
  text: string;
}

export function selectedOptionText(
  options: readonly OptionLike[] | null | undefined,
  selectedOptionId: string | null | undefined,
): string | null {
  if (!selectedOptionId || !options) return null;
  const match = options.find((o) => o.option_id === selectedOptionId);
  const text = match?.text?.trim();
  return text || null;
}

/**
 * The tutor's ink colours, by what the ink is FOR.
 *
 * Manjusha, 22 Sep 2026: "more tutor writing … with clear presentation (diff
 * ink and simple way) similar to phase 4 review". Palette agreed 4 Oct: amber
 * for what changes, teal for what stays fixed, navy for the conclusion.
 *
 * Content names a role, never a colour — the same rule as the canvas contract,
 * where the backend names a token or a slot and the frontend lays it out. One
 * map, so Phase 1 and Phase 2 speak the same colour language.
 *
 * The amber is darker than the brand's highlight amber (#FF9F1C): that one is
 * a fill colour, and as thin handwriting on white it fails contrast.
 */

export type InkRole = 'CHANGE' | 'FIXED' | 'CONCLUSION';

export const INK_DEFAULT = '#1B2A4A';

const INK: Record<InkRole, string> = {
  CHANGE: '#C26A00',
  FIXED: '#0F8A7E',
  CONCLUSION: '#1B2A4A',
};

/** The colour for a role; navy for none, or for a role this build doesn't know. */
export function inkFor(role: string | null | undefined): string {
  if (!role) return INK_DEFAULT;
  return INK[role.toUpperCase() as InkRole] ?? INK_DEFAULT;
}

import { Caveat } from 'next/font/google';

/**
 * The tutor's handwriting.
 *
 * Caveat is a marker-style connected hand. The connection matters: the canvas
 * reveals written marks with a left→right ink wipe, and cursive is genuinely
 * written left→right in one motion, so the wipe lands as real handwriting
 * rather than as an approximation of it. A print face would expose the trick.
 *
 * Self-hosted by next/font so the static export on the VM has no external font
 * request to make.
 */
export const caveat = Caveat({
  subsets: ['latin'],
  weight: ['500', '700'],
  display: 'swap',
  variable: '--font-tutor-hand',
});

/**
 * Consumed only by the root layout, which applies `caveat.variable` so the face
 * is fetched and `--font-tutor-hand` is exposed. Canvas code must NOT import
 * this module: `next/font` is a build-time transform and pulling it into a pure
 * helper makes that helper impossible to unit test. The canvas resolves the
 * family from the CSS variable at runtime instead — see tutorFontFamily().
 */

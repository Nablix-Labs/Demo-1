/**
 * The image that belongs to a visual cue, if the backend sent a usable one.
 *
 * Sanya, 12 Aug 2026: cue asset URLs are arriving wrapped in escaped quotes —
 *
 *   "asset_url": "\"https://.../cues/VC-T01-ADD-NOT-MULTIPLY.png\""
 *
 * — which is not a loadable URL, and some cues (VC-T01-OPERATOR-SLOT) have no
 * URL at all and are text-only by design. The content fix is hers; this makes
 * the client survive both without the cue card breaking.
 *
 * The rule is that a cue image is strictly additive. The text card is the cue;
 * the picture illustrates it. Anything we cannot confidently load returns null
 * and the card renders exactly as it does today.
 */

/** Hosts a cue image may be loaded from. */
const ALLOWED_HOSTS = ['nablixmathvideos.blob.core.windows.net'];

export function cueAssetUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  // Strip the escaped/plain quotes the content pipeline is wrapping URLs in,
  // plus surrounding whitespace.
  const cleaned = raw.trim().replace(/^["'\\\s]+/, '').replace(/["'\\\s]+$/, '');
  if (!cleaned) return null;

  let url: URL;
  try {
    url = new URL(cleaned);
  } catch {
    return null;
  }
  // https only, and only from a host we publish cues on: this string comes from
  // authored content and ends up in an <img src>, so it is not a place to be
  // permissive.
  if (url.protocol !== 'https:') return null;
  if (!ALLOWED_HOSTS.includes(url.hostname)) return null;
  return url.toString();
}

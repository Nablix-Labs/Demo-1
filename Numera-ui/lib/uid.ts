/**
 * `crypto.randomUUID()` only exists in secure contexts (HTTPS or localhost) —
 * on a plain-HTTP origin it's undefined and throws. These IDs are just
 * client-side React/store keys, so a non-cryptographic fallback is fine.
 */
export function uid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

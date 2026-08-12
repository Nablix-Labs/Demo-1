/**
 * Cue images must never be able to break the cue.
 *
 * Sanya, 12 Aug 2026: asset URLs are arriving wrapped in escaped quotes, and
 * some cues have no URL at all and are text-only by design. The text card IS
 * the cue; the picture only illustrates it, so anything we cannot confidently
 * load has to degrade to "no image" rather than to a broken card.
 */

import { describe, it, expect } from 'vitest';
import { cueAssetUrl } from '@/lib/cueAsset';

const GOOD = 'https://nablixmathvideos.blob.core.windows.net/numeradev/cues/VC-T01-ADD-NOT-MULTIPLY.png';

describe('cueAssetUrl', () => {
  it('accepts a well-formed cue URL', () => {
    expect(cueAssetUrl(GOOD)).toBe(GOOD);
  });

  it('unwraps the escaped quotes the content pipeline is adding', () => {
    // The exact malformed shape from Sanya's report.
    expect(cueAssetUrl(`"${GOOD}"`)).toBe(GOOD);
    expect(cueAssetUrl(`\\"${GOOD}\\"`)).toBe(GOOD);
    expect(cueAssetUrl(`  ${GOOD}  `)).toBe(GOOD);
  });

  it('returns null for a cue that is text-only', () => {
    // VC-T01-OPERATOR-SLOT has no usable URL; the card still renders.
    for (const raw of [null, undefined, '', '   ', '""']) {
      expect(cueAssetUrl(raw)).toBeNull();
    }
  });

  it('returns null rather than throwing on a value that is not a URL', () => {
    for (const raw of ['not a url', 'cues/VC-T01.png', 'javascript:alert(1)']) {
      expect(cueAssetUrl(raw)).toBeNull();
    }
  });

  it('refuses anything not https on our own cue host', () => {
    // This string comes from authored content and ends up in an <img src>.
    expect(cueAssetUrl('http://nablixmathvideos.blob.core.windows.net/c/x.png')).toBeNull();
    expect(cueAssetUrl('https://example.com/cues/x.png')).toBeNull();
  });
});

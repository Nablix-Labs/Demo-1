/**
 * Orientation video URLs.
 *
 * These are built by string interpolation from a sequence number, so a padding
 * or base-path slip produces a URL that 404s at Azure — and the only symptom is
 * a video that silently never plays. The exact filenames were confirmed against
 * the container on 2026-07-28 (01–06 return 206, 07 returns 404).
 */

import { describe, it, expect } from 'vitest';
import { ORIENTATION_VIDEOS, orientationFor, orientationVideoForTopicCode } from '@/lib/demoContent';

describe('ORIENTATION_VIDEOS', () => {
  it('covers exactly the six files that exist in the container', () => {
    expect(ORIENTATION_VIDEOS.map((v) => v.src)).toEqual([
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-01.mp4',
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-02.mp4',
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-03.mp4',
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-04.mp4',
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-05.mp4',
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-06.mp4',
    ]);
  });

  it('numbers sequences from 1 to match the backend subtopic order', () => {
    expect(ORIENTATION_VIDEOS.map((v) => v.sequence)).toEqual([1, 2, 3, 4, 5, 6]);
  });
});

describe('orientationFor', () => {
  it('gives algebra the real first video, not the simulated player', () => {
    const media = orientationFor('algebra');
    expect(media?.kind).toBe('video');
    expect(media && 'src' in media ? media.src : null).toBe(ORIENTATION_VIDEOS[0].src);
  });

  it('leaves a topic with no file on the simulated player', () => {
    const media = orientationFor('geometry');
    expect(media?.kind).toBe('video');
    expect(media && 'src' in media ? media.src : undefined).toBeUndefined();
  });
});

/**
 * Which URL the player uses.
 *
 * The backend currently sends `asset_url: null` and we fall back to the blob
 * file resolved from the topic code. The moment the Student Model populates
 * asset_url it must take priority with no frontend change — this pins that
 * precedence so the fallback can't quietly shadow a real backend URL.
 *
 * Mirrors `const src = item.video.asset_url ?? orientationVideoForTopicCode(...)`
 * in OrientationClient's OrientationItem.
 */
describe('orientation video source precedence', () => {
  const resolve = (assetUrl: string | null, topicCode: string | null) =>
    assetUrl ?? orientationVideoForTopicCode(topicCode);

  it('uses the backend asset_url when it is present', () => {
    expect(resolve('https://cdn.example.com/whatever.mp4', 'ALG-ORI-02'))
      .toBe('https://cdn.example.com/whatever.mp4');
  });

  it('falls back to the uploaded file when asset_url is null', () => {
    expect(resolve(null, 'ALG-ORI-02')).toMatch(/ALG-ORI-02\.mp4$/);
  });

  it('renders no player when there is neither', () => {
    expect(resolve(null, 'ALG-99')).toBeNull();
  });
});

/**
 * Reverted to Azure blob on 2026-08-10 (storage decision: one ecosystem), so
 * there is no second host to prefer any more — asset_url, then the file we
 * resolve from the topic code, and that is the whole rule. The precedence
 * block above is now the only one, which is the point.
 */

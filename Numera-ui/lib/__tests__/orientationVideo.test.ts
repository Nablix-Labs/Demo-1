/**
 * Orientation video URLs.
 *
 * These are built by string interpolation from a sequence number, so a padding
 * or base-path slip produces a URL that 404s at Azure — and the only symptom is
 * a video that silently never plays. The exact filenames were confirmed against
 * the container on 2026-07-28 (01–06 return 206, 07 returns 404).
 */

import { describe, it, expect } from 'vitest';
import { ORIENTATION_VIDEOS, orientationFor } from '@/lib/demoContent';

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

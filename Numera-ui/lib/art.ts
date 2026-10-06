/**
 * Illustrations in /public/art (Midjourney, backgrounds cut out, WebP).
 *
 * Raw /public URLs are not prefixed with the export base path (/app on the VM),
 * so every src goes through here rather than being written inline.
 */
import { basePath } from '@/lib/runtimeConfig';

export const art = (path: string): string => `${basePath}/art/${path}.webp`;

const TOPICS = new Set(['algebra', 'number', 'geometry', 'statistics']);
const SUBTOPICS = new Set([
  'linear-equations', 'expressions', 'calculus', 'fractions',
  'ratio', 'angles', 'area', 'averages',
]);

/** Cover art for a curriculum topic, or null when there is none yet. */
export const topicArt = (id: string): string | null => (TOPICS.has(id) ? art(`topics/${id}`) : null);

/** Spot art for a subtopic sheet, or null when there is none yet. */
export const subtopicArt = (id: string): string | null =>
  SUBTOPICS.has(id) ? art(`subtopics/${id}`) : null;

/** The paper colour behind cover art — matches the illustrations' own stock. */
export const ART_PAPER = '#F4EEE1';

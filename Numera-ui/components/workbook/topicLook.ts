/**
 * How each topic's book looks.
 *
 * Shared by the workbook shelf and the opened topic, because the whole point is
 * that they are the same object: click the blue Algebra book and the blue
 * Algebra book opens. Two copies of this map would drift the first time someone
 * changed one colour, and the connection would quietly break.
 *
 * Colour is fixed per subject rather than derived from progress, so a topic
 * stays recognisable — the shelf works by recognition, not by reading.
 */

import { Sigma, Hash, Shapes, BarChart3, Folder } from 'lucide-react';

export interface TopicLook {
  color: string;
  Icon: typeof Folder;
}

const LOOKS: Record<string, TopicLook> = {
  algebra: { color: '#3E5FD4', Icon: Sigma },
  number: { color: '#0E93B4', Icon: Hash },
  geometry: { color: '#E07A3F', Icon: Shapes },
  statistics: { color: '#4F8A6B', Icon: BarChart3 },
};

const FALLBACK: TopicLook = { color: '#4A6984', Icon: Folder };

export const topicLook = (id: string): TopicLook => LOOKS[id] ?? FALLBACK;

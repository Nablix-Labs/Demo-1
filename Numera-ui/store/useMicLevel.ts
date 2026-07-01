'use client';

/**
 * useMicLevel — a tiny, isolated store for the live microphone level.
 *
 * Kept separate from the main store on purpose: the VAD loop writes here at
 * ~30fps while listening, and only the listening bar subscribes. Putting this
 * in the main store would re-render the canvas, toolbar and every other
 * whole-store subscriber on every audio frame.
 */

import { create } from 'zustand';

export const MIC_BARS = 14;

interface MicLevelState {
  active: boolean;        // mic is capturing
  levels: number[];       // per-bar input level, 0..1 (length MIC_BARS)
  caption: string;        // live speech-to-text of the current utterance
  setLevels: (levels: number[]) => void;
  setActive: (active: boolean) => void;
  setCaption: (caption: string) => void;
}

export const useMicLevel = create<MicLevelState>((set) => ({
  active: false,
  levels: new Array(MIC_BARS).fill(0),
  caption: '',
  setLevels: (levels) => set({ levels }),
  setActive: (active) => set(active ? { active } : { active: false, levels: new Array(MIC_BARS).fill(0), caption: '' }),
  setCaption: (caption) => set({ caption }),
}));

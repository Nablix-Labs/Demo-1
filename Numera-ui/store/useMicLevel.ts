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

/** Why the microphone is not delivering audio, when it should be. */
export type MicError = 'denied' | 'failed' | null;

interface MicLevelState {
  active: boolean;        // mic is capturing
  levels: number[];       // per-bar input level, 0..1 (length MIC_BARS)
  caption: string;        // live speech-to-text of the current utterance
  aiSpeaking: boolean;    // Numera's TTS is currently talking
  lastBoundary: number;   // performance.now() of the last spoken-word boundary
  micError: MicError;     // capture failed — the UI must say so, not show "Listening…"
  setLevels: (levels: number[]) => void;
  setActive: (active: boolean) => void;
  setCaption: (caption: string) => void;
  setAiSpeaking: (aiSpeaking: boolean) => void;
  setMicError: (micError: MicError) => void;
  markBoundary: () => void; // a word was just spoken — pulses the avatar's mouth
}

export const useMicLevel = create<MicLevelState>((set) => ({
  active: false,
  levels: new Array(MIC_BARS).fill(0),
  caption: '',
  aiSpeaking: false,
  lastBoundary: 0,
  micError: null,
  setLevels: (levels) => set({ levels }),
  setActive: (active) => set(active ? { active } : { active: false, levels: new Array(MIC_BARS).fill(0), caption: '' }),
  setCaption: (caption) => set({ caption }),
  setAiSpeaking: (aiSpeaking) => set({ aiSpeaking }),
  setMicError: (micError) => set({ micError }),
  markBoundary: () => set({ aiSpeaking: true, lastBoundary: typeof performance !== 'undefined' ? performance.now() : Date.now() }),
}));

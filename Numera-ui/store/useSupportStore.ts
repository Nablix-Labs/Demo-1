'use client';

/**
 * Nablix Assist — support-mode store.
 *
 * Deliberately SEPARATE from useNumeraStore: support mode must never touch the
 * academic transcript, session or learning state. Everything the assistant
 * says/hears lives here, and opening/closing support only pauses/resumes the
 * tutor around a snapshot of the pre-support voice state — no page refresh,
 * no canvas or form changes.
 */

import { create } from 'zustand';
import { useNumeraStore } from '@/store/useNumeraStore';
import { tutorAudioStream } from '@/lib/tts';
import { uid } from '@/lib/uid';
import type { SupportInstructionResponse } from '@/lib/support/assistApi';

export interface SupportMessage {
  id: string;
  role: 'assist' | 'user';
  text: string;
  timestamp: number;
}

/** An allow-listed action waiting for the student's confirmation. */
export interface PendingAction {
  actionId: string;
  label: string; // human phrasing for the consent modal ("I can do X — continue?")
}

/** Voice state captured when support opens, restored exactly on close. */
interface TutorSnapshot {
  micMuted: boolean;
  voiceStatus: 'idle' | 'listening' | 'speaking' | 'processing';
}

interface SupportState {
  open: boolean;
  /** Support chat — never mixed into the academic transcript. */
  messages: SupportMessage[];
  /** The instruction the student is currently being walked through. */
  instruction: SupportInstructionResponse | null;
  /** Action awaiting the consent modal. */
  pendingAction: PendingAction | null;
  /** True while waiting on the assist backend or running an action. */
  busy: boolean;
  /** Text input is forced open when the issue is the mic itself. */
  textOnly: boolean;

  snapshot: TutorSnapshot | null;

  openSupport: () => void;
  closeSupport: () => void;
  addMessage: (msg: Omit<SupportMessage, 'id' | 'timestamp'>) => void;
  setInstruction: (instruction: SupportInstructionResponse | null) => void;
  setPendingAction: (pendingAction: PendingAction | null) => void;
  setBusy: (busy: boolean) => void;
  setTextOnly: (textOnly: boolean) => void;
}

export const useSupportStore = create<SupportState>((set, get) => ({
  open: false,
  messages: [],
  instruction: null,
  pendingAction: null,
  busy: false,
  textOnly: false,
  snapshot: null,

  // Pause the tutor without touching its state beyond the mic: snapshot the
  // voice flags, mute (the lesson page stops capture when muted) and silence
  // any in-flight tutor speech. Transcript/session/canvas are left alone.
  openSupport: () => {
    if (get().open) return;
    const n = useNumeraStore.getState();
    const snapshot: TutorSnapshot = { micMuted: n.micMuted, voiceStatus: n.voiceStatus };
    n.setMicMuted(true);
    if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
    tutorAudioStream.stop();
    set({ open: true, snapshot });
  },

  // Restore the exact pre-support voice state. Support chat is kept so
  // re-opening shows the conversation so far.
  closeSupport: () => {
    const { snapshot } = get();
    if (snapshot) {
      const n = useNumeraStore.getState();
      n.setMicMuted(snapshot.micMuted);
      n.setVoiceStatus(snapshot.voiceStatus);
    }
    set({ open: false, snapshot: null, pendingAction: null, busy: false });
  },

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, { ...msg, id: uid(), timestamp: Date.now() }] })),

  setInstruction: (instruction) => set({ instruction }),
  setPendingAction: (pendingAction) => set({ pendingAction }),
  setBusy: (busy) => set({ busy }),
  setTextOnly: (textOnly) => set({ textOnly }),
}));

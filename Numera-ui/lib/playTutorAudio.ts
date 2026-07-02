'use client';

import { useMicLevel } from '@/store/useMicLevel';

function speak(text: string, onDone?: () => void): void {
  if (typeof window === 'undefined' || !text) {
    onDone?.();
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onend = () => onDone?.();
  utterance.onerror = () => onDone?.();
  window.speechSynthesis.speak(utterance);
}

/** Play the tutor's TTS (or speak the fallback). `onDone` fires when playback finishes.
 *  Drives the 3D avatar's mouth via useMicLevel: aiSpeaking=true while playing.
 *  ponytail: continuous flutter only — <Audio> has no word-boundary events. */
export function playTutorAudio(
  audioBase64: string | null | undefined,
  fallbackText: string,
  onDone?: () => void,
): void {
  useMicLevel.getState().setAiSpeaking(true);
  const finish = () => {
    useMicLevel.getState().setAiSpeaking(false);
    onDone?.();
  };

  if (!audioBase64 || typeof Audio === 'undefined') {
    speak(fallbackText, finish);
    return;
  }

  const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
  audio.onended = finish;
  audio.onerror = finish;
  void audio.play().catch(() => speak(fallbackText, finish));
}

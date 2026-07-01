'use client';

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

/** Play the tutor's TTS (or speak the fallback). `onDone` fires when playback finishes. */
export function playTutorAudio(
  audioBase64: string | null | undefined,
  fallbackText: string,
  onDone?: () => void,
): void {
  if (!audioBase64 || typeof Audio === 'undefined') {
    speak(fallbackText, onDone);
    return;
  }

  const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
  audio.onended = () => onDone?.();
  audio.onerror = () => onDone?.();
  void audio.play().catch(() => speak(fallbackText, onDone));
}

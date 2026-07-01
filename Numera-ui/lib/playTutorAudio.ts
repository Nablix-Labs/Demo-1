'use client';

function speak(text: string): void {
  if (typeof window === 'undefined' || !text) return;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

export function playTutorAudio(audioBase64: string | null | undefined, fallbackText: string): void {
  if (!audioBase64 || typeof Audio === 'undefined') {
    speak(fallbackText);
    return;
  }

  const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
  void audio.play().catch(() => speak(fallbackText));
}

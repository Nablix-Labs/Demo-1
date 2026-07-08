'use client';

/**
 * Tutor text-to-speech — two independent engines:
 *
 *   • Browser (Web Speech API) via speakTutor() — the browser voices the reply
 *     itself. Zero latency, no backend. Used by the REST demo path (useDemoTutor)
 *     when the voice server isn't driving the turn.
 *
 *   • Streaming (MediaSource) via tutorAudioStream — plays the MP3 audio the voice
 *     server streams over the /voice WebSocket, so the tutor starts speaking while
 *     the clip is still being generated (~300-500ms vs 2-3s). This is Aditya's
 *     :8004 protocol, fed in by useWebSocket:
 *
 *       { type: 'tutor_response',    text, voice_text, ... }   // text — show now
 *       { type: 'tutor_audio_chunk', chunk, chunk_index }      // base64 MP3
 *       { type: 'tutor_audio_end',   total_chunks, error? }    // done (or failed)
 *
 * Both engines drive the 3D avatar's mouth via useMicLevel (setAiSpeaking +
 * markBoundary), so the face animates the same way regardless of engine.
 */

import { useMicLevel } from '@/store/useMicLevel';

/** The voice server always streams MP3. */
const AUDIO_MIME = 'audio/mpeg';
/** Mouth-flutter pace while streamed audio plays (no real word boundaries in mp3). */
const MOUTH_PULSE_MS = 180;

// ── Browser engine (Web Speech API) ──────────────────────────────────────────
export function speakBrowser(text: string): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onstart = () => useMicLevel.getState().setAiSpeaking(true);
  utterance.onboundary = () => useMicLevel.getState().markBoundary();
  utterance.onend = () => useMicLevel.getState().setAiSpeaking(false);
  utterance.onerror = () => useMicLevel.getState().setAiSpeaking(false);
  window.speechSynthesis.cancel();
  useMicLevel.getState().setAiSpeaking(false); // reset before the new utterance starts
  window.speechSynthesis.speak(utterance);
}

/** Voice the tutor's reply through the browser. Pass the exact text shown in chat
 *  so the audio matches the words on screen. Used by the REST demo path. */
export function speakTutor(text: string): void {
  speakBrowser(text);
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64);
  const bytes = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

// ── Streaming engine (MediaSource, "Option B") ───────────────────────────────
/**
 * Plays MP3 audio streamed over the WebSocket in chunks. begin() on tutor_response,
 * push() per tutor_audio_chunk, finish() on tutor_audio_end. Chunks are appended in
 * chunk_index order (WS preserves order, but we honour the index defensively).
 */
class TutorAudioStream {
  private audio: HTMLAudioElement | null = null;
  private media: MediaSource | null = null;
  private buffer: SourceBuffer | null = null;
  private objectUrl: string | null = null;

  private active = false;
  private nextIndex = 0;
  private pending = new Map<number, Uint8Array<ArrayBuffer>>(); // chunks held until their turn
  private ended = false;
  private mouthTimer: ReturnType<typeof setInterval> | null = null;

  /** A new tutor reply is starting — reset and prepare to receive audio chunks. */
  begin(): void {
    window.speechSynthesis?.cancel(); // streamed audio supersedes any browser voice
    this.teardown();

    const supported =
      typeof window !== 'undefined' &&
      typeof MediaSource !== 'undefined' &&
      MediaSource.isTypeSupported(AUDIO_MIME);
    if (!supported) return; // text is already shown; skip audio on this browser

    this.active = true;
    this.nextIndex = 0;
    this.ended = false;
    this.pending.clear();

    const media = new MediaSource();
    this.media = media;
    this.objectUrl = URL.createObjectURL(media);
    const audio = new Audio();
    audio.src = this.objectUrl;
    this.audio = audio;

    media.addEventListener('sourceopen', () => {
      if (this.media !== media) return; // superseded before it opened
      try {
        const buffer = media.addSourceBuffer(AUDIO_MIME);
        this.buffer = buffer;
        buffer.addEventListener('updateend', () => this.pump());
        this.pump();
      } catch {
        this.finish();
      }
    });

    audio.onplaying = () => {
      useMicLevel.getState().setAiSpeaking(true);
      this.startMouth();
    };
    audio.onended = () => this.finish();
    audio.onerror = () => this.finish();
    void audio.play().catch(() => { /* may defer until buffered data lands */ });
  }

  /** One tutor_audio_chunk: base64 MP3 bytes at chunk_index. */
  push(chunkIndex: number, base64: string): void {
    if (!this.active) return;
    this.pending.set(chunkIndex, base64ToBytes(base64));
    this.pump();
  }

  /** tutor_audio_end: no more chunks. total<=0 or an error means text-only (no audio). */
  finishStream(totalChunks: number, error?: string): void {
    if (!this.active) return;
    if (error || totalChunks <= 0) {
      this.finish(); // nothing to play — leave the text on screen
      return;
    }
    this.ended = true;
    this.pump();
  }

  /** Stop playback immediately (e.g. student barge-in). */
  stop(): void {
    window.speechSynthesis?.cancel();
    this.finish();
  }

  // Append in-order chunks as they arrive; close the stream once fully drained.
  private pump(): void {
    const buffer = this.buffer;
    const media = this.media;
    if (!buffer || !media || buffer.updating) return;
    const next = this.pending.get(this.nextIndex);
    if (next) {
      this.pending.delete(this.nextIndex);
      this.nextIndex++;
      try {
        buffer.appendBuffer(next);
      } catch {
        this.finish();
      }
      return;
    }
    if (this.ended && this.pending.size === 0 && media.readyState === 'open') {
      try {
        media.endOfStream();
      } catch { /* already ended */ }
    }
  }

  private startMouth(): void {
    if (this.mouthTimer) return;
    this.mouthTimer = setInterval(() => useMicLevel.getState().markBoundary(), MOUTH_PULSE_MS);
  }

  private finish(): void {
    this.stopMouth();
    useMicLevel.getState().setAiSpeaking(false);
    this.teardown();
  }

  private stopMouth(): void {
    if (this.mouthTimer) clearInterval(this.mouthTimer);
    this.mouthTimer = null;
  }

  private teardown(): void {
    this.stopMouth();
    if (this.audio) {
      this.audio.onplaying = this.audio.onended = this.audio.onerror = null;
      try { this.audio.pause(); } catch { /* noop */ }
      this.audio.removeAttribute('src');
      this.audio = null;
    }
    this.buffer = null;
    this.media = null;
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
    this.active = false;
    this.ended = false;
    this.pending.clear();
  }
}

export const tutorAudioStream = new TutorAudioStream();

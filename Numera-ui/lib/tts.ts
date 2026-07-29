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
import { useAuthStore } from '@/store/useAuthStore';
import { defaultVoiceForTier } from '@/lib/voiceOptions';
import { useNumeraStore } from '@/store/useNumeraStore';
import { synthesizeSpeech } from '@/lib/api';

/** The voice server always streams MP3. */
const AUDIO_MIME = 'audio/mpeg';
/** Mouth-flutter pace while streamed audio plays (no real word boundaries in mp3). */
// Mouth pulses with no audio progress before we treat the utterance as over.
const STALL_TICKS = 6;

const MOUTH_PULSE_MS = 180;

// ── Browser engine (Web Speech API) ──────────────────────────────────────────
export function speakBrowser(text: string, onEnd?: () => void): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) {
    onEnd?.();
    return;
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onstart = () => useMicLevel.getState().setAiSpeaking(true);
  utterance.onboundary = () => useMicLevel.getState().markBoundary();
  utterance.onend = () => { useMicLevel.getState().setAiSpeaking(false); onEnd?.(); };
  utterance.onerror = () => { useMicLevel.getState().setAiSpeaking(false); onEnd?.(); };
  window.speechSynthesis.cancel();
  useMicLevel.getState().setAiSpeaking(false); // reset before the new utterance starts
  window.speechSynthesis.speak(utterance);
}

// ── Backend engine (/voice/tts) with browser fallback ───────────────────────
const ttsApiEnabled = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

/**
 * The provider/voice this student should be heard in, right now.
 *
 * THE single source of truth for both transports — REST `POST /voice/tts` and
 * the `/voice/stream` WebSocket — so a student hears one voice across every
 * phase. Resolve at call time rather than seeding the store at login: the tier
 * is the server's to decide, and a value written into persisted state at login
 * would outlive an upgrade or downgrade.
 *
 * A null selection means "whatever my plan gives me", NOT "whatever the server
 * env is set to". That distinction is the bug this fixes: the WebSocket used to
 * pass the raw store values through, so before anyone opened the voice picker
 * it sent no tts_provider at all and guided practice fell back to the server
 * default (OpenAI) while the diagnostic — which already applied the tier
 * default — spoke as Cartesia or Inworld. Same student, two voices, one
 * session (Manjusha, 2026-07-29).
 */
export function effectiveVoice(): { provider: string | null; voice: string | null } {
  const { ttsProvider, ttsVoice } = useNumeraStore.getState();
  if (ttsProvider) return { provider: ttsProvider, voice: ttsVoice };
  const tierDefault = defaultVoiceForTier(useAuthStore.getState().tier);
  return { provider: tierDefault?.provider ?? null, voice: tierDefault?.voice ?? null };
}

let currentAudio: HTMLAudioElement | null = null;
let speakToken = 0; // invalidates in-flight TTS fetches when superseded/stopped

/** Stop whichever engine is currently voicing the tutor. */
export function stopTutorSpeech(): void {
  speakToken++;
  if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
  if (currentAudio) {
    try { currentAudio.pause(); } catch { /* noop */ }
    currentAudio = null;
  }
  useMicLevel.getState().setAiSpeaking(false);
}

function playBase64Mp3(base64: string, onEnd?: () => void): void {
  const audio = new Audio(`data:${AUDIO_MIME};base64,${base64}`);
  currentAudio = audio;
  let mouthTimer: ReturnType<typeof setInterval> | null = null;
  const finish = () => {
    if (mouthTimer) clearInterval(mouthTimer);
    useMicLevel.getState().setAiSpeaking(false);
    if (currentAudio === audio) currentAudio = null;
    onEnd?.();
  };
  audio.onplaying = () => {
    useMicLevel.getState().setAiSpeaking(true);
    if (mouthTimer) return;
    // Same rule as the streaming path: the mouth follows real audio progress,
    // so a stalled or silently-failed clip ends rather than animating forever.
    let lastTime = -1;
    let stalledTicks = 0;
    mouthTimer = setInterval(() => {
      const advanced = !audio.paused && !audio.ended && audio.currentTime > lastTime;
      if (advanced) {
        lastTime = audio.currentTime;
        stalledTicks = 0;
        useMicLevel.getState().markBoundary();
        return;
      }
      if (++stalledTicks >= STALL_TICKS) finish();
    }, MOUTH_PULSE_MS);
  };
  audio.onended = finish;
  audio.onerror = finish;
  void audio.play().catch(finish);
}

/**
 * When each provider last failed.
 *
 * Purpose is to stop hammering a provider that is genuinely down — Inworld ran
 * out of credits on 2026-07-28 and every reply burned a 502 first. It is a
 * COOL-OFF, not a blacklist: the previous version put the provider in a Set
 * that nothing ever cleared, so a single transient 502 silenced the real voice
 * for the rest of the page's life.
 */
const failedAt = new Map<string, number>();
const COOL_OFF_MS = 60_000;

const coolingOff = (provider: string | null): boolean => {
  if (!provider) return false;
  const at = failedAt.get(provider);
  return at !== undefined && Date.now() - at < COOL_OFF_MS;
};

/**
 * Voice the tutor's reply: the student's own provider via POST /voice/tts,
 * browser speechSynthesis only when that fails (the text stays on screen either
 * way). Pass the exact text shown in chat so audio matches the words.
 *
 * ── Why there is no fallback to a different provider ────────────────────────
 * There used to be one, and it was the bug. `alternateProvider` returned the
 * first provider in the catalogue that wasn't the one that had just failed —
 * OpenAI — so a single Inworld hiccup moved the student onto a completely
 * different voice for the rest of the session, and marked Inworld dead so it
 * never came back. Mid-lesson the tutor simply became someone else.
 *
 * The provider is a property of the subscription (Manjusha, 2026-07-29):
 * premium is Cartesia, basic is Inworld, everywhere, end to end. So the retry
 * is against the SAME provider, and if that fails we drop to the browser voice
 * — audibly degraded, but honest, and it recovers on the next utterance once
 * the cool-off passes. Switching a student to a voice their plan doesn't
 * include is never the right answer.
 */
export function speakTutor(text: string, onEnd?: () => void): void {
  if (!text) { onEnd?.(); return; }
  stopTutorSpeech();
  if (!ttsApiEnabled()) { speakBrowser(text, onEnd); return; }
  const token = speakToken;
  const { provider, voice } = effectiveVoice();

  // Don't spend a request on a provider that failed moments ago.
  if (coolingOff(provider)) { speakBrowser(text, onEnd); return; }

  const attempt = (allowRetry: boolean): void => {
    synthesizeSpeech(text, { provider, voice })
      .then((audioBase64) => {
        if (token !== speakToken) return; // superseded while fetching
        if (audioBase64) {
          failedAt.delete(provider ?? '');
          playBase64Mp3(audioBase64, onEnd);
          return;
        }
        giveUp(allowRetry);
      })
      .catch(() => {
        if (token !== speakToken) return;
        giveUp(allowRetry);
      });
  };

  const giveUp = (allowRetry: boolean): void => {
    if (allowRetry) {
      console.warn(`[tts] ${provider ?? 'default'} failed; retrying once`);
      attempt(false);
      return;
    }
    if (provider) failedAt.set(provider, Date.now());
    console.warn(`[tts] ${provider ?? 'default'} unavailable; using browser speech`);
    speakBrowser(text, onEnd);
  };

  attempt(true);
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
    stopTutorSpeech(); // streamed audio supersedes any browser/REST tutor voice
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

  /**
   * Pulse the avatar's mouth ONLY while the audio is genuinely advancing.
   *
   * This used to pulse on a bare interval, stopped only by onended/onerror. If
   * playback stalled or never really started — a dropped stream, a browser that
   * refused to play — neither fired, so the tutor's face kept talking with no
   * sound and no text behind it (reported 2026-07-28). Watching currentTime
   * means the mouth can only move when there is really something to hear, and
   * a stall ends the utterance instead of hanging.
   */
  private startMouth(): void {
    if (this.mouthTimer) return;
    let lastTime = -1;
    let stalledTicks = 0;
    this.mouthTimer = setInterval(() => {
      const audio = this.audio;
      const advanced = Boolean(audio && !audio.paused && !audio.ended && audio.currentTime > lastTime);
      if (advanced) {
        lastTime = audio!.currentTime;
        stalledTicks = 0;
        useMicLevel.getState().markBoundary();
        return;
      }
      if (++stalledTicks >= STALL_TICKS) this.finish();
    }, MOUTH_PULSE_MS);
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

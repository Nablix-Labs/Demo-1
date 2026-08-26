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

import { stripTutorMarkdown } from '@/lib/tutorMarkdown';
import { useMicLevel } from '@/store/useMicLevel';
import { useAuthStore } from '@/store/useAuthStore';
import { defaultVoiceForTier, providersForTier } from '@/lib/voiceOptions';
import { useNumeraStore } from '@/store/useNumeraStore';
import { synthesizeSpeech } from '@/lib/api';

/** The voice server always streams MP3. */
const AUDIO_MIME = 'audio/mpeg';
/** Mouth-flutter pace while streamed audio plays (no real word boundaries in mp3). */
// Mouth pulses with no audio progress before we treat the utterance as over.
const STALL_TICKS = 6;

const MOUTH_PULSE_MS = 180;

/**
 * How fast the tutor speaks, as a multiplier. 1 is the natural pace.
 *
 * Module-level rather than a store value because it has to be readable from
 * inside the audio callbacks below, which run outside React, and because it is
 * a playback setting rather than lesson state — nothing about the session
 * changes when a student slows the tutor down.
 *
 * Applied at both playback sites. Setting it on only the generated-audio path
 * would mean a student who had slowed the tutor down heard it snap back to full
 * speed the moment the provider failed over to browser speech, which is exactly
 * when they would be least able to follow it.
 */
let tutorRate = 1;

/** Clamped to what both engines can actually do — speechSynthesis ignores
 *  anything outside 0.1–10 and generated audio distorts badly past 2×. */
export function setTutorSpeechRate(rate: number): void {
  tutorRate = Math.min(2, Math.max(0.5, rate));
  // Take effect on the clip already playing, not only the next one: a student
  // reaches for the speed control because THIS sentence is going too fast.
  if (currentAudio) currentAudio.playbackRate = tutorRate;
}

export function tutorSpeechRate(): number {
  return tutorRate;
}

// ── Browser engine (Web Speech API) ──────────────────────────────────────────
export function speakBrowser(text: string, onEnd?: () => void): void {
  if (typeof window === 'undefined' || !('speechSynthesis' in window) || !text) {
    onEnd?.();
    return;
  }
  // The tutor emphasises with **…**; an engine must never be handed the markers.
  const utterance = new SpeechSynthesisUtterance(stripTutorMarkdown(text));
  utterance.rate = tutorRate;
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
  const tier = useAuthStore.getState().tier;
  // A persisted picker choice only counts while its provider is one the
  // student's tier still offers. Without this, everyone who ever picked a
  // Cartesia voice kept getting Cartesia after the 31 Jul switch to Inworld —
  // the stale selection outlived the product decision.
  const offered = new Set(providersForTier(tier).map((p) => p.id as string));
  const chosen = ttsProvider && offered.has(ttsProvider)
    ? { provider: ttsProvider as string | null, voice: ttsVoice as string | null }
    : (() => {
        const tierDefault = defaultVoiceForTier(tier);
        return { provider: tierDefault?.provider ?? null, voice: tierDefault?.voice ?? null };
      })();
  // Session-sticky degradation: if this student's provider has hard-failed
  // (e.g. Cartesia out of credits, live on 31 Jul), speak in the OTHER product
  // voice instead of flapping robot/real every cool-off cycle.
  const downgraded = degradedReplacement(chosen.provider);
  return downgraded ?? chosen;
}

// ── Product-voice degradation (Cartesia ⇄ Inworld) ──────────────────────────
/**
 * What happens when the student's own provider is genuinely down — not a
 * hiccup, but e.g. Cartesia returning 402 quota_exceeded on every call, which
 * has now happened twice (28 and 31 Jul).
 *
 * The old cross-provider fallback was removed for good reasons: it switched
 * silently, to OpenAI (a voice in nobody's plan), and never switched back.
 * This is the deliberate version, different on every point that made that one
 * a bug:
 *
 *   • only between the two PRODUCT voices (premium Cartesia ⇄ basic Inworld —
 *     both voices a Numera student can legitimately hear), never anything else;
 *   • only after the same-provider retry has failed twice in one cool-off
 *     cycle (a transient 502 still just retries);
 *   • sticky for DEGRADE_RECOVERY_MS rather than forever, so topping up the
 *     account brings the right voice back on its own within a few minutes;
 *   • logged loudly, so "the voice changed" is one console line, not a mystery.
 *
 * Without this, a quota outage sounds like: real voice → robot → (60s) → slow
 * robot → … in the diagnostic, and total silence in guided practice. That
 * flip-flopping is what got reported as "Cartesia is not synced with voice".
 */
const PRODUCT_FALLBACK: Record<string, { provider: string; voice: string }> = {
  cartesia: { provider: 'inworld', voice: 'Ashley' },
  inworld: { provider: 'cartesia', voice: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4' }, // Skylar
};
const DEGRADE_RECOVERY_MS = 5 * 60_000;
const degradedAt = new Map<string, number>();

/** The replacement product voice while `provider` is degraded, else null. */
function degradedReplacement(
  provider: string | null,
): { provider: string; voice: string } | null {
  if (!provider) return null;
  const at = degradedAt.get(provider);
  if (at === undefined) return null;
  if (Date.now() - at >= DEGRADE_RECOVERY_MS) {
    degradedAt.delete(provider); // window over — let the real voice try again
    return null;
  }
  return PRODUCT_FALLBACK[provider] ?? null;
}

/** Test hook + the marker speakTutor uses when a provider hard-fails. */
export function markProviderDegraded(provider: string, now = Date.now()): void {
  if (!(provider in PRODUCT_FALLBACK)) return; // never degrade onto non-product voices
  degradedAt.set(provider, now);
  console.warn(
    `[tts] ${provider} is down; speaking as ${PRODUCT_FALLBACK[provider].provider} ` +
      `for the next ${Math.round(DEGRADE_RECOVERY_MS / 60_000)} minutes`,
  );
}

/** Test hook. */
export function resetVoiceDegradation(): void {
  degradedAt.clear();
  failedAt.clear();
}

let currentAudio: HTMLAudioElement | null = null;
let speakToken = 0; // invalidates in-flight TTS fetches when superseded/stopped

/** Stop whichever engine is currently voicing the tutor.
 *
 * "Whichever" includes the STREAMING player. It didn't used to — this only
 * silenced speechSynthesis and the REST <audio>, so every caller that assumed
 * it silences the tutor (student picks up the pen, a hint plays, sign-out,
 * navigation) left the streamed reply talking underneath, and a REST-voiced
 * line then played ON TOP of it: two tutor voices at once. hardStop() silences
 * without firing onIdle, so callers keep owning what happens next. */
export function stopTutorSpeech(): void {
  speakToken++;
  if (typeof window !== 'undefined') window.speechSynthesis?.cancel();
  if (currentAudio) {
    try { currentAudio.pause(); } catch { /* noop */ }
    currentAudio = null;
  }
  tutorAudioStream.hardStop();
  useMicLevel.getState().setAiSpeaking(false);
}

function playBase64Mp3(
  base64: string,
  fallbackText: string,
  onEnd?: () => void,
): void {
  const audio = new Audio(`data:${AUDIO_MIME};base64,${base64}`);
  audio.playbackRate = tutorRate;
  currentAudio = audio;
  let mouthTimer: ReturnType<typeof setInterval> | null = null;
  let settled = false;
  const cleanUp = () => {
    if (mouthTimer) clearInterval(mouthTimer);
    mouthTimer = null;
    useMicLevel.getState().setAiSpeaking(false);
    if (currentAudio === audio) currentAudio = null;
  };
  const finish = () => {
    if (settled) return;
    settled = true;
    cleanUp();
    onEnd?.();
  };
  const speakBlockedAudioInBrowser = () => {
    if (settled) return;
    settled = true;
    cleanUp();
    console.warn('[tts] generated audio playback was blocked; using browser speech');
    speakBrowser(fallbackText, onEnd);
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
  void audio.play().catch(speakBlockedAudioInBrowser);
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
  // Speak the words, not the markdown the tutor wrote them in. The chat bubble
  // renders the same string with the emphasis applied (lib/tutorMarkdown).
  text = stripTutorMarkdown(text);
  stopTutorSpeech();
  if (!ttsApiEnabled()) { speakBrowser(text, onEnd); return; }
  const token = speakToken;
  // effectiveVoice() already accounts for an active degradation window, so a
  // student whose provider is down asks for the replacement voice up front.
  const { provider, voice } = effectiveVoice();

  // Don't spend a request on a provider that failed moments ago.
  if (coolingOff(provider)) { speakBrowser(text, onEnd); return; }

  const attemptWith = (
    p: string | null,
    v: string | null,
    onFail: () => void,
  ): void => {
    synthesizeSpeech(text, { provider: p, voice: v })
      .then((audioBase64) => {
        if (token !== speakToken) return; // superseded while fetching
        if (audioBase64) {
          failedAt.delete(p ?? '');
          playBase64Mp3(audioBase64, text, onEnd);
          return;
        }
        onFail();
      })
      .catch(() => {
        if (token !== speakToken) return;
        onFail();
      });
  };

  // same provider → same provider once more → the OTHER product voice →
  // browser. Each arrow is logged; nothing switches silently.
  attemptWith(provider, voice, () => {
    console.warn(`[tts] ${provider ?? 'default'} failed; retrying once`);
    attemptWith(provider, voice, () => {
      if (provider) failedAt.set(provider, Date.now());
      const replacement = provider ? (markProviderDegraded(provider), degradedReplacement(provider)) : null;
      if (replacement && replacement.provider !== provider) {
        attemptWith(replacement.provider, replacement.voice, () => {
          failedAt.set(replacement.provider, Date.now());
          console.warn('[tts] replacement voice also unavailable; using browser speech');
          speakBrowser(text, onEnd);
        });
        return;
      }
      console.warn(`[tts] ${provider ?? 'default'} unavailable; using browser speech`);
      speakBrowser(text, onEnd);
    });
  });
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
/** How long a reply may sit with NO audio ever having played before the words
 *  are voiced through the fallback chain instead. Covers server-side synthesis
 *  plus first-chunk buffering with room to spare — a healthy stream starts in
 *  well under 3s. */
const AUDIO_ARRIVAL_MS = 12_000;

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
  /** Bumped by every begin()/hardStop(). Async callbacks (play() rejection,
   *  the arrival guard) compare the generation they were created in so a
   *  callback for a superseded reply can never touch the current one. */
  private generation = 0;
  private playbackStarted = false;
  private arrivalGuard: ReturnType<typeof setTimeout> | null = null;
  /** The words this stream is meant to say — spoken via speakTutor if the
   *  server's audio never arrives (streaming TTS failed, e.g. quota). */
  private fallbackText: string | null = null;

  /** A new tutor reply is starting — reset and prepare to receive audio chunks. */
  begin(voiceText?: string): void {
    stopTutorSpeech(); // streamed audio supersedes any browser/REST tutor voice (this also hardStop()s us)
    const myGeneration = ++this.generation;
    this.fallbackText = voiceText?.trim() || null;
    this.playbackStarted = false;

    const supported =
      typeof window !== 'undefined' &&
      typeof MediaSource !== 'undefined' &&
      MediaSource.isTypeSupported(AUDIO_MIME);
    if (!supported) {
      // No MSE (iPhone Safari < 17.1) or no MP3-in-MSE. This used to just
      // return, with `active` still false — every chunk dropped, finishStream a
      // no-op, onIdle NEVER fired. voiceStatus stayed 'speaking' and the mic
      // never reopened: the lesson was dead after one turn. Voice the words
      // through the REST fallback chain instead, and always reach onIdle.
      console.warn('[tts] MediaSource unsupported here; voicing the turn via fallback');
      this.failToFallback(myGeneration);
      return;
    }

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
      this.playbackStarted = true;
      this.clearArrivalGuard();
      useMicLevel.getState().setAiSpeaking(true);
      this.startMouth();
    };
    audio.onended = () => this.finish();
    audio.onerror = () => this.finish();
    void audio.play().catch((err: unknown) => {
      // A rejection here is a real refusal (autoplay policy / unsupported
      // src), not "no data yet" — with MSE the promise stays pending until
      // data lands. It used to be swallowed, and with playback never starting
      // neither the stall detector nor onended could ever run: a silent,
      // permanent 'speaking' deadlock. Route to the fallback voice instead.
      if (myGeneration !== this.generation || this.playbackStarted) return;
      console.warn('[tts] streamed audio play() was refused; voicing via fallback', err);
      this.failToFallback(myGeneration);
    });

    // The last line of defence for the audio phase: the turn watchdog stands
    // down when tutor_response arrives, so if the audio then never comes
    // (server died mid-stream, chunks lost) nothing else would ever end the
    // turn. If nothing has PLAYED by the deadline, speak the text instead.
    this.arrivalGuard = setTimeout(() => {
      this.arrivalGuard = null;
      if (myGeneration !== this.generation || this.playbackStarted) return;
      console.warn('[tts] no streamed audio played within the arrival window; voicing via fallback');
      this.failToFallback(myGeneration);
    }, AUDIO_ARRIVAL_MS);
  }

  /** One tutor_audio_chunk: base64 MP3 bytes at chunk_index. */
  push(chunkIndex: number, base64: string): void {
    if (!this.active) return;
    this.pending.set(chunkIndex, base64ToBytes(base64));
    this.pump();
  }

  /** tutor_audio_end: no more chunks. total<=0 or an error means the server
   *  produced no audio for this turn. */
  finishStream(totalChunks: number, error?: string): void {
    if (!this.active) return;
    if (error || totalChunks <= 0) {
      // The streamed audio never came (streaming TTS failed server-side —
      // Cartesia quota, 31 Jul). This used to just fall silent, so guided
      // practice lost its voice entirely while the diagnostic kept talking.
      // If nothing has played yet, voice the same words through the REST
      // fallback chain (own voice → other product voice → browser).
      if (this.nextIndex === 0) {
        console.warn('[tts] streamed audio failed; voicing the turn via fallback');
        this.failToFallback(this.generation);
      } else {
        this.finish();
      }
      return;
    }
    this.ended = true;
    this.pump();
  }

  /**
   * The stream is dead — voice its words through the REST fallback chain
   * (own voice → other product voice → browser speech) and only report idle
   * once THAT has finished, so the mic can't reopen mid-fallback-sentence.
   * Every no-audio failure (unsupported browser, refused play(), nothing
   * arrived, server-reported TTS error) funnels through here, which is what
   * guarantees onIdle always eventually fires.
   */
  private failToFallback(generation: number): void {
    if (generation !== this.generation) return;
    const speakInstead = this.fallbackText;
    const idle = this.onIdle;
    this.finish();
    if (speakInstead) {
      useMicLevel.getState().setAiSpeaking(true);
      speakTutor(speakInstead, () => {
        useMicLevel.getState().setAiSpeaking(false);
        idle?.();
      });
    }
  }

  /** Stop playback immediately (e.g. student barge-in). */
  stop(): void {
    window.speechSynthesis?.cancel();
    this.finish();
  }

  /**
   * Silence this player without reporting idle — for stopTutorSpeech(), whose
   * callers (student picked up the pen, another line is about to be voiced,
   * sign-out) own what happens to the turn next. finish()/stop() remain the
   * paths that hand the floor back to the student.
   */
  hardStop(): void {
    this.generation++;
    this.stopMouth();
    this.teardown();
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

  /**
   * Called when the tutor has genuinely stopped making sound — cleanly, on
   * error, or on a stall.
   *
   * The mic gate depends on this. Every path that ends a reply funnels through
   * `finish()`, so this fires from all of them (onended, onerror, the stall
   * detector, a failed stream, an explicit stop). That single funnel is the
   * reason the mic cannot be left shut by a reply that died quietly.
   */
  private onIdle: (() => void) | null = null;

  setOnIdle(handler: (() => void) | null): void {
    this.onIdle = handler;
  }

  private finish(): void {
    this.generation++; // invalidate any in-flight play()/arrival callbacks
    this.stopMouth();
    useMicLevel.getState().setAiSpeaking(false);
    this.teardown();
    this.onIdle?.();
  }

  private clearArrivalGuard(): void {
    if (this.arrivalGuard) clearTimeout(this.arrivalGuard);
    this.arrivalGuard = null;
  }

  private stopMouth(): void {
    if (this.mouthTimer) clearInterval(this.mouthTimer);
    this.mouthTimer = null;
  }

  private teardown(): void {
    this.stopMouth();
    this.clearArrivalGuard();
    this.playbackStarted = false;
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

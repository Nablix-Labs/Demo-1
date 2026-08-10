'use client';

/**
 * useVoiceStream — streams raw microphone audio to the voice server (:8004) over
 * the /voice WebSocket, for the server-side STT path (Deepgram).
 *
 * This is the counterpart to useVoiceTurn: where useVoiceTurn does STT in the
 * browser (Web Speech) and fires a REST turn, this hook does no STT at all — it
 * just pushes PCM audio and lets the server transcribe, detect turn ends, and
 * stream back transcript_final / tutor_response / tutor_audio_* messages (handled
 * in useWebSocket).
 *
 * Wire contract (out): { type: 'audio_chunk', data: <base64 PCM16 16kHz mono> },
 * matching the OUT schema documented in useWebSocket. Audio is streamed
 * continuously while active; the server segments turns (Deepgram utterance_end).
 *
 * ScriptProcessorNode is used (deprecated but universally supported and simplest
 * for raw PCM taps) rather than an AudioWorklet, which needs a separately served
 * module — avoided here to keep the frontend self-contained.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMicLevel, MIC_BARS } from '@/store/useMicLevel';
import { audioConstraints } from '@/lib/support/micPreference';

/** Sample rate the voice server / Deepgram expects. */
const TARGET_RATE = 16000;

interface SpeechWindow extends Window {
  webkitAudioContext?: typeof AudioContext;
}

// Average-decimate to the target rate (input is usually 44.1/48kHz).
function downsample(input: Float32Array, inRate: number): Float32Array {
  if (inRate <= TARGET_RATE) return input;
  const ratio = inRate / TARGET_RATE;
  const outLen = Math.floor(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.floor((i + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let j = start; j < end && j < input.length; j++) {
      sum += input[j];
      count++;
    }
    out[i] = count ? sum / count : 0;
  }
  return out;
}

function floatToPcm16(input: Float32Array): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(new ArrayBuffer(input.length * 2));
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true); // little-endian PCM16
  }
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

interface UseVoiceStreamOptions {
  /** Sends one base64 PCM16 16kHz mono frame over the WS (useWebSocket.sendAudioChunk). */
  onAudio: (base64: string) => void;
}

export function useVoiceStream({ onAudio }: UseVoiceStreamOptions) {
  const [active, setActive] = useState(false);
  const supported = typeof window !== 'undefined' && 'mediaDevices' in navigator;

  // Latest callback without re-subscribing the audio graph.
  const onAudioRef = useRef(onAudio);
  useEffect(() => {
    onAudioRef.current = onAudio;
  }, [onAudio]);

  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  /**
   * Whether captured frames are actually SENT. The mic used to be fully torn
   * down and re-acquired on every turn boundary, which cost 100-400ms of dead
   * air per turn — the opening syllable of every answer was simply never
   * captured, and Deepgram graded "It is" instead of "It is 5". The hardware
   * now stays open for the whole session (start/stop = mute/unmute and
   * unmount); turn-taking only flips this flag.
   */
  const transmitting = useRef(true);

  /**
   * Bumped by every stop(). A start() that was awaiting getUserMedia compares
   * the generation it began in against this: if they differ it was cancelled
   * while waiting, and must throw away the stream it just acquired.
   *
   * Without it the mic could go live AFTER being muted — start()'s only guard
   * was `ctxRef.current`, which isn't set until after the await, so a stop()
   * during permission/acquisition cleared nothing and the pending start() then
   * installed a live capture. The student saw "Muted" while the tutor kept
   * hearing them and answering (reported 2026-07-28).
   */
  const generation = useRef(0);
  const starting = useRef(false);

  const stop = useCallback(() => {
    generation.current += 1;
    starting.current = false;
    setActive(false);
    procRef.current?.disconnect();
    procRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    // close() rejects if the context is already closed/closing — that used to
    // surface as an unhandled promise rejection in the console.
    void ctxRef.current?.close().catch(() => { /* already closed */ });
    ctxRef.current = null;
    useMicLevel.getState().setActive(false);
  }, []);

  /** Gate transmission without releasing the hardware (turn-taking). */
  const setTransmitting = useCallback((on: boolean) => {
    transmitting.current = on;
    if (!on) useMicLevel.getState().setLevels(new Array(MIC_BARS).fill(0));
  }, []);

  const start = useCallback(async () => {
    // `starting` is checked synchronously so two calls in the same tick can't
    // both get past the guard and open two microphones.
    if (!supported || ctxRef.current || starting.current) return;
    starting.current = true;
    const myGeneration = generation.current;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints({ echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }),
      });
    } catch (err) {
      starting.current = false;   // permission refused or no device
      // This used to be swallowed whole. A denied or missing mic then looked
      // exactly like the tutor ignoring the student: the panel said
      // "Listening…" while zero audio was being sent. Say so, everywhere.
      const denied = (err as { name?: string })?.name === 'NotAllowedError';
      console.error('[voice] microphone capture failed:', err);
      useMicLevel.getState().setMicError(denied ? 'denied' : 'failed');
      return;
    }
    useMicLevel.getState().setMicError(null);

    // Muted (or unmounted) while we were waiting — release the mic immediately
    // rather than wiring up a capture nobody asked for.
    if (myGeneration !== generation.current) {
      stream.getTracks().forEach((t) => t.stop());
      starting.current = false;
      return;
    }
    streamRef.current = stream;

    const Ctx = window.AudioContext ?? (window as SpeechWindow).webkitAudioContext!;
    /**
     * Ask for the capture rate Deepgram is actually configured for
     * (`encoding=linear16&sample_rate=16000`, streaming_server.py:86-87)
     * instead of taking the hardware's 44.1/48kHz and squashing it ourselves.
     *
     * `downsample()` below is a box average: it sums ~3 input samples per
     * output sample and divides. That is a low-pass filter with a very poor
     * response, so everything above 8kHz folds back into the speech band as
     * aliasing rather than being filtered out. Sibilants and plosives are
     * exactly where that lands, and it is the ASR that pays — garbled,
     * repeated-word transcripts of the kind reported on 7 Aug ("I call BBB.
     * Because that that that has an extra support").
     *
     * Browsers resample in the audio thread with a proper polyphase filter, so
     * asking for 16kHz here hands the job to code built for it. When the
     * browser honours it, `downsample()` sees inRate === TARGET_RATE and
     * returns its input untouched; when it doesn't, the old path still runs.
     * Either way the wire format is unchanged.
     *
     * This does NOT make transcription accurate on its own — model and
     * language are the voice server's to tune. It removes damage we were
     * adding.
     */
    let ctx: AudioContext;
    try {
      try {
        ctx = new Ctx({ sampleRate: TARGET_RATE });
      } catch {
        // Older Safari rejects the option outright rather than ignoring it.
        ctx = new Ctx();
      }
    } catch (err) {
      // Even the bare constructor failed (context limit hit, platform bug).
      // Uncaught, this was an unhandled rejection and a mic held open with no
      // graph behind it.
      console.error('[voice] AudioContext creation failed:', err);
      stream.getTracks().forEach((t) => t.stop());
      starting.current = false;
      useMicLevel.getState().setMicError('failed');
      return;
    }
    ctxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;
    const inRate = ctx.sampleRate;
    // Whether the browser honoured the request is not knowable from the code —
    // say which path is live so a transcription complaint can be checked
    // against it rather than guessed at.
    console.log(
      `[voice] capture ${inRate}Hz → ${TARGET_RATE}Hz`,
      inRate === TARGET_RATE ? '(native, no resampling)' : '(falling back to box-average downsample)',
    );

    proc.onaudioprocess = (e: AudioProcessingEvent) => {
      // Hardware stays open; only transmission is gated (half-duplex). Frames
      // captured while the tutor speaks are dropped here, never sent.
      if (!transmitting.current) return;
      const input = e.inputBuffer.getChannelData(0);
      const down = downsample(input, inRate);
      onAudioRef.current(bytesToBase64(floatToPcm16(down)));

      // Drive the mic-level bars off the same frames so the button stays lively.
      let sum = 0;
      for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.min(1, Math.sqrt(sum / input.length) * 4);
      const levels = new Array(MIC_BARS);
      for (let b = 0; b < MIC_BARS; b++) levels[b] = Math.max(0, rms * (0.7 + 0.6 * Math.random()));
      useMicLevel.getState().setLevels(levels);
    };

    // Route through a muted node so the graph pulls audio without echoing the mic.
    const silent = ctx.createGain();
    silent.gain.value = 0;
    source.connect(proc);
    proc.connect(silent);
    silent.connect(ctx.destination);

    useMicLevel.getState().setActive(true);
    setActive(true);
    starting.current = false;
  }, [supported]);

  // Clean up on unmount.
  useEffect(() => stop, [stop]);

  return { active, supported, start, stop, setTransmitting };
}

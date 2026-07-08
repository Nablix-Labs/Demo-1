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

  const stop = useCallback(() => {
    setActive(false);
    procRef.current?.disconnect();
    procRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void ctxRef.current?.close();
    ctxRef.current = null;
    useMicLevel.getState().setActive(false);
  }, []);

  const start = useCallback(async () => {
    if (!supported || ctxRef.current) return;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    });
    streamRef.current = stream;

    const Ctx = window.AudioContext ?? (window as SpeechWindow).webkitAudioContext!;
    const ctx = new Ctx();
    ctxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;
    const inRate = ctx.sampleRate;

    proc.onaudioprocess = (e: AudioProcessingEvent) => {
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
  }, [supported]);

  // Clean up on unmount.
  useEffect(() => stop, [stop]);

  return { active, supported, start, stop };
}

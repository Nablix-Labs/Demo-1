'use client';

/**
 * useVoiceTurn — hands-free turn detection for the live voice loop.
 *
 * Two engines, deliberately split so the rest of the app doesn't care how a turn
 * ends (see the "ears vs brain" design):
 *   - VAD (Web Audio energy + a silence timer) DECIDES the turn end. When the
 *     student goes quiet past `silenceMs`, the turn is committed.
 *   - Web Speech API provides the TRANSCRIPT only (pure STT — never used to
 *     generate the reply; the backend owns content).
 *
 * On turn end it calls `onTurnEnd(transcript, confidence)` — that's where the
 * caller fires the canvas + transcript to the backend.
 *
 * If/when Aditya's voice layer owns turn detection, only the innards of this
 * hook change; callers keep using `onTurnEnd` unchanged.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useMicLevel, MIC_BARS } from '@/store/useMicLevel';

// ── Minimal Web Speech typings (not in the standard DOM lib) ──────────────────
interface SpeechRecognitionAlternativeLike {
  transcript: string;
  confidence: number;
}
interface SpeechRecognitionResultLike {
  0: SpeechRecognitionAlternativeLike;
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

interface SpeechWindow extends Window {
  webkitSpeechRecognition?: SpeechRecognitionCtor;
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitAudioContext?: typeof AudioContext;
}

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as SpeechWindow;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface UseVoiceTurnOptions {
  onTurnEnd: (transcript: string, confidence?: number) => void;
  /** Silence gap (ms) that counts as "student stopped". Generous so we don't cut kids off. */
  silenceMs?: number;
  /** RMS energy (post-gain) above this counts as speech. Lower = more sensitive. */
  energyThreshold?: number;
  /** Input gain applied before detection so normal (not loud) speech registers. */
  micGain?: number;
}

export function useVoiceTurn({
  onTurnEnd,
  silenceMs = 1300,
  energyThreshold = 0.009,
  micGain = 2.4,
}: UseVoiceTurnOptions) {
  const [active, setActive] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const supported =
    typeof window !== 'undefined' && getRecognitionCtor() !== null && 'mediaDevices' in navigator;

  // Latest callback without re-subscribing the audio graph.
  const onTurnEndRef = useRef(onTurnEnd);
  useEffect(() => {
    onTurnEndRef.current = onTurnEnd;
  }, [onTurnEnd]);

  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const activeRef = useRef(false);

  // Turn state
  const transcriptRef = useRef('');
  const confidenceRef = useRef<number | undefined>(undefined);
  const hadSpeechRef = useRef(false);
  const lastVoiceTsRef = useRef(0);

  const commitTurn = useCallback(() => {
    const text = transcriptRef.current.trim();
    transcriptRef.current = '';
    hadSpeechRef.current = false;
    setSpeaking(false);
    if (text) onTurnEndRef.current(text, confidenceRef.current);
  }, []);

  const stop = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    setSpeaking(false);
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    void audioCtxRef.current?.close();
    audioCtxRef.current = null;
    transcriptRef.current = '';
    hadSpeechRef.current = false;
    useMicLevel.getState().setActive(false);
  }, []);

  const start = useCallback(async () => {
    if (activeRef.current || !supported) return;

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    streamRef.current = stream;

    const Ctx = window.AudioContext ?? (window as SpeechWindow).webkitAudioContext!;
    const audioCtx = new Ctx();
    audioCtxRef.current = audioCtx;
    const source = audioCtx.createMediaStreamSource(stream);
    // Boost the signal before detection so normal-volume speech clears the bar.
    const gain = audioCtx.createGain();
    gain.gain.value = micGain;
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.75;
    source.connect(gain);
    gain.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const freq = new Uint8Array(analyser.frequencyBinCount);
    useMicLevel.getState().setActive(true);
    let lastLevelPush = 0;

    // Transcript engine (STT only).
    const RecognitionCtor = getRecognitionCtor();
    if (RecognitionCtor) {
      const recognition = new RecognitionCtor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';
      recognition.onresult = (e) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const result = e.results[i];
          if (result.isFinal) {
            transcriptRef.current += result[0].transcript;
            confidenceRef.current = result[0].confidence;
          }
        }
      };
      recognition.onend = () => {
        // Web Speech stops itself periodically; keep it alive while we're active.
        if (activeRef.current) {
          try {
            recognition.start();
          } catch {
            /* already starting */
          }
        }
      };
      recognitionRef.current = recognition;
      recognition.start();
    }

    activeRef.current = true;
    setActive(true);
    lastVoiceTsRef.current = performance.now();

    // VAD loop: decide turn-end by silence.
    const tick = () => {
      if (!activeRef.current) return;
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();

      // Drive the listening bar from real input (throttled ~30fps).
      if (now - lastLevelPush > 33) {
        lastLevelPush = now;
        analyser.getByteFrequencyData(freq);
        const maxBin = Math.min(freq.length, 220); // speech energy ≈ up to ~2.4kHz
        const per = maxBin / MIC_BARS;
        const levels = new Array(MIC_BARS);
        for (let b = 0; b < MIC_BARS; b++) {
          const start = Math.floor(b * per);
          const end = Math.max(start + 1, Math.floor((b + 1) * per));
          let s = 0;
          for (let i = start; i < end; i++) s += freq[i];
          levels[b] = Math.min(1, (s / (end - start) / 255) * 1.6);
        }
        useMicLevel.getState().setLevels(levels);
      }

      if (rms > energyThreshold) {
        hadSpeechRef.current = true;
        lastVoiceTsRef.current = now;
        if (!speaking) setSpeaking(true);
      } else if (hadSpeechRef.current && now - lastVoiceTsRef.current > silenceMs) {
        commitTurn(); // student went quiet → fire the turn
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [supported, energyThreshold, micGain, silenceMs, speaking, commitTurn]);

  // Clean up on unmount.
  useEffect(() => stop, [stop]);

  return { active, speaking, supported, start, stop };
}

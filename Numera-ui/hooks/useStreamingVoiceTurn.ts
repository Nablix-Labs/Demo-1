'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? '';
const STUDENT_ID = 'ST001';
const TARGET_SAMPLE_RATE = 16000;
const NO_SPEECH_TIMEOUT_MS = 10000;
const MIN_TURN_MS = 2500;

export interface StreamingTutorResponse {
  type: 'tutor_response';
  transcript: string;
  normalized_expression: string | null;
  confidence: number;
  text: string;
  voice_text: string;
  audio_base64: string | null;
  needs_clarification: boolean;
  tts_latency_ms: number | null;
  total_pipeline_ms: number;
}

interface UseStreamingVoiceTurnOptions {
  sessionId: string | null;
  studentId?: string;
  onStudentTranscript: (transcript: string, confidence?: number) => void;
  onTutorResponse: (response: StreamingTutorResponse) => void;
  onError?: (message: string) => void;
  silenceMs?: number;
  energyThreshold?: number;
}

interface SpeechWindow extends Window {
  webkitAudioContext?: typeof AudioContext;
}

function downsample(input: Float32Array, inputSampleRate: number): Float32Array {
  if (inputSampleRate === TARGET_SAMPLE_RATE) return input;

  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    output[i] = input[Math.floor(i * ratio)] ?? 0;
  }

  return output;
}

function pcm16(samples: Float32Array): ArrayBuffer {
  const output = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i] ?? 0));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output.buffer;
}

export function useStreamingVoiceTurn({
  sessionId,
  studentId = STUDENT_ID,
  onStudentTranscript,
  onTutorResponse,
  onError,
  silenceMs = 1300,
  energyThreshold = 0.015,
}: UseStreamingVoiceTurnOptions) {
  const [active, setActive] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const supported =
    typeof window !== 'undefined' &&
    Boolean(WS_URL) &&
    Boolean(sessionId) &&
    'mediaDevices' in navigator &&
    typeof WebSocket !== 'undefined';

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const activeRef = useRef(false);
  const stopSentRef = useRef(false);
  const lastVoiceTsRef = useRef(0);
  const audioStartedTsRef = useRef(0);
  const hadSpeechRef = useRef(false);
  const transcriptSentRef = useRef(false);
  const tutorResponseHandledRef = useRef(false);
  const finalTranscriptRef = useRef('');
  const finalConfidenceRef = useRef<number | undefined>(undefined);
  const speakingRef = useRef(false);
  const onStudentTranscriptRef = useRef(onStudentTranscript);
  const onTutorResponseRef = useRef(onTutorResponse);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onStudentTranscriptRef.current = onStudentTranscript;
    onTutorResponseRef.current = onTutorResponse;
    onErrorRef.current = onError;
  }, [onStudentTranscript, onTutorResponse, onError]);

  const stopInput = useCallback((sendStop: boolean, closeSocket: boolean) => {
    activeRef.current = false;
    speakingRef.current = false;
    setActive(false);
    setSpeaking(false);

    if (sendStop && !stopSentRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
      stopSentRef.current = true;
    }

    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    void audioCtxRef.current?.close();
    processorRef.current = null;
    sourceRef.current = null;
    streamRef.current = null;
    audioCtxRef.current = null;

    if (closeSocket) {
      wsRef.current?.close(1000, 'voice stopped');
      wsRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    stopInput(true, true);
  }, [stopInput]);

  const start = useCallback(async () => {
    if (!supported || activeRef.current || !sessionId || wsRef.current !== null) return;

    const ws = new WebSocket(`${WS_URL}?session_id=${encodeURIComponent(sessionId)}&student_id=${encodeURIComponent(studentId)}`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    stopSentRef.current = false;
    transcriptSentRef.current = false;
    tutorResponseHandledRef.current = false;
    finalTranscriptRef.current = '';
    finalConfidenceRef.current = undefined;
    hadSpeechRef.current = false;

    ws.onopen = async () => {
      ws.send(JSON.stringify({ type: 'start', language: 'en' }));

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const Ctx = window.AudioContext ?? (window as SpeechWindow).webkitAudioContext!;
      const audioCtx = new Ctx();
      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      streamRef.current = stream;
      audioCtxRef.current = audioCtx;
      sourceRef.current = source;
      processorRef.current = processor;
      activeRef.current = true;
      speakingRef.current = false;
      setActive(true);
      audioStartedTsRef.current = performance.now();
      lastVoiceTsRef.current = audioStartedTsRef.current;

      processor.onaudioprocess = (event) => {
        if (!activeRef.current || ws.readyState !== WebSocket.OPEN) return;

        const input = event.inputBuffer.getChannelData(0);
        let sum = 0;
        for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
        const rms = Math.sqrt(sum / input.length);
        const now = performance.now();
        const turnAgeMs = now - audioStartedTsRef.current;

        if (rms > energyThreshold) {
          hadSpeechRef.current = true;
          lastVoiceTsRef.current = now;
          if (!speakingRef.current) {
            speakingRef.current = true;
            setSpeaking(true);
          }
        }
        const shouldStop =
          (turnAgeMs >= MIN_TURN_MS && hadSpeechRef.current && now - lastVoiceTsRef.current > silenceMs) ||
          (turnAgeMs >= NO_SPEECH_TIMEOUT_MS && !hadSpeechRef.current);
        if (shouldStop) {
          stopInput(true, false);
          return;
        }

        ws.send(pcm16(downsample(input, audioCtx.sampleRate)));
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);
    };

    ws.onmessage = (event) => {
      if (typeof event.data !== 'string') return;
      const message = JSON.parse(event.data) as Record<string, unknown>;

      if (message.type === 'final_transcript') {
        const text = String(message.text ?? '').trim();
        if (text) finalTranscriptRef.current = text;
        finalConfidenceRef.current = Number(message.confidence ?? 0);
      }

      if (message.type === 'tutor_response') {
        if (tutorResponseHandledRef.current) return;
        tutorResponseHandledRef.current = true;

        const response = message as unknown as StreamingTutorResponse;
        const transcript = response.transcript || finalTranscriptRef.current;
        if (!transcriptSentRef.current && transcript) {
          transcriptSentRef.current = true;
          onStudentTranscriptRef.current(transcript, response.confidence || finalConfidenceRef.current);
        }
        onTutorResponseRef.current(response);
        ws.close(1000, 'turn complete');
      }

      if (message.type === 'error') {
        onErrorRef.current?.(String(message.message ?? 'Voice streaming failed.'));
        ws.close(4000, 'voice error');
      }
    };

    ws.onerror = () => {
      onErrorRef.current?.('Voice WebSocket failed.');
      stopInput(false, true);
    };

    ws.onclose = () => {
      stopInput(false, false);
      wsRef.current = null;
    };
  }, [
    supported,
    sessionId,
    studentId,
    energyThreshold,
    silenceMs,
    stopInput,
  ]);

  useEffect(() => stop, [stop]);

  return { active, speaking, supported, start, stop };
}

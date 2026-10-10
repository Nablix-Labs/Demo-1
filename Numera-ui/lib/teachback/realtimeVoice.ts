import { api } from '@/lib/api';
import { audioConstraints } from '@/lib/support/micPreference';

/**
 * Live voice for Teach-Back: OpenAI Realtime is only the ears and the mouth.
 * It transcribes the student (its turn detection decides when they have
 * finished) and speaks text the backend already approved. Grading and the
 * tutor's words come from the normal /interaction call, as in Standard mode.
 */

interface RealtimeSession {
  client_secret: string;
  calls_url: string;
  response_timeout_seconds: number;
  request_retry_count: number;
  speaker_instructions: string;
  filler_words: string[];
}

interface RealtimeEvent {
  type: string;
  transcript?: string;
  delta?: string;
  logprobs?: Array<{ logprob: number }>;
  item_id?: string;
  error?: { message?: string; code?: string };
  response?: { status?: string };
}

export interface TeachBackVoiceEvents {
  /** Words heard so far in the student's turn, for a live caption. */
  onHeard: (text: string) => void;
  /** The student finished speaking and it was transcribed. */
  onTranscript: (text: string, confidence: number | null) => void;
  /** The connection is gone; the screen has to reconnect. */
  onClosed: () => void;
}

/** Spoken words per second, used only when playback never reports its end. */
const SPOKEN_WORDS_PER_SECOND = 2.2;

/** Geometric-mean token probability: the 0–1 confidence the backend checks. */
export function transcriptConfidence(logprobs: RealtimeEvent['logprobs']): number | null {
  if (!logprobs?.length || logprobs.some((entry) => !Number.isFinite(entry.logprob) || entry.logprob > 0)) return null;
  return Math.exp(logprobs.reduce((sum, entry) => sum + entry.logprob, 0) / logprobs.length);
}

/** A turn made only of fillers ("um", "okay so") is thinking out loud, not an answer. */
export function isOnlyFiller(text: string, fillerWords: string[]): boolean {
  const words = text.toLowerCase().match(/[a-z']+/g) ?? [];
  return words.length > 0 && !/\d/.test(text) && words.every((word) => fillerWords.includes(word));
}

/** The request that makes Realtime say exactly the approved words and nothing else. */
export function speakRequest(speakerInstructions: string, text: string) {
  return {
    type: 'response.create',
    response: {
      conversation: 'none',
      output_modalities: ['audio'],
      input: [],
      instructions: `${speakerInstructions}\n<say>${text}</say>`,
    },
  };
}

export class TeachBackVoiceConnection {
  private readonly peer: RTCPeerConnection;
  private readonly channel: RTCDataChannel;
  private readonly microphone: MediaStream;
  private readonly player: HTMLAudioElement;
  private readonly session: RealtimeSession;
  private readonly events: TeachBackVoiceEvents;
  private heard = '';
  private closed = false;
  private speech: { done: () => void; timer: ReturnType<typeof setTimeout>; words: number } | null = null;

  private constructor(peer: RTCPeerConnection, channel: RTCDataChannel, microphone: MediaStream,
    player: HTMLAudioElement, session: RealtimeSession, events: TeachBackVoiceEvents) {
    this.peer = peer;
    this.channel = channel;
    this.microphone = microphone;
    this.player = player;
    this.session = session;
    this.events = events;
    channel.onmessage = (event: MessageEvent<string>) => this.receive(event.data);
    channel.onclose = () => this.close();
    peer.onconnectionstatechange = () => {
      if (peer.connectionState === 'failed') this.close();
    };
  }

  static async connect(sessionId: string, studentId: string, events: TeachBackVoiceEvents): Promise<TeachBackVoiceConnection> {
    const microphone = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints({ echoCancellation: true, noiseSuppression: true, autoGainControl: true }),
    });
    let session: RealtimeSession;
    try {
      session = (await api.post<RealtimeSession>('/voice/teach-back/session', { session_id: sessionId, student_id: studentId })).data;
    } catch (error: unknown) {
      microphone.getTracks().forEach((track) => track.stop());
      throw error;
    }
    const peer = new RTCPeerConnection();
    const player = new Audio();
    player.autoplay = true;
    peer.ontrack = (event) => { player.srcObject = event.streams[0]; };
    const channel = peer.createDataChannel('oai-events');
    microphone.getAudioTracks().forEach((track) => { track.enabled = false; peer.addTrack(track, microphone); });
    const connection = new TeachBackVoiceConnection(peer, channel, microphone, player, session, events);
    try {
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      if (!offer.sdp) throw new Error('The browser could not create a voice connection offer.');
      const answer = await TeachBackVoiceConnection.exchangeOffer(session, offer.sdp);
      await peer.setRemoteDescription({ type: 'answer', sdp: answer });
      await new Promise<void>((resolve, reject) => {
        if (channel.readyState === 'open') { resolve(); return; }
        const timer = setTimeout(() => reject(new Error('Voice connection timed out.')), session.response_timeout_seconds * 1000);
        channel.onopen = () => { clearTimeout(timer); resolve(); };
        channel.onerror = () => { clearTimeout(timer); reject(new Error('Voice data channel failed to open.')); };
      });
      return connection;
    } catch (error: unknown) {
      connection.close(false);
      throw error;
    }
  }

  private static async exchangeOffer(session: RealtimeSession, sdp: string): Promise<string> {
    const attempts = session.request_retry_count + 1;
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      let response: Response;
      try {
        response = await fetch(session.calls_url, {
          method: 'POST', body: sdp,
          headers: { Authorization: `Bearer ${session.client_secret}`, 'Content-Type': 'application/sdp' },
          signal: AbortSignal.timeout(session.response_timeout_seconds * 1000),
        });
      } catch (error: unknown) {
        if (!(error instanceof TypeError || (error instanceof DOMException && error.name === 'TimeoutError')) || attempt === attempts) throw error;
        console.warn('teach_back_voice_connection_retry', { attempt, attempts });
        continue;
      }
      const body = await response.text();
      if (response.ok) return body;
      if (response.status >= 500 && attempt < attempts) {
        console.warn('teach_back_voice_connection_retry', { attempt, attempts, status: response.status });
        continue;
      }
      throw new Error(`Voice connection failed (${response.status}): ${body}`);
    }
    throw new Error('Voice connection exhausted its configured retries.');
  }

  /** The student's turn: open the mic. Turn detection ends the turn by itself. */
  listen(): void {
    if (this.closed || this.speech) return;
    this.heard = '';
    this.send({ type: 'input_audio_buffer.clear' });
    this.setMic(true);
  }

  /** Close the mic and drop anything half-said. */
  pause(): void {
    if (this.closed) return;
    this.setMic(false);
    this.send({ type: 'input_audio_buffer.clear' });
  }

  /** Say the backend-approved words. Resolves when playback ends, or fails, so the lesson never stalls. */
  speak(text: string): Promise<void> {
    this.pause();
    this.finishSpeech();
    if (this.closed) return Promise.resolve();
    return new Promise<void>((resolve) => {
      const timer = setTimeout(() => this.finishSpeech(), this.session.response_timeout_seconds * 1000);
      this.speech = { done: resolve, timer, words: text.split(/\s+/).length };
      this.send(speakRequest(this.session.speaker_instructions, text));
    });
  }

  /** The student cut in: stop talking now. */
  stopSpeaking(): void {
    if (!this.speech) return;
    this.send({ type: 'response.cancel' });
    this.send({ type: 'output_audio_buffer.clear' });
    this.finishSpeech();
  }

  close(notify = true): void {
    if (this.closed) return;
    this.closed = true;
    this.finishSpeech();
    this.microphone.getTracks().forEach((track) => track.stop());
    this.player.srcObject = null;
    this.channel.close();
    this.peer.close();
    if (notify) this.events.onClosed();
  }

  private setMic(on: boolean): void {
    this.microphone.getAudioTracks().forEach((track) => { track.enabled = on; });
  }

  private send(event: object): void {
    if (this.channel.readyState === 'open') this.channel.send(JSON.stringify(event));
  }

  private finishSpeech(): void {
    const speech = this.speech;
    if (!speech) return;
    this.speech = null;
    clearTimeout(speech.timer);
    speech.done();
  }

  private receive(raw: string): void {
    let event: RealtimeEvent;
    try { event = JSON.parse(raw) as RealtimeEvent; } catch { return; }
    switch (event.type) {
      case 'conversation.item.input_audio_transcription.delta':
        this.heard += event.delta ?? '';
        this.events.onHeard(this.heard);
        break;
      case 'input_audio_buffer.committed':
        // Turn over: nothing else is heard until the tutor has answered.
        this.setMic(false);
        break;
      case 'conversation.item.input_audio_transcription.completed': {
        // Each turn is graded on its own by the backend; keep the Realtime conversation empty.
        if (event.item_id) this.send({ type: 'conversation.item.delete', item_id: event.item_id });
        const text = (event.transcript ?? '').trim();
        this.heard = '';
        this.events.onHeard('');
        if (text && !isOnlyFiller(text, this.session.filler_words)) this.events.onTranscript(text, transcriptConfidence(event.logprobs));
        else this.listen();
        break;
      }
      case 'conversation.item.input_audio_transcription.failed':
        console.warn('teach_back_voice_transcription_failed', event.error);
        this.events.onHeard('');
        this.listen();
        break;
      case 'output_audio_buffer.stopped':
        this.finishSpeech();
        break;
      case 'response.done':
        if (!this.speech) break;
        if (event.response?.status !== 'completed') { this.finishSpeech(); break; }
        // Normally output_audio_buffer.stopped ends the speech; never wait much past the words' length.
        clearTimeout(this.speech.timer);
        this.speech.timer = setTimeout(() => this.finishSpeech(), (this.speech.words / SPOKEN_WORDS_PER_SECOND + 2) * 1000);
        break;
      case 'error':
        console.warn('teach_back_voice_error', event.error);
        this.finishSpeech();
        break;
      default:
        break;
    }
  }
}

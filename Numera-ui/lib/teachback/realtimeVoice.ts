import { api } from '@/lib/api';

export interface TeachBackReply {
  evaluation: {
    understanding_status: 'UNDERSTOOD' | 'MISCONCEPTION' | null;
    misconception_detected: boolean;
    error_code: string | null;
    unmapped_misconception_description: string | null;
  };
  tutor_message: string;
  tutor_message_voice: string;
  next_action: 'ASK_TEACH_BACK' | 'DISCUSS_AND_CLARIFY' | 'ASK_REEXPLANATION'
    | 'NEXT_MICRO_SKILL' | 'MOVE_TO_PHASE_2' | 'RETURN_TO_ORIENTATION';
}

export interface TeachBackRealtimeContext {
  instructions: string;
  teach_back_id: string;
  micro_skill_id: string;
  tool_name: string;
}

interface RealtimeSession {
  client_secret: string;
  calls_url: string;
  response_timeout_seconds: number;
  request_retry_count: number;
  context: TeachBackRealtimeContext;
}

interface RealtimeEvent {
  type: string;
  transcript?: string;
  logprobs?: Array<{ logprob: number }>;
  name?: string;
  arguments?: string;
  call_id?: string;
  item_id?: string;
  error?: { message: string };
  response?: { status: string; status_details?: { error?: { message: string } } };
}

export interface RealtimeTurn {
  transcript: string;
  transcriptConfidence: number | null;
  reply: TeachBackReply;
  callId: string;
}

interface PendingTurn {
  transcript: string;
  transcriptConfidence: number | null;
  reply: TeachBackReply | null;
  callId: string | null;
  resolve: (turn: RealtimeTurn) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

/** Owns only the OpenAI connection; backend validation owns all teaching decisions. */
export class TeachBackVoiceConnection {
  private readonly peer: RTCPeerConnection;
  private readonly channel: RTCDataChannel;
  private readonly microphone: MediaStream;
  private readonly timeoutMs: number;
  private pending: PendingTurn | null;
  private context: TeachBackRealtimeContext;

  private constructor(peer: RTCPeerConnection, channel: RTCDataChannel, microphone: MediaStream, session: RealtimeSession) {
    this.peer = peer;
    this.channel = channel;
    this.microphone = microphone;
    this.timeoutMs = session.response_timeout_seconds * 1000;
    this.context = session.context;
    this.pending = null;
    channel.onmessage = (event: MessageEvent<string>) => this.receive(event.data);
    channel.onclose = () => this.fail(new Error('The voice connection closed. Reconnect before trying again.'));
    peer.onconnectionstatechange = () => {
      if (peer.connectionState === 'failed' || peer.connectionState === 'disconnected') {
        this.fail(new Error('The voice connection was interrupted. Reconnect before trying again.'));
      }
    };
  }

  static async connect(sessionId: string, studentId: string): Promise<TeachBackVoiceConnection> {
    const microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
    let session: RealtimeSession;
    try {
      const response = await api.post<RealtimeSession>('/voice/teach-back/session', { session_id: sessionId, student_id: studentId });
      session = response.data;
    } catch (error: unknown) {
      microphone.getTracks().forEach((track) => track.stop());
      throw error;
    }
    const peer = new RTCPeerConnection();
    const channel = peer.createDataChannel('oai-events');
    microphone.getAudioTracks().forEach((track) => { track.enabled = false; peer.addTrack(track, microphone); });
    const connection = new TeachBackVoiceConnection(peer, channel, microphone, session);
    try {
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      if (!offer.sdp) throw new Error('The browser could not create a voice connection offer.');
      const answerText = await TeachBackVoiceConnection.exchangeOffer(session, offer.sdp);
      await peer.setRemoteDescription({ type: 'answer', sdp: answerText });
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Voice connection timed out.')), connection.timeoutMs);
        channel.onopen = () => { clearTimeout(timer); resolve(); };
        channel.onerror = () => { clearTimeout(timer); reject(new Error('Voice data channel failed to open.')); };
        if (channel.readyState === 'open') { clearTimeout(timer); resolve(); }
      });
      channel.onerror = () => connection.fail(new Error('The voice data channel failed. Reconnect before trying again.'));
      return connection;
    } catch (error: unknown) {
      connection.close();
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
        console.warn('teach_back_voice_connection_retry', { attempt, attempts, url: session.calls_url });
        continue;
      }
      const body = await response.text();
      if (response.ok) return body;
      if (response.status >= 500 && attempt < attempts) {
        console.warn('teach_back_voice_connection_retry', { attempt, attempts, status: response.status, response_body: body });
        continue;
      }
      throw new Error(`Voice connection failed (${response.status}) at ${session.calls_url}: ${body}`);
    }
    throw new Error('Voice connection exhausted its configured retries.');
  }

  get lessonContext(): TeachBackRealtimeContext { return this.context; }

  async refreshContext(sessionId: string, studentId: string): Promise<void> {
    const response = await api.post<TeachBackRealtimeContext>('/voice/teach-back/context', { session_id: sessionId, student_id: studentId });
    this.context = response.data;
    this.channel.send(JSON.stringify({ type: 'session.update', session: { type: 'realtime', instructions: this.context.instructions } }));
  }

  startListening(): void {
    if (this.pending) throw new Error('Wait for the current teachback reply.');
    if (this.channel.readyState !== 'open') throw new Error('Connect voice before speaking.');
    this.channel.send(JSON.stringify({ type: 'input_audio_buffer.clear' }));
    this.microphone.getAudioTracks().forEach((track) => { track.enabled = true; });
  }

  finishListening(): Promise<RealtimeTurn> {
    this.microphone.getAudioTracks().forEach((track) => { track.enabled = false; });
    const turn = this.waitForTurn('');
    this.channel.send(JSON.stringify({ type: 'input_audio_buffer.commit' }));
    // Transcription must finish first so the backend receives final student evidence.
    return turn;
  }

  submitText(text: string): Promise<RealtimeTurn> {
    const turn = this.waitForTurn(text);
    this.channel.send(JSON.stringify({ type: 'conversation.item.create', item: {
      type: 'message', role: 'user', content: [{ type: 'input_text', text }],
    } }));
    this.channel.send(JSON.stringify({ type: 'response.create' }));
    return turn;
  }

  acknowledge(callId: string, message: string): void {
    this.channel.send(JSON.stringify({ type: 'conversation.item.create', item: {
      type: 'function_call_output', call_id: callId, output: message,
    } }));
  }

  close(): void {
    this.fail(new Error('Voice session closed.'));
    this.microphone.getTracks().forEach((track) => track.stop());
    this.channel.close();
    this.peer.close();
  }

  private waitForTurn(transcript: string): Promise<RealtimeTurn> {
    if (this.pending) throw new Error('A teachback turn is already in progress.');
    if (this.channel.readyState !== 'open') throw new Error('The voice connection is not open.');
    return new Promise<RealtimeTurn>((resolve, reject) => {
      const timer = setTimeout(() => this.fail(new Error('The voice tutor timed out. Reconnect before trying again.')), this.timeoutMs);
      this.pending = { transcript, transcriptConfidence: null, reply: null, callId: null, resolve, reject, timer };
    });
  }

  private receive(raw: string): void {
    let event: RealtimeEvent;
    try { event = JSON.parse(raw) as RealtimeEvent; }
    catch (error: unknown) { this.fail(new Error(`Invalid voice event: ${String(error)}`)); return; }
    if (event.type === 'error' || event.type === 'conversation.item.input_audio_transcription.failed') {
      this.fail(new Error(event.error?.message ?? 'Voice transcription failed.'));
      return;
    }
    if (!this.pending) return;
    if (event.type === 'conversation.item.input_audio_transcription.completed') {
      this.pending.transcript = event.transcript ?? '';
      if (event.logprobs?.length) {
        if (event.logprobs.some((entry) => !Number.isFinite(entry.logprob) || entry.logprob > 0)) {
          this.fail(new Error('The transcription returned invalid confidence data.'));
          return;
        }
        // Geometric mean token probability supplies the existing 0–1 confidence check.
        this.pending.transcriptConfidence = Math.exp(event.logprobs.reduce((sum, entry) => sum + entry.logprob, 0) / event.logprobs.length);
      }
      this.channel.send(JSON.stringify({ type: 'response.create' }));
    } else if (event.type === 'response.function_call_arguments.done') {
      if (event.name !== this.context.tool_name || !event.arguments || !event.call_id) {
        this.fail(new Error('The voice tutor returned an unexpected tool result.'));
        return;
      }
      try {
        if (this.pending.reply) throw new Error('The voice tutor returned multiple results for one explanation.');
        this.pending.reply = JSON.parse(event.arguments) as TeachBackReply;
        this.pending.callId = event.call_id;
      } catch (error: unknown) { this.fail(new Error(`Invalid tutor reply: ${String(error)}`)); }
    } else if (event.type === 'response.done') {
      const pending = this.pending;
      if (event.response?.status !== 'completed' || !pending.reply || !pending.callId) {
        this.fail(new Error(event.response?.status_details?.error?.message ?? 'The voice tutor did not complete a teachback result.'));
        return;
      }
      clearTimeout(pending.timer);
      this.pending = null;
      pending.resolve({ transcript: pending.transcript, transcriptConfidence: pending.transcriptConfidence, reply: pending.reply, callId: pending.callId });
    }
  }

  private fail(error: Error): void {
    if (!this.pending) return;
    clearTimeout(this.pending.timer);
    this.pending.reject(error);
    this.pending = null;
  }
}

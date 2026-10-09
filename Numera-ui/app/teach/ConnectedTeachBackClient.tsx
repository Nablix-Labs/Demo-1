'use client';

import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { api, getSession, sendInteraction, studentId, type InteractionPayload, type InteractionResponse } from '@/lib/api';
import { acceptResponse } from '@/lib/interactionPresentation';
import { syncBackendSession } from '@/hooks/useDemoTutor';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { usePhaseRouting } from '@/lib/usePhaseRouting';
import { tutorSay } from '@/lib/tutorSpeech';
import { stopTutorSpeech } from '@/lib/tts';
import { TeachBackVoiceConnection, type RealtimeTurn } from '@/lib/teachback/realtimeVoice';
import { useNumeraStore } from '@/store/useNumeraStore';

type TeachBackMode = 'standard' | 'realtime';
type Turn = { role: 'student' | 'tutor'; text: string };

function interactionFor(text: string, source: 'TEXT' | 'VOICE', confidence: number | null): InteractionPayload {
  const state = useNumeraStore.getState();
  if (!state.sessionId || state.currentPhase !== 'TEACH_BACK') throw new Error('Open an active teachback lesson first.');
  return {
    session_id: state.sessionId, student_id: studentId(),
    interaction_type: 'TEACH_BACK_SUBMISSION', input_source: source,
    ...(source === 'TEXT' ? { text_input: text } : { voice_transcript: text, transcript_final: true }),
    ...(source === 'VOICE' && confidence !== null ? { transcript_confidence: confidence } : {}),
    current_phase: 'TEACH_BACK', concept_id: state.activeConceptId,
    question_id: state.activeQuestionId, hint_count: 0,
    turn_id: state.beginSubmissionTurn(), previous_tutor_turn_id: state.lastTutorTurnId,
  };
}

export default function ConnectedTeachBackClient() {
  usePhaseRouting();
  const sessionId = useNumeraStore((state) => state.sessionId);
  const phase = useNumeraStore((state) => state.currentPhase);
  const [mode, setMode] = useState<TeachBackMode>('standard');
  const [realtimeEnabled, setRealtimeEnabled] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connection = useRef<TeachBackVoiceConnection | null>(null);
  const inFlight = useRef(false);
  const retrySave = useRef<(() => Promise<InteractionResponse>) | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; connection.current?.close(); connection.current = null; stopTutorSpeech(); };
  }, []);

  useEffect(() => {
    if (!sessionId) { setError('Return to your lesson to start a teachback session.'); return; }
    let cancelled = false;
    setBusy(true);
    void Promise.all([
      getSession(sessionId, studentId(), {}),
      api.get<{ realtime_enabled: boolean }>('/voice/teach-back/options'),
    ]).then(([session, options]) => {
      if (cancelled) return;
      syncBackendSession(session);
      setRealtimeEnabled(options.data.realtime_enabled);
      setTurns([{ role: 'tutor', text: session.message }]);
      setError(null);
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : 'Could not load teachback.');
    }).finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; connection.current?.close(); connection.current = null; };
  }, [sessionId]);

  const presentReply = (response: InteractionResponse): void => {
    if (!mounted.current || !acceptResponse(response)) return;
    setTurns((previous) => [...previous, { role: 'tutor', text: response.message }]);
    useNumeraStore.getState().addTranscriptMessage({ role: 'ai', text: response.message });
    setSpeaking(true);
    tutorSay(response.message_voice, { onEnd: () => {
      if (mounted.current) { syncBackendSession(response); setSpeaking(false); }
    } });
  };

  const saveReply = async (): Promise<void> => {
    const save = retrySave.current;
    if (!save) throw new Error('No teachback reply is waiting to be saved.');
    const response = await save();
    retrySave.current = null;
    presentReply(response);
    if (connection.current && response.current_phase === 'TEACH_BACK' && sessionId) {
      await connection.current.refreshContext(sessionId, studentId());
    } else {
      connection.current?.close(); connection.current = null; setConnected(false);
    }
  };

  const recordRealtime = async (turn: RealtimeTurn, source: 'TEXT' | 'VOICE'): Promise<void> => {
    const active = connection.current;
    if (!active) throw new Error('The voice connection closed before the reply could be saved.');
    const context = active.lessonContext;
    const interaction: InteractionPayload = {
      ...interactionFor(turn.transcript, source, turn.transcriptConfidence),
      ...(turn.transcriptConfidence !== null ? { transcript_confidence: turn.transcriptConfidence } : {}),
    };
    setTurns((previous) => [...previous, { role: 'student', text: turn.transcript }]);
    useNumeraStore.getState().addTranscriptMessage({ role: 'student', text: turn.transcript });
    retrySave.current = async () => {
      const response = await api.post<InteractionResponse>('/voice/teach-back/result', {
        interaction, teach_back_id: context.teach_back_id, micro_skill_id: context.micro_skill_id, reply: turn.reply,
      });
      if (connection.current === active) active.acknowledge(turn.callId, JSON.stringify({ accepted: true, tutor_message: response.data.message }));
      return response.data;
    };
    await saveReply();
  };

  const reportError = (cause: unknown): void => {
    if (axios.isAxiosError(cause) && cause.response?.status === 422) {
      retrySave.current = null;
    }
    setError(cause instanceof Error ? cause.message : 'The teachback request failed.');
    connection.current?.close(); connection.current = null;
    setConnected(false); setListening(false);
  };

  const submitStandard = async (value: string, source: 'TEXT' | 'VOICE', confidence: number | null): Promise<void> => {
    if (inFlight.current || !value.trim()) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const interaction = interactionFor(value, source, confidence);
      setTurns((previous) => [...previous, { role: 'student', text: value }]);
      useNumeraStore.getState().addTranscriptMessage({ role: 'student', text: value });
      retrySave.current = async () => {
        const response = await sendInteraction(interaction);
        if (response.status === 'STALE_TURN') throw new Error('This turn is out of date. Refresh the lesson before continuing.');
        return response;
      };
      await saveReply(); setText('');
    } catch (cause: unknown) { reportError(cause); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const standardVoice = useVoiceTurn({ onTurnEnd: (transcript: string, confidence: number | undefined): void => {
    standardVoice.stop();
    setListening(false);
    if (transcript) void submitStandard(transcript, 'VOICE', confidence ?? null);
  } });

  const connectVoice = async (): Promise<void> => {
    if (!sessionId || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try {
      const active = await TeachBackVoiceConnection.connect(sessionId, studentId());
      if (!mounted.current || useNumeraStore.getState().sessionId !== sessionId) { active.close(); return; }
      connection.current = active; setConnected(true);
    } catch (cause: unknown) { reportError(cause); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const toggleMic = async (): Promise<void> => {
    if (mode === 'standard') {
      if (standardVoice.active) standardVoice.finish();
      else { stopTutorSpeech(); standardVoice.start(); setListening(true); }
      return;
    }
    const active = connection.current;
    if (!active || inFlight.current) return;
    if (!listening) {
      try { active.startListening(); setListening(true); }
      catch (cause: unknown) { reportError(cause); }
      return;
    }
    setListening(false); inFlight.current = true; setBusy(true); setError(null);
    try { await recordRealtime(await active.finishListening(), 'VOICE'); }
    catch (cause: unknown) { reportError(cause); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const submitText = async (): Promise<void> => {
    if (mode === 'standard') { await submitStandard(text, 'TEXT', null); return; }
    const active = connection.current;
    if (!active || inFlight.current || !text.trim()) return;
    inFlight.current = true; setBusy(true); setError(null);
    try { await recordRealtime(await active.submitText(text), 'TEXT'); setText(''); }
    catch (cause: unknown) { reportError(cause); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const retry = async (): Promise<void> => {
    if (inFlight.current || !sessionId) return;
    inFlight.current = true; setBusy(true); setError(null);
    try { await getSession(sessionId, studentId(), {}); await saveReply(); }
    catch (cause: unknown) { reportError(cause); }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  };

  const disabled = busy || speaking || Boolean(retrySave.current) || phase !== 'TEACH_BACK';
  return (
    <main className="flex-1 overflow-y-auto bg-[#FFF8EE] p-6" aria-label="Teachback">
      <div className="mx-auto flex max-w-2xl flex-col gap-5">
        <h1 className="text-xl font-semibold text-focus-navy">Your turn to teach</h1>
        <label className="flex items-center gap-3 text-sm">Conversation mode
          <select value={mode} disabled={disabled || listening} onChange={(event) => {
            standardVoice.stop();
            connection.current?.close(); connection.current = null; setConnected(false);
            setMode(event.target.value as TeachBackMode); setError(null);
          }} className="rounded-lg border bg-white p-2">
            <option value="standard">Standard</option>
            {realtimeEnabled && <option value="realtime">Realtime voice</option>}
          </select>
        </label>
        <div className="space-y-3" aria-live="polite">
          {turns.map((turn, index) => <p key={index} className={`rounded-xl p-4 ${turn.role === 'tutor' ? 'bg-white' : 'bg-focus-navy text-white'}`}>{turn.text}</p>)}
        </div>
        {error && <p role="alert" className="text-action-orange">{error}</p>}
        {retrySave.current && <button disabled={busy} onClick={() => void retry()} className="rounded-lg border bg-white p-3">Retry saving this reply</button>}
        {mode === 'realtime' && !connected && <button disabled={disabled} onClick={() => void connectVoice()} className="rounded-lg bg-focus-navy p-3 text-white">Connect voice</button>}
        <form onSubmit={(event) => { event.preventDefault(); void submitText(); }} className="flex gap-2">
          <input value={text} onChange={(event) => setText(event.target.value)} maxLength={500}
            disabled={disabled || listening || (mode === 'realtime' && !connected)} placeholder="Explain the idea in your own words…" aria-label="Your explanation" className="min-w-0 flex-1 rounded-lg border p-3" />
          <button type="submit" disabled={disabled || listening || !text.trim() || (mode === 'realtime' && !connected)} className="rounded-lg bg-focus-navy px-4 text-white">Send</button>
        </form>
        <button disabled={disabled || (mode === 'realtime' ? !connected : !standardVoice.supported)} onClick={() => void toggleMic()} className="rounded-lg border bg-white p-3">
          {listening ? 'Finish explanation' : 'Speak your explanation'}
        </button>
        <p className="text-sm text-slate-blue">{busy ? 'Waiting for your tutor…' : speaking ? 'Your tutor is speaking…' : listening ? 'Listening. Select “Finish explanation” when you are ready.' : 'Take your time. You can speak or type.'}</p>
      </div>
    </main>
  );
}

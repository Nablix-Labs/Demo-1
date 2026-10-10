'use client';

/**
 * Teach-Back on the live backend: the student explains the idea back to
 * Numera, by voice or text, and the backend decides what happens next.
 *
 * The screen follows the phase the backend returns and never counts turns
 * itself: TEACH_BACK stays here, CONCEPT_ORIENTATION (a second misconception)
 * goes back to orientation for that skill, GUIDED_PRACTICE (everything
 * understood) moves on. The global phase router does the navigation once the
 * reply has been spoken. No canvas, score, attempt counter or hint ladder.
 *
 * Live voice only changes the ears and the mouth: Realtime hears the student
 * and says the approved reply, while every turn is graded by the same
 * /interaction call as Standard mode.
 *
 * Request rules and failure handling live in lib/teachback/connected.ts.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Check, GraduationCap, Mic, MicOff, RotateCw, Send } from 'lucide-react';
import { api, getSession, studentId, type InteractionPayload, type InteractionResponse } from '@/lib/api';
import { acceptResponse } from '@/lib/interactionPresentation';
import { adoptSessionRecord, sendSynchronizedInteraction, syncBackendSession } from '@/hooks/useDemoTutor';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { useMicLevel } from '@/store/useMicLevel';
import { phaseAnnouncement, withTransitionVoice } from '@/lib/phaseTransition';
import { tutorSay } from '@/lib/tutorSpeech';
import { stopTutorSpeech } from '@/lib/tts';
import { TeachBackVoiceConnection } from '@/lib/teachback/realtimeVoice';
import {
  restoredLines, teachBackFailure, teachBackFailureMessage, teachBackPayload,
  type TeachBackLine, type TeachBackSource,
} from '@/lib/teachback/connected';
import { PupilMark, Thinking } from '@/components/teach/TeachMarks';
import { useAuthStore } from '@/store/useAuthStore';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

type Mode = 'standard' | 'realtime';

/** A turn that failed in a way that may not have been saved: resend it as-is. */
interface PendingTurn {
  studentText: string;
  previousTutorTurnId: string | null;
  send: () => Promise<InteractionResponse>;
}

/** Longest we wait for the tutor's voice to end before unlocking or moving on anyway. */
const HANDOFF_FALLBACK_MS = 20_000;

export default function ConnectedTeachBackClient() {
  const sessionId = useNumeraStore((s) => s.sessionId);
  const phase = useNumeraStore((s) => s.currentPhase);
  const [lines, setLines] = useState<TeachBackLine[]>([]);
  const [opening, setOpening] = useState<{ text: string; voice: string } | null>(null);
  const [started, setStarted] = useState(false);
  const [mode, setMode] = useState<Mode>('standard');
  const [realtimeEnabled, setRealtimeEnabled] = useState(false);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [connected, setConnected] = useState(false);
  // Both modes work like the lesson mic: hands-free while on, and a tap pauses it without sending.
  const [micPaused, setMicPaused] = useState(false);
  const [heard, setHeard] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const [done, setDone] = useState(false);
  const connection = useRef<TeachBackVoiceConnection | null>(null);
  const inFlight = useRef(false);
  const hintCount = useRef(0);
  const conceptId = useRef<string>('');
  const mounted = useRef(true);
  const endRef = useRef<HTMLDivElement>(null);
  const onHeardTurn = useRef<(text: string, confidence: number | null) => void>(() => {});

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      connection.current?.close();
      connection.current = null;
      stopTutorSpeech();
    };
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [lines, busy, heard]);

  /** GET the session: runs the backend's pending recovery and re-adopts its phase and history. */
  const refresh = useCallback(async () => {
    const id = useNumeraStore.getState().sessionId;
    if (!id) return null;
    const rec = await getSession(id, studentId());
    adoptSessionRecord(rec);
    conceptId.current = rec.concept_id;
    hintCount.current = rec.hint_count ?? 0;
    if (mounted.current) setLines(restoredLines(rec));
    return rec;
  }, []);

  // `/teach` is a focus route: AuthGate never mounts, so rehydrate the auth
  // store here or a direct load sends the anonymous bearer (as orientation does).
  useEffect(() => { void useAuthStore.persist.rehydrate(); }, []);

  useEffect(() => {
    if (!sessionId) { setError('Go back to your lesson to start teaching.'); setLoadFailed(true); return; }
    let cancelled = false;
    setBusy(true);
    setError(null);
    void (async () => {
      try {
        const [rec, options] = await Promise.all([
          refresh(),
          api.get<{ realtime_enabled: boolean }>('/voice/teach-back/options').catch(() => ({ data: { realtime_enabled: false } })),
        ]);
        if (cancelled || !rec) return;
        setRealtimeEnabled(Boolean(options.data.realtime_enabled));
        // Arriving from orientation, the handoff queued this line for speech.
        // Claim it here, or the guided screen would speak it later.
        const claimed = useNumeraStore.getState().claimPendingTutorSpeech();
        const restored = restoredLines(rec);
        const fresh = restored.filter((l) => l.role === 'student').length === 0;
        if (fresh && rec.message?.trim()) {
          setOpening({ text: rec.message, voice: rec.message_voice?.trim() || claimed || rec.message });
        } else {
          setStarted(true); // a reload mid-conversation: no intro, no replayed voice
        }
        setLoadFailed(false);
      } catch (cause) {
        if (cancelled) return;
        setError(teachBackFailureMessage(teachBackFailure(cause)));
        setLoadFailed(true);
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, refresh]);

  const speak = useCallback((voice: string, onEnd?: () => void) => {
    setSpeaking(true);
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      if (mounted.current) setSpeaking(false);
      onEnd?.();
    };
    const live = connection.current;
    if (live) void live.speak(voice).then(finish);
    else tutorSay(voice, { onEnd: finish });
    // Audio can be blocked or never report its end; never leave the input locked.
    window.setTimeout(finish, HANDOFF_FALLBACK_MS);
  }, []);

  const begin = () => {
    setStarted(true);
    if (opening) speak(opening.voice); // a click, so the browser allows audio
  };

  const present = useCallback((response: InteractionResponse) => {
    if (!acceptResponse(response)) return;
    hintCount.current = response.hint_count ?? hintCount.current;
    const announcement = phaseAnnouncement(response, 'TEACH_BACK');
    const voice = withTransitionVoice(announcement, response.message_voice || response.message);
    const added: TeachBackLine[] = [{ role: 'tutor', text: response.message }];
    if (announcement && announcement.text !== response.message) added.push({ role: 'tutor', text: announcement.text });
    if (mounted.current) setLines((prev) => [...prev, ...added]);
    const store = useNumeraStore.getState();
    added.forEach((l) => store.addTranscriptMessage({ role: 'ai', text: l.text }));

    if (response.current_phase === 'TEACH_BACK') {
      // Take the new tutor turn now, so the next answer points at it.
      syncBackendSession(response);
      speak(voice);
      return;
    }
    // Leaving Teach-Back. Hold the route until Numera has finished speaking,
    // but take its turn id now so nothing sent meanwhile is stale.
    store.setTutorTurn(response.tutor_turn_id ?? store.lastTutorTurnId, { expects: false, allow: false });
    if (mounted.current && response.current_phase === 'GUIDED_PRACTICE') setDone(true);
    speak(voice, () => {
      connection.current?.close(false);
      connection.current = null;
      if (mounted.current) setConnected(false);
      syncBackendSession(response);
    });
  }, [speak]);

  /** Send a student turn; on failure refresh first, then keep or drop it. */
  const runTurn = useCallback(async (studentText: string, send: () => Promise<InteractionResponse>) => {
    const previousTutorTurnId = useNumeraStore.getState().lastTutorTurnId;
    try {
      const response = await send();
      setPending(null);
      present(response);
    } catch (cause) {
      const action = teachBackFailure(cause);
      let rec = null;
      try { rec = await refresh(); } catch { /* keep the screen as it is */ }
      const savedAnyway = rec != null && (rec.last_tutor_turn_id ?? null) !== previousTutorTurnId;
      if (action === 'retry' && rec == null) {
        // Could not reach the server at all: the screen is unchanged, keep the turn.
        setPending({ studentText, previousTutorTurnId, send });
      } else if (action === 'retry' && !savedAnyway && rec?.current_phase === 'TEACH_BACK') {
        // refresh() replaced the lines from the server; put the unsaved answer back.
        setLines((prev) => [...prev, { role: 'student', text: studentText }]);
        setPending({ studentText, previousTutorTurnId, send });
      } else {
        setPending(null);
      }
      if (!savedAnyway) setError(teachBackFailureMessage(action));
    }
  }, [present, refresh]);

  const payloadFor = (value: string, source: TeachBackSource, confidence?: number | null): InteractionPayload => {
    const s = useNumeraStore.getState();
    if (!s.sessionId || s.currentPhase !== 'TEACH_BACK') throw new Error('Teach-Back is not active.');
    return teachBackPayload({ text: value, source, confidence }, {
      sessionId: s.sessionId,
      studentId: studentId(),
      conceptId: conceptId.current || s.activeConceptId,
      hintCount: hintCount.current,
      turnId: s.beginSubmissionTurn(),
      previousTutorTurnId: s.lastTutorTurnId,
    });
  };

  const submitStandard = async (value: string, source: TeachBackSource, confidence?: number | null) => {
    if (inFlight.current || !value.trim()) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const payload = payloadFor(value, source, confidence);
      setLines((prev) => [...prev, { role: 'student', text: value.trim() }]);
      useNumeraStore.getState().addTranscriptMessage({ role: 'student', text: value.trim() });
      setText('');
      // Same object on every retry, so the backend recognises it (turn_id + content).
      // sendSynchronizedInteraction already resends once on a transient failure.
      await runTurn(value.trim(), () => sendSynchronizedInteraction(payload));
    } catch (cause) {
      setError(teachBackFailureMessage(teachBackFailure(cause)));
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  // Standard: the student went quiet, so send what they said after anything they paused into the box.
  const voice = useVoiceTurn({
    onTurnEnd: (transcript, confidence) => {
      setHeard('');
      const full = [text.trim(), transcript.trim()].filter(Boolean).join(' ');
      if (full) void submitStandard(full, 'VOICE', confidence);
    },
    onInterim: setHeard,
  });
  const listening = mode === 'standard' && voice.active;

  /** Standard: pause without sending; the words heard so far move into the box to edit, send or add to. */
  const pauseStandard = (typed?: string) => {
    const words = (useMicLevel.getState().caption || heard).trim();
    setText((t) => [(typed ?? t).trim(), words].filter(Boolean).join(' '));
    setHeard('');
    setMicPaused(true);
  };

  onHeardTurn.current = (transcript, confidence) => { void submitStandard(transcript, 'VOICE', confidence); };

  const guarded = async (work: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try { await work(); } catch (cause) {
      setError(teachBackFailureMessage(teachBackFailure(cause)));
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const connectVoice = async () => {
    const id = useNumeraStore.getState().sessionId;
    if (!id || busy) return;
    setBusy(true);
    setError(null);
    try {
      const live = await TeachBackVoiceConnection.connect(id, studentId(), {
        onHeard: (text) => { if (mounted.current) setHeard(text); },
        onTranscript: (text, confidence) => onHeardTurn.current(text, confidence),
        onClosed: () => {
          connection.current = null;
          if (!mounted.current) return;
          setConnected(false);
          setHeard('');
          setError('Live voice disconnected. Press Start live voice to carry on, or switch to Standard.');
        },
      });
      if (!mounted.current || useNumeraStore.getState().sessionId !== id) { live.close(false); return; }
      connection.current = live;
      setMicPaused(false);
      setConnected(true);
    } catch (cause) {
      console.warn('teach_back_voice_connect_failed', cause);
      setError('Live voice could not start. Check that the microphone is allowed, or switch to Standard.');
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const toggleMic = () => {
    if (mode === 'standard') {
      if (micPaused) setMicPaused(false); // listens once Numera has finished talking
      else pauseStandard();
      return;
    }
    if (speaking) { connection.current?.stopSpeaking(); return; }
    setMicPaused((paused) => !paused);
  };

  const submitText = async () => {
    await submitStandard(text, 'TEXT');
  };

  const retry = () => guarded(async () => {
    const turn = pending;
    if (!turn) return;
    setPending(null);
    await runTurn(turn.studentText, turn.send);
  });

  const reload = () => {
    setLoadFailed(false);
    setError(null);
    void guarded(async () => { await refresh(); setStarted(true); });
  };

  const active = phase === 'TEACH_BACK' && !done;
  const locked = !active || busy || speaking || pending !== null || !started;
  const needsConnect = mode === 'realtime' && !connected;
  // Live voice: the mic is open exactly when it is the student's turn.
  const liveListening = mode === 'realtime' && connected && !locked && !micPaused;

  useEffect(() => {
    const live = connection.current;
    if (!live) return;
    if (liveListening) live.listen();
    else live.pause();
  }, [liveListening, connected]);
  // Standard is half-duplex like the lesson: the mic listens only while the floor is the student's.
  const standardListening = mode === 'standard' && !micPaused && voice.supported && !locked;
  const { start: startVoice, stop: stopVoice } = voice;
  useEffect(() => {
    if (standardListening) void startVoice();
    else if (mode === 'standard') { stopVoice(); setHeard(''); }
  }, [standardListening, mode, startVoice, stopVoice]);
  const lastTutor = [...lines].reverse().find((l) => l.role === 'tutor');
  const status = busy ? 'Numera is thinking…' : speaking
    ? (mode === 'realtime' ? 'Numera is talking… press the mic to cut in.' : 'Numera is talking…')
    : liveListening ? 'Listening. Just talk, Numera will know when you have finished.'
    : mode === 'realtime' && connected && micPaused ? 'Mic paused. Press the mic to talk.'
    : listening ? 'Listening. Numera hears you when you stop talking. Tap the mic to pause.'
    : mode === 'standard' && micPaused && voice.supported ? 'Mic paused. Tap the mic to talk, or type your explanation.'
    : 'Take your time. Speak or type your explanation.';
  const micOn = mode === 'realtime' ? liveListening : listening;

  return (
    <main className="relative flex flex-1 flex-col overflow-hidden bg-[#FFF8EE]" aria-label="Teach-Back">
      <header className="flex items-center gap-3 border-b border-[#F1E3C8] px-6 py-4">
        <PupilMark size={40} bob={busy} puzzled={Boolean(lastTutor && lastTutor.text.trim().endsWith('?'))} />
        <div className="min-w-0 flex-1">
          <h1 className="text-[17px] font-bold leading-tight text-focus-navy">Your turn to teach</h1>
          <p className="text-[12.5px] text-slate-blue">Explain it to Numera in your own words.</p>
        </div>
        {realtimeEnabled && (
          <div className="flex rounded-full bg-[#F6E9D0] p-1 text-[12px] font-semibold" role="group" aria-label="Voice mode">
            {(['standard', 'realtime'] as const).map((m) => (
              <button
                key={m}
                disabled={busy || speaking || listening || pending !== null}
                aria-pressed={mode === m}
                onClick={() => { voice.stop(); connection.current?.close(false); connection.current = null; setConnected(false); setHeard(''); setMode(m); setError(null); }}
                className={cn('rounded-full px-3 py-1.5 transition-colors', mode === m ? 'bg-white text-focus-navy shadow-sm' : 'text-[#9A7B45]')}
              >
                {m === 'standard' ? 'Standard' : 'Live voice'}
              </button>
            ))}
          </div>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-3" aria-live="polite">
          {lines.map((line, i) => (
            <div key={i} className={cn('flex items-end gap-2.5', line.role === 'student' ? 'justify-end' : 'justify-start')}>
              {line.role === 'tutor' && <PupilMark size={28} />}
              <p
                className={cn(
                  'max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-[14.5px] leading-relaxed',
                  line.role === 'tutor'
                    ? 'rounded-bl-md border border-[#F1E3C8] bg-white text-ink'
                    : 'rounded-br-md bg-focus-navy text-white',
                )}
              >
                {line.text}
              </p>
            </div>
          ))}
          {heard && (
            <div className="flex justify-end">
              <p className="max-w-[80%] rounded-2xl rounded-br-md bg-focus-navy/60 px-4 py-3 text-[14.5px] leading-relaxed text-white">{heard}</p>
            </div>
          )}
          {busy && started && (
            <div className="flex items-end gap-2.5">
              <PupilMark size={28} bob />
              <span className="rounded-2xl rounded-bl-md border border-[#F1E3C8] bg-white px-4 py-3"><Thinking /></span>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="border-t border-[#F1E3C8] bg-[#FFF8EE] px-6 pb-6 pt-3">
        <div className="mx-auto max-w-2xl">
          {error && (
            <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 rounded-xl bg-[#FFE9D6] px-4 py-2.5 text-[13px] text-[#8A4B08]">
              <span className="flex-1">{error}</span>
              {pending && (
                <button onClick={() => void retry()} disabled={busy} className="inline-flex items-center gap-1.5 rounded-full bg-action-orange px-3.5 py-1.5 text-[12.5px] font-semibold text-white disabled:opacity-50">
                  <RotateCw size={13} /> Send again
                </button>
              )}
              {loadFailed && sessionId && (
                <button onClick={reload} disabled={busy} className="inline-flex items-center gap-1.5 rounded-full bg-action-orange px-3.5 py-1.5 text-[12.5px] font-semibold text-white disabled:opacity-50">
                  <RotateCw size={13} /> Try again
                </button>
              )}
            </div>
          )}

          {needsConnect && started && active ? (
            <button
              onClick={() => void connectVoice()}
              disabled={busy}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-focus-navy py-3 text-[14px] font-semibold text-white disabled:opacity-50"
            >
              <Mic size={16} /> Start live voice
            </button>
          ) : (
            <form onSubmit={(e) => { e.preventDefault(); void submitText(); }} className="flex items-center gap-2 rounded-full border border-[#EAD6B2] bg-white p-1.5 pl-2">
              <button
                type="button"
                onClick={toggleMic}
                disabled={mode === 'realtime'
                  ? !active || busy || pending !== null || !started
                  : !active || !started || !voice.supported}
                aria-label={mode === 'realtime' && speaking ? 'Stop Numera talking' : micPaused ? 'Turn the mic on' : 'Pause the mic'}
                aria-pressed={!micPaused}
                title={mode === 'standard' && !micPaused && locked ? 'The mic listens when Numera has finished' : undefined}
                className={cn(
                  'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full transition disabled:opacity-40',
                  micOn ? 'bg-action-orange text-white'
                    : mode === 'standard' && micPaused ? 'bg-[#F3EBDD] text-[#9A7B45]'
                    : mode === 'standard' ? 'bg-action-orange/50 text-white'
                    : 'bg-[#FFF1DC] text-action-orange',
                )}
              >
                {mode === 'standard' && micPaused ? <MicOff size={17} /> : micOn ? <Mic size={17} className="animate-pulse" /> : <Mic size={17} />}
              </button>
              <input
                value={text}
                // Typing pauses the Standard mic, keeping what it heard.
                onChange={(e) => (listening ? pauseStandard(e.target.value) : setText(e.target.value))}
                maxLength={500}
                disabled={locked || (mode === 'realtime' && Boolean(heard))}
                placeholder="Explain the idea in your own words…"
                aria-label="Your explanation"
                className="min-w-0 flex-1 bg-transparent px-2 text-[14.5px] text-ink outline-none placeholder:text-[#B9A27A]"
              />
              <button
                type="submit"
                disabled={locked || !text.trim()}
                aria-label="Send to Numera"
                className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-highlight-amber text-white transition hover:brightness-105 disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </form>
          )}
          <p className="mt-2 text-center text-[12px] text-[#9A7B45]">{status}</p>
        </div>
      </div>

      {!started && opening && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#FFF8EE]/85 backdrop-blur-sm">
          <div className="teach-pop w-[420px] max-w-[90%] px-8 text-center">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-highlight-amber/15">
              <GraduationCap size={26} className="text-action-orange" />
            </div>
            <h2 className="text-[24px] font-bold leading-tight text-focus-navy">Your turn to teach</h2>
            <p className="mt-2.5 text-[13.5px] leading-relaxed text-slate-blue">
              You&apos;ve just seen the idea. Now explain it back to Numera in your own words: talk or type. There&apos;s no
              score. Numera just wants to understand.
            </p>
            <button
              onClick={begin}
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-action-orange px-6 py-3 text-[14px] font-semibold text-white transition hover:brightness-105"
            >
              Start teaching <ArrowRight size={16} strokeWidth={2.2} />
            </button>
          </div>
        </div>
      )}

      {done && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-[#FFF8EE]/90 backdrop-blur-sm">
          <div className="teach-pop px-8 text-center">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-success-sage/20">
              <Check size={28} className="text-success-sage" strokeWidth={2.5} />
            </div>
            <h2 className="text-[24px] font-bold text-focus-navy">You taught it!</h2>
            <p className="mt-2 text-[13.5px] text-slate-blue">Next, some questions to practise with Numera.</p>
          </div>
        </div>
      )}
    </main>
  );
}

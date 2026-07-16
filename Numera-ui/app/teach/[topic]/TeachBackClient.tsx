'use client';

/**
 * Teacher Mode (TEACH_BACK) — role reversal. After the orientation video the
 * student teaches the concept back to Numera, who plays a curious learner and
 * asks one question at a time. The screen renders whatever the tutor turn
 * returns and follows the phase it hands back; it never scores the explanation
 * (that's the Tutor Engine). See lib/teachback/teachApi.ts.
 *
 * The palette deliberately turns warm here: the lesson is cool and tutor-led,
 * so when the student takes over as teacher, amber (Numera's "aha" accent)
 * leads. That flip is the whole signal — you're in charge now.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Mic, PencilLine, Send, ArrowRight, Check, GraduationCap, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useFlowNav } from '@/lib/useFlowNav';
import { useVoiceTurn } from '@/hooks/useVoiceTurn';
import { CURRICULUM } from '@/lib/curriculum';
import {
  submitTeachTurn,
  teachOpening,
  type TeachTurnResponse,
  type TeachInputSource,
} from '@/lib/teachback/teachApi';
import { cn } from '@/lib/cn';

const DrawingCanvas = dynamic(() => import('@/components/Canvas/DrawingCanvas'), { ssr: false });

type Turn = { role: 'tutor' | 'student'; text: string; action?: TeachTurnResponse['action'] };

// How many student turns the mock takes to reach guided practice (for the dots).
const TARGET_TURNS = 5;

export default function TeachBackClient({ topicId }: { topicId: string }) {
  const { goStage } = useFlowNav();
  const setCanvasExporter = useNumeraStore((s) => s.setCanvasExporter);
  const canvasExporter = useNumeraStore((s) => s.canvasExporter);
  const topicTitle = CURRICULUM.find((t) => t.id === topicId)?.title ?? 'this topic';

  const [started, setStarted] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [current, setCurrent] = useState<TeachTurnResponse | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [turnNumber, setTurnNumber] = useState(0);
  const [boardOpen, setBoardOpen] = useState(false);
  const [done, setDone] = useState(false);

  const historyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns.length]);

  const begin = () => {
    const opening = teachOpening();
    setCurrent(opening);
    setTurns([{ role: 'tutor', text: opening.student_facing_response, action: opening.action }]);
    setStarted(true);
  };

  const submit = useCallback(
    async (payloadText: string, source: TeachInputSource) => {
      const value = payloadText.trim();
      if (!value || sending || done) return;
      setText('');
      setTurns((t) => [...t, { role: 'student', text: value }]);
      setSending(true);
      const next = turnNumber + 1;
      setTurnNumber(next);
      const snapshot = source === 'CANVAS' ? canvasExporter?.() ?? null : null;
      const res = await submitTeachTurn({
        session_id: null,
        student_id: 'ST001',
        current_phase: 'TEACH_BACK',
        input_source: source,
        text_input: source === 'TEXT' ? value : undefined,
        voice_transcript: source === 'VOICE' ? value : undefined,
        canvas_snapshot: snapshot,
        turn_number: next,
      });
      setCurrent(res);
      setTurns((t) => [...t, { role: 'tutor', text: res.student_facing_response, action: res.action }]);
      setSending(false);
      if (res.next_phase === 'GUIDED_PRACTICE') {
        setDone(true);
        setTimeout(() => goStage('guided', topicId), 2400);
      } else if (res.next_phase === 'CONCEPT_ORIENTATION') {
        setTimeout(() => goStage('orientation', topicId), 1600);
      }
    },
    [sending, done, turnNumber, canvasExporter, goStage, topicId],
  );

  const voice = useVoiceTurn({
    onTurnEnd: (transcript) => {
      if (transcript) void submit(transcript, 'VOICE');
    },
  });
  const toggleMic = () => (voice.active ? voice.stop() : voice.start());

  const sendBoard = () => {
    setBoardOpen(false);
    void submit('I showed my working on the board.', 'CANVAS');
  };

  const isMisconception = current?.action === 'PRESENT_MISCONCEPTION';
  const priorTurns = turns.slice(0, -1); // everything above the current question

  return (
    <main
      aria-label="Teacher Mode"
      className="flex-1 min-w-0 flex flex-col relative overflow-hidden"
      style={{ background: 'linear-gradient(180deg, #FFFDF8 0%, #FFF8EE 55%, #FFF1DF 100%)' }}
    >
      {/* Top bar */}
      <header className="flex items-center gap-4 px-7 py-4 flex-shrink-0">
        <PupilMark size={34} />
        <div className="leading-tight">
          <div className="text-[13px] font-semibold text-focus-navy">Numera is your student</div>
          <div className="text-[11px] text-[#B07A2B]">Teaching · {topicTitle}</div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-[9px] font-bold tracking-[0.18em] text-[#B07A2B] uppercase">Teacher Mode</span>
          <TurnDots done={Math.min(turnNumber, TARGET_TURNS)} total={TARGET_TURNS} />
        </div>
      </header>

      {/* Conversation — the current question is the vertically-centred hero,
          with any prior turns as a compact fading strip above it. */}
      <div className="flex-1 min-h-0 flex flex-col items-center justify-center px-6">
        <div className="w-full max-w-[680px] flex flex-col">
          {/* Quiet history */}
          {priorTurns.length > 0 && (
            <div
              ref={historyRef}
              className="max-h-[26vh] overflow-y-auto py-2 space-y-2.5 mb-3"
              style={{ maskImage: 'linear-gradient(to bottom, transparent, #000 42px)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 42px)' }}
            >
              {priorTurns.map((t, i) => (
                <div key={i} className={cn('flex', t.role === 'student' ? 'justify-end' : 'justify-start')}>
                  <div
                    className={cn(
                      'max-w-[80%] rounded-2xl px-3.5 py-2 text-[12.5px] leading-snug',
                      t.role === 'student'
                        ? 'bg-focus-navy text-white rounded-br-sm'
                        : 'bg-white/70 text-slate-blue border border-[#F0E0C6] rounded-bl-sm',
                    )}
                  >
                    {t.text}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Current question — the focal point */}
          {current && (
            <div key={turnNumber} className="teach-fade-up flex items-end gap-3.5">
              <PupilMark size={46} bob puzzled={isMisconception} />
              <div className="flex-1 min-w-0">
                {isMisconception && (
                  <div className="mb-1.5 inline-flex items-center gap-1 rounded-full bg-[#FFE2C2] px-2.5 py-0.5 text-[10px] font-semibold text-[#B4600A]">
                    Numera looks confused
                  </div>
                )}
                <div
                  className={cn(
                    'relative rounded-2xl rounded-bl-md px-5 py-4 text-[17px] leading-relaxed text-ink shadow-[0_10px_30px_rgba(214,150,40,0.18)]',
                    isMisconception ? 'bg-[#FFF3E0] border border-[#F4C77A]' : 'bg-white border border-[#F3DFBB]',
                  )}
                >
                  {sending ? <Thinking /> : current.student_facing_response}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Input dock */}
      <div className="flex-shrink-0 px-6 pb-6">
        <div className="mx-auto w-full max-w-[680px]">
          {boardOpen && (
            <div className="teach-fade-up mb-3 rounded-2xl border border-[#F3DFBB] bg-white overflow-hidden">
              <div className="flex items-center justify-between px-3 py-2 border-b border-[#F5EAD6]">
                <span className="text-[11px] font-semibold text-[#B07A2B]">Show Numera on the board</span>
                <button onClick={() => setBoardOpen(false)} aria-label="Close board" className="text-slate-blue hover:text-ink">
                  <X size={15} />
                </button>
              </div>
              <div className="relative h-[240px]">
                <DrawingCanvas onExportReady={setCanvasExporter} />
              </div>
              <div className="flex justify-end px-3 py-2 border-t border-[#F5EAD6]">
                <button
                  onClick={sendBoard}
                  disabled={sending}
                  className="inline-flex items-center gap-1.5 rounded-full bg-action-orange px-4 py-1.5 text-[12px] font-semibold text-white hover:brightness-105 disabled:opacity-50 transition"
                >
                  Show Numera <ArrowRight size={13} strokeWidth={2.2} />
                </button>
              </div>
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submit(text, 'TEXT');
            }}
            className="flex items-center gap-2 rounded-full border border-[#EAD6B2] bg-white/90 backdrop-blur px-2 py-2 shadow-[0_4px_18px_rgba(214,150,40,0.10)]"
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={!started || sending || done}
              placeholder={started ? 'Teach Numera in your own words…' : 'Start teaching to begin…'}
              className="flex-1 min-w-0 bg-transparent px-3 text-[14px] text-ink placeholder:text-[#C0A878] focus:outline-none"
            />
            <button
              type="button"
              onClick={toggleMic}
              disabled={!started || !voice.supported || sending || done}
              aria-label={voice.active ? 'Stop talking' : 'Talk to Numera'}
              className={cn(
                'flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition disabled:opacity-40',
                voice.active ? 'bg-action-orange text-white animate-pulse' : 'text-[#B07A2B] hover:bg-[#FFF1DE]',
              )}
            >
              <Mic size={17} />
            </button>
            <button
              type="button"
              onClick={() => setBoardOpen((b) => !b)}
              disabled={!started || sending || done}
              aria-label="Show on the board"
              className={cn(
                'flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition disabled:opacity-40',
                boardOpen ? 'bg-[#FFE7C4] text-[#B4600A]' : 'text-[#B07A2B] hover:bg-[#FFF1DE]',
              )}
            >
              <PencilLine size={17} />
            </button>
            <button
              type="submit"
              disabled={!started || sending || done || !text.trim()}
              aria-label="Send to Numera"
              className="flex-shrink-0 w-9 h-9 rounded-full bg-highlight-amber text-white flex items-center justify-center hover:brightness-105 transition disabled:opacity-40"
            >
              <Send size={16} />
            </button>
          </form>
        </div>
      </div>

      {/* Role-swap intro */}
      {!started && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-[#FFF8EE]/85 backdrop-blur-sm">
          <div className="teach-pop w-[420px] max-w-[90%] text-center px-8">
            <div className="mx-auto mb-5 w-14 h-14 rounded-2xl bg-highlight-amber/15 flex items-center justify-center">
              <GraduationCap size={26} className="text-action-orange" />
            </div>
            <h1 className="text-[24px] font-bold text-focus-navy leading-tight">Your turn to teach</h1>
            <p className="mt-2.5 text-[13.5px] text-slate-blue leading-relaxed">
              You just watched the idea — now explain it back to Numera in your own words. Talk, type, or show it on the
              board. Numera will ask questions like a curious student.
            </p>
            <button
              onClick={begin}
              className="mt-6 inline-flex items-center gap-2 rounded-full bg-action-orange px-6 py-3 text-[14px] font-semibold text-white hover:brightness-105 transition"
            >
              Start teaching <ArrowRight size={16} strokeWidth={2.2} />
            </button>
          </div>
        </div>
      )}

      {/* Completion */}
      {done && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-[#FFF8EE]/90 backdrop-blur-sm">
          <div className="teach-pop text-center px-8">
            <div className="mx-auto mb-5 w-14 h-14 rounded-full bg-success-sage/20 flex items-center justify-center">
              <Check size={28} className="text-success-sage" strokeWidth={2.5} />
            </div>
            <h1 className="text-[24px] font-bold text-focus-navy">You taught it!</h1>
            <p className="mt-2 text-[13.5px] text-slate-blue">
              You explained what to do and why. Let&apos;s solve one together now.
            </p>
          </div>
        </div>
      )}
    </main>
  );
}

/** Numera-as-learner mark: a softer, warm 'N' — visually the flip of the cool tutor mark. */
function PupilMark({ size = 40, bob = false, puzzled = false }: { size?: number; bob?: boolean; puzzled?: boolean }) {
  return (
    <div
      className={cn('flex-shrink-0 relative', bob && 'teach-bob')}
      style={{ width: size, height: size }}
      aria-hidden="true"
    >
      <div
        className="w-full h-full rounded-[30%] flex items-center justify-center font-bold text-white"
        style={{
          fontSize: size * 0.5,
          background: 'linear-gradient(150deg, #FFB44D 0%, #FF9F1C 55%, #F77F00 100%)',
          boxShadow: '0 4px 14px rgba(247,127,0,0.28)',
        }}
      >
        N
      </div>
      {puzzled && (
        <span
          className="absolute -top-1.5 -right-1.5 rounded-full bg-white text-[#B4600A] font-bold flex items-center justify-center border border-[#F4C77A]"
          style={{ width: size * 0.42, height: size * 0.42, fontSize: size * 0.26 }}
        >
          ?
        </span>
      )}
    </div>
  );
}

function TurnDots({ done, total }: { done: number; total: number }) {
  return (
    <div className="flex items-center gap-1.5" aria-label={`${done} of ${total} turns`}>
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full transition-colors"
          style={{ background: i < done ? '#8A9A86' : '#EAD6B2' }}
        />
      ))}
    </div>
  );
}

function Thinking() {
  return (
    <span className="inline-flex items-center gap-1 py-0.5" aria-label="Numera is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#E0A94E] animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

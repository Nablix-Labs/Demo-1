'use client';

import { useEffect, useRef } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';
import TutorProse from '@/components/TutorProse';

export default function Transcript() {
  const transcript = useNumeraStore((s) => s.transcript);
  const voiceStatus = useNumeraStore((s) => s.voiceStatus);
  const scrollRef = useRef<HTMLDivElement>(null);

  /**
   * What the dotted bubble says while it waits.
   *
   * "transcribing…" is only true while words are still arriving. Once the turn
   * has settled — no speech for utterance_end_ms, which is what puts us in
   * PROCESSING — nothing is being transcribed any more; we are waiting on the
   * tutor.
   *
   * That distinction is not cosmetic. Deepgram does not always emit
   * UtteranceEnd after the last partial (observed 7 Aug, 10:22:13), and when it
   * doesn't, the turn is only rescued by the 45-second watchdog in
   * lib/turnWatchdog.ts. For those 45 seconds the bubble sat there claiming to
   * be transcribing speech that had finished long before, which reads as the
   * app having lost the answer. It hadn't — the rescue fires and the backend
   * answers 200 — but nothing on screen said so.
   *
   * The real fix is a server-side cancellable silence timer so the turn never
   * waits that long; that is the voice server's. This is the honest label in
   * the meantime.
   */
  const waitingLabel = voiceStatus === 'processing' ? 'waiting for the tutor…' : 'transcribing…';

  // Keep the newest message in view as the conversation grows (incl. partials).
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [transcript]);

  return (
    <div
      ref={scrollRef}
      className="flex-1 min-h-0 overflow-y-auto mx-3.5 mb-3.5 border-t border-dashed border-muted-gray pt-3 flex flex-col gap-2.5"
      aria-live="polite"
      aria-label="Conversation transcript"
    >
      {transcript.map((msg) => (
        <div
          key={msg.id}
          className={cn('text-[11.5px] leading-[1.45]', msg.role === 'student' ? 'text-right' : '')}
        >
          <div className="text-[8.5px] tracking-widest uppercase text-slate-blue mb-0.5">
            {msg.role === 'ai' ? 'Numera' : 'You'}
          </div>
          {msg.role === 'ai' ? (
            <div
              className={cn(
                'bg-reading-surface border border-muted-gray border-l-[3px] border-l-ai-cyan rounded px-2.5 py-1.5',
                msg.partial ? 'border-dashed italic text-slate-blue' : ''
              )}
            >
              <TutorProse text={msg.text} />
              {msg.partial && (
                <span className="ml-1 text-[10px] text-slate-blue">{waitingLabel}</span>
              )}
            </div>
          ) : (
            <div className="inline-block max-w-[90%] text-left">
              <div
                className={cn(
                  'bg-learning-blue text-white rounded px-2.5 py-1.5',
                  msg.partial ? 'border border-dashed border-muted-gray bg-transparent text-slate-blue italic' : ''
                )}
              >
                {msg.text}
                {msg.partial && (
                  <span className="ml-1 text-[10px]">{waitingLabel}</span>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

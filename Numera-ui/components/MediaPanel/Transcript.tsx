'use client';

import { useEffect, useRef } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function Transcript() {
  const transcript = useNumeraStore((s) => s.transcript);
  const scrollRef = useRef<HTMLDivElement>(null);

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
              {msg.text}
              {msg.partial && (
                <span className="ml-1 text-[10px] text-slate-blue">transcribing…</span>
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
                  <span className="ml-1 text-[10px]">transcribing…</span>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

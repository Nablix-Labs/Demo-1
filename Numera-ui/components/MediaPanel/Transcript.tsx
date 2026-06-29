'use client';

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function Transcript() {
  const transcript = useNumeraStore((s) => s.transcript);

  return (
    <div
      className="flex-1 min-h-0 overflow-y-auto mx-3.5 mb-3.5 border-t border-dashed border-[#c8c8c8] pt-3 flex flex-col gap-2.5"
      aria-live="polite"
      aria-label="Conversation transcript"
    >
      {transcript.map((msg) => (
        <div
          key={msg.id}
          className={cn('text-[11.5px] leading-[1.45]', msg.role === 'student' ? 'text-right' : '')}
        >
          <div className="text-[8.5px] tracking-widest uppercase text-[#9a9a9a] mb-0.5">
            {msg.role === 'ai' ? 'Numera' : 'You'}
          </div>
          {msg.role === 'ai' ? (
            <div
              className={cn(
                'bg-[#f4f4f4] border border-[#c8c8c8] border-l-[3px] border-l-[#1a1a1a] rounded px-2.5 py-1.5',
                msg.partial ? 'border-dashed italic text-[#9a9a9a]' : ''
              )}
            >
              {msg.text}
              {msg.partial && (
                <span className="ml-1 text-[10px] text-[#9a9a9a]">transcribing…</span>
              )}
            </div>
          ) : (
            <div className="inline-block max-w-[90%] text-left">
              <div
                className={cn(
                  'bg-[#1a1a1a] text-white rounded px-2.5 py-1.5',
                  msg.partial ? 'border border-dashed border-[#9a9a9a] bg-transparent text-[#9a9a9a] italic' : ''
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

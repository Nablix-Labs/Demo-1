'use client';

/**
 * AITutorBar — shared AI tutor voice + text bar at the bottom of the challenge.
 * Students can type a question or use voice. Mock: a typed question gets a
 * canned acknowledgement into the commentary feed.
 */

import { useState } from 'react';
import { Mic, MicOff, ArrowUp } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function AITutorBar() {
  const { micMuted, toggleMic, addCommentary } = useNumeraStore();
  const [text, setText] = useState('');

  const send = () => {
    const q = text.trim();
    if (!q) return;
    setText('');
    // Mock AI acknowledgement; the real tutor responds via the backend
    addCommentary({ text: 'Good question — let me show the group.', tone: 'observe' });
  };

  return (
    <div className="flex-shrink-0 border-t border-[#c8c8c8] bg-white px-4 py-3">
      <div className="flex items-center gap-2 max-w-3xl mx-auto">
        <button
          onClick={toggleMic}
          aria-label={micMuted ? 'Unmute microphone' : 'Mute microphone'}
          className={cn(
            'flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center border transition-colors',
            micMuted
              ? 'border-[#c8c8c8] bg-white text-[#7a7a7a] hover:text-[#1a1a1a]'
              : 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
          )}
        >
          {micMuted ? <MicOff size={17} strokeWidth={1.8} /> : <Mic size={17} strokeWidth={1.8} />}
        </button>

        <div className="flex-1 flex items-center gap-2 rounded-full border border-[#9a9a9a] bg-white pl-4 pr-1.5 py-1.5">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask the tutor…"
            aria-label="Ask the tutor"
            className="flex-1 bg-transparent text-[13px] text-[#1a1a1a] placeholder:text-[#9a9a9a] outline-none"
          />
          <button
            onClick={send}
            disabled={!text.trim()}
            aria-label="Send"
            className={cn(
              'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-colors',
              text.trim() ? 'bg-[#1a1a1a] text-white hover:opacity-80' : 'bg-[#eaeaea] text-[#9a9a9a]'
            )}
          >
            <ArrowUp size={16} strokeWidth={2} />
          </button>
        </div>
      </div>
    </div>
  );
}

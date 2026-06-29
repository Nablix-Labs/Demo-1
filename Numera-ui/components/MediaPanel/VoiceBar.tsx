'use client';

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

const WAVE_HEIGHTS = [12, 20, 8, 24, 14, 22, 10, 18, 22, 9, 16, 20];

export default function VoiceBar() {
  const { micMuted, voiceStatus, toggleMic } = useNumeraStore();

  return (
    <div className="px-3.5 pb-3.5 flex flex-col gap-2.5">
      {/* Status */}
      <p className="text-[11.5px] text-[#7a7a7a] text-center">
        Status:{' '}
        <strong className="text-[#1a1a1a]">
          {micMuted ? 'Muted' : voiceStatus === 'listening' ? 'Listening…' : voiceStatus === 'speaking' ? 'Speaking…' : voiceStatus === 'processing' ? 'Processing…' : 'Idle'}
        </strong>
      </p>

      {/* Waveform */}
      <div className="flex items-center justify-center gap-[3px] h-[26px]" aria-hidden="true">
        {WAVE_HEIGHTS.map((h, i) => (
          <span
            key={i}
            className={cn(
              'w-[3px] rounded-sm bg-[#9a9a9a]',
              micMuted ? '' : 'animate-wave'
            )}
            style={{
              height: micMuted ? '5px' : `${h}px`,
              animationDelay: `${(i * 0.08).toFixed(2)}s`,
              animationDuration: `${0.7 + (i % 5) * 0.12}s`,
            }}
          />
        ))}
      </div>

      {/* Mute toggle */}
      <button
        onClick={toggleMic}
        aria-label={micMuted ? 'Unmute microphone' : 'Mute microphone'}
        className={cn(
          'w-full border rounded-md px-2.5 py-2.5 text-xs font-semibold flex items-center justify-center gap-2 transition-colors',
          micMuted
            ? 'border-[#1a1a1a] bg-white text-[#1a1a1a]'
            : 'border-[#1a1a1a] bg-[#1a1a1a] text-white'
        )}
      >
        {/* Mic icon (on / off) */}
        {micMuted ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="9" rx="3"/>
            <path d="M5 11 a7 7 0 0 0 11.5 5.5"/>
            <path d="M19 11 a7 7 0 0 0 -0.3 -2"/>
            <line x1="12" y1="18" x2="12" y2="21"/>
            <line x1="9" y1="21" x2="15" y2="21"/>
            <line x1="4" y1="4" x2="20" y2="20"/>
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3"/>
            <path d="M5 11 a7 7 0 0 0 14 0"/>
            <line x1="12" y1="18" x2="12" y2="21"/>
            <line x1="9" y1="21" x2="15" y2="21"/>
          </svg>
        )}
        <span>{micMuted ? 'Muted — tap to unmute' : 'Tap to mute'}</span>
      </button>
    </div>
  );
}

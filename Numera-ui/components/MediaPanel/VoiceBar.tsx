'use client';

import { useNumeraStore } from '@/store/useNumeraStore';
import { useMicLevel, MIC_BARS } from '@/store/useMicLevel';
import { cn } from '@/lib/cn';

export default function VoiceBar() {
  const { micMuted, voiceStatus, toggleMic } = useNumeraStore();
  const levels = useMicLevel((s) => s.levels);
  const active = useMicLevel((s) => s.active);
  const caption = useMicLevel((s) => s.caption);

  // The bar is "live" (reacting to real input) only while capturing + unmuted.
  const live = active && !micMuted;

  return (
    <div className="px-3.5 pb-3.5 flex flex-col gap-2.5">
      {/* Status */}
      <p className="text-[11.5px] text-slate-blue text-center">
        Status:{' '}
        <strong className="text-ink">
          {micMuted ? 'Muted' : voiceStatus === 'listening' ? 'Listening…' : voiceStatus === 'speaking' ? 'Speaking…' : voiceStatus === 'processing' ? 'Processing…' : 'Idle'}
        </strong>
      </p>

      {/* Live input level — reflects how much mic signal is being detected */}
      <div className="flex items-center justify-center gap-[3px] h-[26px]" aria-hidden="true">
        {Array.from({ length: MIC_BARS }).map((_, i) => {
          const lvl = live ? levels[i] ?? 0 : 0;
          const height = 3 + lvl * 23; // 3px (silent) … 26px (loud)
          return (
            <span
              key={i}
              className={cn(
                'w-[3px] rounded-sm transition-[height,background-color] duration-75 ease-out',
                live ? 'bg-ai-cyan' : 'bg-muted-gray'
              )}
              style={{ height: `${height}px` }}
            />
          );
        })}
      </div>

      {/* Live caption — what Numera is hearing (helps confirm the mic is working) */}
      {live && (
        <div
          className="min-h-[34px] rounded-md bg-reading-surface border border-muted-gray px-2.5 py-1.5 flex items-center justify-center text-center"
          aria-live="polite"
        >
          {caption ? (
            <p className="text-[11.5px] text-ink leading-snug">
              <span className="text-ai-cyan font-semibold">“</span>{caption}<span className="text-ai-cyan font-semibold">”</span>
            </p>
          ) : (
            <p className="text-[11px] text-slate-blue italic">Listening — start speaking…</p>
          )}
        </div>
      )}

      {/* Mute toggle */}
      <button
        onClick={toggleMic}
        aria-label={micMuted ? 'Unmute microphone' : 'Mute microphone'}
        className={cn(
          'w-full border rounded-md px-2.5 py-2.5 text-xs font-semibold flex items-center justify-center gap-2 transition-colors',
          micMuted
            ? 'border-muted-gray bg-white text-ink'
            : 'border-focus-navy bg-focus-navy text-white'
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

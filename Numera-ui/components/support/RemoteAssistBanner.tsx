'use client';

/**
 * RemoteAssistBanner — the persistent "Support is viewing your screen" notice.
 *
 * Mounted in the app shell so it survives navigation and closing the support
 * panel: as long as the share is live, the student can always see it and stop
 * it in one tap. Orange glass — the app's "strong action" colour — with a
 * recording pulse so it can't be mistaken for chrome.
 */

import { MonitorUp } from 'lucide-react';
import { useSupportStore } from '@/store/useSupportStore';
import { stopScreenShare } from '@/lib/support/remoteAssist';

export default function RemoteAssistBanner() {
  const remoteAssistActive = useSupportStore((s) => s.remoteAssistActive);

  if (!remoteAssistActive) return null;

  return (
    <div
      className="lg-anim-pop fixed top-2 left-1/2 -translate-x-1/2 z-[95] flex items-center gap-3 rounded-full pl-4 pr-1.5 py-1.5 text-white"
      style={{
        background: 'linear-gradient(160deg, rgba(255,143,28,0.92), rgba(247,127,0,0.88))',
        backdropFilter: 'blur(18px) saturate(160%)',
        WebkitBackdropFilter: 'blur(18px) saturate(160%)',
        border: '1px solid rgba(255,255,255,0.4)',
        boxShadow: '0 10px 30px rgba(247,127,0,0.45), inset 0 1px 0 rgba(255,255,255,0.4)',
      }}
      role="status"
      aria-live="polite"
    >
      <span className="relative flex w-2 h-2" aria-hidden="true">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-70" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-white" />
      </span>
      <MonitorUp size={14} strokeWidth={2} aria-hidden="true" />
      <span className="text-[12px] font-semibold tracking-[0.1px]">Support is viewing your screen</span>
      <button
        onClick={stopScreenShare}
        className="rounded-full bg-white/25 hover:bg-white/40 px-3.5 py-1 text-[11.5px] font-semibold transition-colors
                   focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80"
      >
        Stop
      </button>
    </div>
  );
}

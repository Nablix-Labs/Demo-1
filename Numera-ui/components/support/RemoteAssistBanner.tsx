'use client';

/**
 * RemoteAssistBanner — the persistent "Support is viewing your screen" notice.
 *
 * Mounted in the app shell so it survives navigation and closing the support
 * panel: as long as the share is live, the student can always see it and stop
 * it in one tap.
 */

import { MonitorUp } from 'lucide-react';
import { useSupportStore } from '@/store/useSupportStore';
import { stopScreenShare } from '@/lib/support/remoteAssist';

export default function RemoteAssistBanner() {
  const remoteAssistActive = useSupportStore((s) => s.remoteAssistActive);

  if (!remoteAssistActive) return null;

  return (
    <div
      className="fixed top-2 left-1/2 -translate-x-1/2 z-[95] flex items-center gap-3 rounded-full bg-action-orange text-white pl-4 pr-2 py-1.5"
      style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.25)' }}
      role="status"
      aria-live="polite"
    >
      <MonitorUp size={14} strokeWidth={2} aria-hidden="true" />
      <span className="text-[12px] font-semibold">Support is viewing your screen</span>
      <button
        onClick={stopScreenShare}
        className="rounded-full bg-white/20 hover:bg-white/30 px-3 py-1 text-[11.5px] font-semibold transition-colors"
      >
        Stop
      </button>
    </div>
  );
}

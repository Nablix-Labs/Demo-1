'use client';

/**
 * NeedHelpButton — the persistent "Need help?" entry point for Nablix Assist.
 * Lives in the app shell (like FloatingMicButton) so it's reachable from every
 * route, including onboarding. Opening support pauses the tutor via
 * useSupportStore; the button hides while the panel is open.
 */

import { LifeBuoy } from 'lucide-react';
import { useSupportStore } from '@/store/useSupportStore';

export default function NeedHelpButton() {
  const open = useSupportStore((s) => s.open);
  const openSupport = useSupportStore((s) => s.openSupport);

  if (open) return null;

  return (
    <button
      onClick={openSupport}
      aria-label="Open Nablix Assist support"
      data-support-id="need-help"
      className="lg-glass fixed bottom-24 right-4 z-[60] rounded-full pl-3 pr-4 py-2.5 flex items-center gap-2 text-ink text-[12px] font-semibold hover:brightness-[1.03] transition"
      style={{ boxShadow: '0 4px 16px rgba(0,0,0,0.18)' }}
    >
      <LifeBuoy size={16} strokeWidth={1.8} className="text-learning-blue" />
      Need help?
    </button>
  );
}

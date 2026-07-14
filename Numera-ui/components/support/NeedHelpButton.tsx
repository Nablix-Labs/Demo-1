'use client';

/**
 * NeedHelpButton — the persistent "Need help?" entry point for Nablix Assist.
 * Lives in the app shell (like FloatingMicButton) so it's reachable from every
 * route, including onboarding. Opening support pauses the tutor via
 * useSupportStore; the button hides while the panel is open.
 *
 * Visual: elevated liquid glass with the assist lens (breathing blue aura) —
 * the same identity that heads the support panel.
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
      className="lg-sheet lg-anim-pop group fixed bottom-24 right-4 z-[60] rounded-full pl-2 py-2 flex items-center gap-2.5
                 text-ink text-[12.5px] font-semibold tracking-[0.1px]
                 transition-[transform,filter] duration-200 ease-out
                 hover:-translate-y-0.5 hover:brightness-[1.04] active:translate-y-0 active:scale-[0.97]
                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/60 focus-visible:ring-offset-2"
      style={{ paddingRight: 18 }}
    >
      <span className="lg-lens lg-aura w-8 h-8 rounded-full flex items-center justify-center text-white flex-shrink-0">
        <LifeBuoy size={16} strokeWidth={1.9} aria-hidden="true" />
      </span>
      Need help?
    </button>
  );
}

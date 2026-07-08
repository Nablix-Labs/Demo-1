'use client';

/**
 * FloatingMicButton — the mic mute/unmute control. Draggable anywhere on screen
 * (like the drawing toolbar) so it never has to sit on top of the student's
 * working. Defaults to bottom-centre; a plain tap toggles the mic, a drag moves
 * it. Position persists via the store. Uses action-orange (brand: "Strong CTA")
 * while live, since this is the primary control of the voice session.
 */

import { useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore, isConsentActive } from '@/store/useAuthStore';
import { cn } from '@/lib/cn';

const SIZE = 56; // w-14 / h-14 in px
const MARGIN = 8; // keep this far from the viewport edges
const DRAG_THRESHOLD = 4; // px of movement before a press counts as a drag, not a tap

const SHADOW = '0 4px 16px rgba(0,0,0,0.2)';

export default function FloatingMicButton() {
  const micMuted = useNumeraStore((s) => s.micMuted);
  const toggleMic = useNumeraStore((s) => s.toggleMic);
  const micButtonPos = useNumeraStore((s) => s.micButtonPos);
  const setMicButtonPos = useNumeraStore((s) => s.setMicButtonPos);
  const consents = useAuthStore((s) => s.consents);

  // Voice is a consented feature (§10): only available with voice_processing consent.
  const voiceAllowed = isConsentActive(consents, 'voice_processing');

  const btnRef = useRef<HTMLButtonElement>(null);
  const dragOffset = useRef<{ dx: number; dy: number } | null>(null);
  const didDrag = useRef(false);

  if (!voiceAllowed) return null;

  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const el = btnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    dragOffset.current = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    didDrag.current = false; // reset so a fresh press starts as a potential tap
    el.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (!dragOffset.current) return;
    const nx = e.clientX - dragOffset.current.dx;
    const ny = e.clientY - dragOffset.current.dy;
    // Only treat it as a drag once past the threshold, so a plain tap (with tiny
    // finger jitter) still toggles the mic instead of moving the button.
    if (!didDrag.current) {
      const r = btnRef.current!.getBoundingClientRect();
      if (Math.abs(nx - r.left) > DRAG_THRESHOLD || Math.abs(ny - r.top) > DRAG_THRESHOLD) {
        didDrag.current = true;
      }
    }
    if (!didDrag.current) return;
    const x = Math.max(MARGIN, Math.min(nx, window.innerWidth - SIZE - MARGIN));
    const y = Math.max(MARGIN, Math.min(ny, window.innerHeight - SIZE - MARGIN));
    setMicButtonPos({ x, y });
  };

  const onPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
    dragOffset.current = null;
    try {
      btnRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* pointer already released */
    }
  };

  const onClick = () => {
    // A drag ends with a click event too — swallow it so moving doesn't toggle.
    if (didDrag.current) {
      didDrag.current = false;
      return;
    }
    toggleMic();
  };

  const positioned = micButtonPos != null;

  return (
    <button
      ref={btnRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onClick={onClick}
      aria-label={micMuted ? 'Unmute microphone' : 'Mute microphone'}
      className={cn(
        'fixed z-[55] w-14 h-14 rounded-full flex items-center justify-center transition-colors',
        'touch-none cursor-grab active:cursor-grabbing',
        // Default docked spot (bottom-centre, clearing the toolbar + demo bar)
        // until the student drags it somewhere.
        !positioned && 'bottom-32 left-1/2 -translate-x-1/2',
        micMuted ? 'lg-glass text-ink' : 'bg-action-orange text-white'
      )}
      style={positioned ? { left: micButtonPos.x, top: micButtonPos.y, boxShadow: SHADOW } : { boxShadow: SHADOW }}
    >
      {micMuted ? (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="9" rx="3"/>
          <path d="M5 11 a7 7 0 0 0 11.5 5.5"/>
          <path d="M19 11 a7 7 0 0 0 -0.3 -2"/>
          <line x1="12" y1="18" x2="12" y2="21"/>
          <line x1="9" y1="21" x2="15" y2="21"/>
          <line x1="4" y1="4" x2="20" y2="20"/>
        </svg>
      ) : (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3"/>
          <path d="M5 11 a7 7 0 0 0 14 0"/>
          <line x1="12" y1="18" x2="12" y2="21"/>
          <line x1="9" y1="21" x2="15" y2="21"/>
        </svg>
      )}
    </button>
  );
}

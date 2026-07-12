'use client';

/**
 * ConsentModal — "I can do X — continue?" gate shown before any safe action
 * with requiresConfirmation (risk ≥ medium). Nothing runs until the student
 * explicitly continues.
 */

import { ShieldQuestion } from 'lucide-react';

interface ConsentModalProps {
  label: string; // human phrasing of the action, e.g. "retry the tutor connection"
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConsentModal({ label, onConfirm, onCancel }: ConsentModalProps) {
  return (
    <div
      className="lg-scrim lg-anim-fade fixed inset-0 z-[90] flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm support action"
    >
      <div className="lg-sheet lg-anim-pop w-[350px] max-w-[calc(100vw-32px)] rounded-[24px] p-5">
        <div className="flex items-center gap-3">
          <span className="lg-lens w-10 h-10 rounded-full flex items-center justify-center text-white flex-shrink-0">
            <ShieldQuestion size={19} strokeWidth={1.9} aria-hidden="true" />
          </span>
          <p className="text-[13.5px] text-ink leading-snug">
            I can <span className="font-semibold">{label}</span> — continue?
          </p>
        </div>
        <div className="flex gap-2.5 mt-4">
          <button onClick={onConfirm} className="btn btn-primary flex-1 !py-2 !rounded-full text-[12.5px]">
            Yes, go ahead
          </button>
          <button
            onClick={onCancel}
            className="lg-chip flex-1 rounded-full py-2 text-[12.5px] font-semibold text-ink/80 hover:text-ink
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-learning-blue/50"
          >
            No, cancel
          </button>
        </div>
      </div>
    </div>
  );
}

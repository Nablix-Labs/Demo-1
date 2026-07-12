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
      className="fixed inset-0 z-[90] flex items-center justify-center bg-ink/30"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm support action"
    >
      <div
        className="w-[340px] max-w-[calc(100vw-32px)] bg-white rounded-xl border border-muted-gray p-5"
        style={{ boxShadow: '0 8px 32px rgba(0,0,0,0.22)' }}
      >
        <div className="flex items-center gap-2.5">
          <span className="w-9 h-9 rounded-full bg-learning-blue/10 text-learning-blue flex items-center justify-center flex-shrink-0">
            <ShieldQuestion size={18} strokeWidth={1.8} />
          </span>
          <p className="text-[13.5px] text-ink leading-snug">
            I can <span className="font-semibold">{label}</span> — continue?
          </p>
        </div>
        <div className="flex gap-2.5 mt-4">
          <button onClick={onConfirm} className="btn btn-primary flex-1 !py-2 text-[12.5px]">
            Yes, go ahead
          </button>
          <button onClick={onCancel} className="btn btn-secondary flex-1 !py-2 text-[12.5px]">
            No, cancel
          </button>
        </div>
      </div>
    </div>
  );
}

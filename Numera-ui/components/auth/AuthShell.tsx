'use client';

/**
 * AuthShell — shared chrome for the pre-auth lifecycle screens (registration,
 * guardian consent, login, restricted states). Keeps them visually one flow:
 * the Numera brand mark, an optional step rail, and a centred panel.
 */

import type { ReactNode } from 'react';

export default function AuthShell({
  step,
  totalSteps,
  width = 480,
  children,
}: {
  step?: number;        // 1-based current step, shown as a progress rail
  totalSteps?: number;
  width?: number;
  children: ReactNode;
}) {
  return (
    <main className="flex-1 min-w-0 flex flex-col items-center bg-off-white overflow-y-auto" aria-label="Numera account">
      {/* Brand header */}
      <div className="w-full flex items-center gap-2.5 px-8 py-6 flex-shrink-0">
        <span className="w-9 h-9 rounded-lg bg-ai-cyan text-white flex items-center justify-center font-bold text-base">
          N
        </span>
        <div className="leading-none">
          <div className="text-[15px] font-semibold text-ink tracking-[0.2px]">Numera</div>
          <div className="text-[8.5px] font-normal text-slate-blue tracking-[1.5px] uppercase mt-0.5">by Nablix</div>
        </div>
      </div>

      <div className="flex-1 w-full flex items-center justify-center px-6 pb-16">
        <div style={{ width }} className="max-w-full">
          {step != null && totalSteps != null && (
            <div className="flex items-center gap-1.5 mb-6" aria-label={`Step ${step} of ${totalSteps}`}>
              {Array.from({ length: totalSteps }, (_, i) => (
                <span
                  key={i}
                  className={
                    'h-1 flex-1 rounded-full transition-colors ' +
                    (i < step ? 'bg-learning-blue' : 'bg-muted-gray')
                  }
                />
              ))}
            </div>
          )}
          {children}
        </div>
      </div>
    </main>
  );
}

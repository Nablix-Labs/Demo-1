'use client';

/**
 * AuthShell — shared chrome for the pre-auth lifecycle screens (registration,
 * guardian consent, restricted states).
 *
 * Same two-panel frame as login, so the whole pre-auth flow reads as one
 * surface: the step's content on the left, the brand panel on the right.
 */

import type { ReactNode } from 'react';
import BrandPanel from './BrandPanel';

export default function AuthShell({
  step,
  totalSteps,
  headline = 'Maths that meets you where you are.',
  children,
}: {
  step?: number;        // 1-based current step, shown as a progress rail
  totalSteps?: number;
  /** Overrides the brand panel's line where a screen has its own point. */
  headline?: string;
  children: ReactNode;
}) {
  return (
    <main className="flex-1 min-w-0 bg-white p-3 text-ink antialiased" aria-label="Numera account">
      <div className="grid min-h-[calc(100vh-1.5rem)] gap-3 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="flex items-center overflow-y-auto rounded-xl border border-muted-gray bg-white px-6 py-12 sm:px-10 lg:px-14 xl:px-20">
          <div className="mx-auto w-full max-w-[460px]">
            {/* Wordmark — carries the identity on small screens, where the
                brand panel is hidden. */}
            <div className="mb-10 flex items-center gap-2.5 lg:hidden">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-learning-blue text-base font-bold text-white">N</span>
              <div className="leading-none">
                <div className="text-[15px] font-semibold text-ink tracking-[0.2px]">Numera</div>
                <div className="mt-0.5 text-[8.5px] uppercase tracking-[1.5px] text-slate-blue">by Nablix</div>
              </div>
            </div>

            {step != null && totalSteps != null && (
              <div className="mb-8 flex items-center gap-1.5" aria-label={`Step ${step} of ${totalSteps}`}>
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

        <BrandPanel headline={headline} />
      </div>
    </main>
  );
}

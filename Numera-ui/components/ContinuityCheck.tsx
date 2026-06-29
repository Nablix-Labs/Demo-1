'use client';

/**
 * ContinuityCheck — when a returning student has prior progress, do a quick
 * retention check on their last topic before resuming, then give feedback.
 * Shown once per browser session. (The "after a deadline" trigger is backend;
 * here it appears whenever there's saved progress and hasn't been seen yet.)
 */

import { useEffect, useState } from 'react';
import { Check, X } from 'lucide-react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

const SEEN_KEY = 'numera-continuity-seen';
const RECAP = { prompt: 'Quick recap — solve: 2x + 5 = 13', options: ['x = 4', 'x = 9', 'x = 3'], answer: 0 };

export default function ContinuityCheck() {
  const completedLessons = useNumeraStore((s) => s.completedLessons);
  const studentName = useNumeraStore((s) => s.studentName);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);

  useEffect(() => {
    if (completedLessons.length === 0) return;
    try {
      if (sessionStorage.getItem(SEEN_KEY)) return;
      sessionStorage.setItem(SEEN_KEY, '1');
    } catch { /* ignore */ }
    setOpen(true);
  }, [completedLessons.length]);

  if (!open) return null;
  const answered = picked !== null;
  const correct = picked === RECAP.answer;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 p-4" role="dialog" aria-modal="true" aria-label="Welcome back check">
      <div className="w-[420px] max-w-full bg-white border border-[#9a9a9a] rounded-xl overflow-hidden" style={{ boxShadow: '0 14px 48px rgba(0,0,0,0.24)' }}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#eaeaea]">
          <span className="text-[14px] font-semibold text-[#1a1a1a]">{studentName ? `Welcome back, ${studentName}` : 'Welcome back'}</span>
          <button onClick={() => setOpen(false)} aria-label="Close" className="w-7 h-7 rounded-md flex items-center justify-center text-[#7a7a7a] hover:bg-[#f4f4f4]">
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="p-5">
          {!answered ? (
            <>
              <p className="text-[12.5px] text-[#7a7a7a] mb-4 leading-snug">
                Let&apos;s make sure last session stuck before we carry on.
              </p>
              <div className="text-[15px] font-semibold text-[#1a1a1a] font-[Cambria_Math,Georgia,serif] mb-4">{RECAP.prompt}</div>
              <div className="flex flex-col gap-2.5">
                {RECAP.options.map((opt, idx) => (
                  <button
                    key={opt}
                    onClick={() => setPicked(idx)}
                    className="rounded-lg border border-[#c8c8c8] hover:border-[#9a9a9a] px-4 py-2.5 text-left text-[14px] font-[Cambria_Math,Georgia,serif] transition-colors"
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className={cn('flex items-center gap-2 text-[14px] font-semibold mb-2', correct ? 'text-[#1a1a1a]' : 'text-[#7a7a7a]')}>
                <span className={cn('w-6 h-6 rounded-full flex items-center justify-center', correct ? 'bg-[#1a1a1a] text-white' : 'border border-[#9a9a9a]')}>
                  {correct ? <Check size={13} strokeWidth={2.4} /> : <X size={13} strokeWidth={2.4} />}
                </span>
                {correct ? 'You remember it well.' : 'Worth a quick refresher.'}
              </div>
              <p className="text-[12.5px] text-[#7a7a7a] leading-snug">
                {correct
                  ? 'Great — picking up where you left off.'
                  : 'We’ll start with a brief recap of solving for x, then continue.'}
              </p>
              <button onClick={() => setOpen(false)} className="mt-4 w-full rounded-md bg-[#1a1a1a] text-white px-4 py-2.5 text-[13px] font-semibold hover:opacity-80 transition-opacity">
                Continue
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

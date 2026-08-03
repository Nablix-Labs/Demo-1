'use client';

/**
 * SlideDots — a vertical progress rail for the lesson's steps. Reads as a
 * connected stepper: completed steps fill cyan, the current one is a ringed navy
 * node, upcoming ones are hollow. Floats as its own glass rail so it reads as a
 * distinct control, not part of the canvas.
 *
 * Read-only on purpose. The nodes used to be buttons that jumped to any step,
 * which let a student skip ahead of the phase the backend had them in — the
 * whole point of the adaptive loop is that progression is earned, not selected
 * (Manjusha, 2026-07-28). It reports progress; it does not steer.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function SlideDots() {
  const { activeSlide, totalSlides } = useNumeraStore();

  // Nothing true to show yet. The rail used to default to "step 3 of 9" and
  // nothing ever assigned it, so every student saw the same invented position
  // for the whole lesson; an absent rail is more honest than a wrong one.
  if (totalSlides <= 0) return null;

  return (
    <div
      className="lg-glass flex flex-col items-center flex-shrink-0 rounded-full my-2 mx-1.5 py-4 overflow-y-auto"
      style={{ width: 34 }}
      role="progressbar"
      aria-label="Lesson progress"
      aria-valuenow={activeSlide + 1}
      aria-valuemin={1}
      aria-valuemax={totalSlides}
    >
      {Array.from({ length: totalSlides }, (_, i) => {
        const done = i < activeSlide;
        const active = i === activeSlide;
        return (
          <div key={i} className="flex flex-col items-center">
            {/* connector to the previous node — filled once reached */}
            {i > 0 && (
              <span
                className={cn(
                  'w-[3px] h-3.5 rounded-full transition-colors duration-300',
                  i <= activeSlide ? 'bg-ai-cyan' : 'bg-muted-gray/70'
                )}
              />
            )}
            <span
              aria-current={active ? 'step' : undefined}
              className={cn(
                'rounded-full transition-all duration-300 flex-shrink-0',
                active
                  ? 'w-[13px] h-[13px] bg-focus-navy ring-2 ring-white'
                  : done
                  ? 'w-[10px] h-[10px] bg-ai-cyan'
                  : 'w-[9px] h-[9px] bg-white/80 border border-muted-gray'
              )}
            />
          </div>
        );
      })}
    </div>
  );
}

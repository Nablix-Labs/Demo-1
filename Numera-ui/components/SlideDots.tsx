'use client';

/**
 * SlideDots — a vertical progress rail for the lesson's steps. Reads as a
 * connected stepper: completed steps fill cyan, the current one is a ringed navy
 * node, upcoming ones are hollow. Clicking a node jumps to that step. Floats as
 * its own glass rail so it reads as a distinct control, not part of the canvas.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function SlideDots() {
  const { activeSlide, totalSlides, setActiveSlide } = useNumeraStore();

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
            <button
              title={`Step ${i + 1}`}
              aria-label={`Go to step ${i + 1}`}
              aria-current={active ? 'step' : undefined}
              onClick={() => setActiveSlide(i)}
              className={cn(
                'rounded-full transition-all duration-300 flex-shrink-0',
                active
                  ? 'w-[13px] h-[13px] bg-focus-navy ring-2 ring-white'
                  : done
                  ? 'w-[10px] h-[10px] bg-ai-cyan hover:scale-110'
                  : 'w-[9px] h-[9px] bg-white/80 border border-muted-gray hover:border-focus-navy'
              )}
            />
          </div>
        );
      })}
    </div>
  );
}

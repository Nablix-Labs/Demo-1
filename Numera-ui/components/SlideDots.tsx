'use client';

import { useNumeraStore } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

export default function SlideDots() {
  const { activeSlide, totalSlides, setActiveSlide } = useNumeraStore();

  return (
    <div
      className="flex flex-col items-center flex-shrink-0 border-r border-muted-gray bg-white py-4.5 gap-2.5 overflow-y-auto"
      style={{ width: 38 }}
      aria-label="Slide navigation"
    >
      {Array.from({ length: totalSlides }, (_, i) => (
        <button
          key={i}
          title={`Slide ${i + 1}`}
          aria-label={`Slide ${i + 1}`}
          aria-current={i === activeSlide ? 'true' : undefined}
          onClick={() => setActiveSlide(i)}
          className={cn(
            'w-[9px] h-[9px] rounded-full border flex-shrink-0 transition-transform',
            i === activeSlide
              ? 'bg-focus-navy border-focus-navy scale-[1.3]'
              : 'bg-white border-muted-gray hover:border-focus-navy'
          )}
        />
      ))}
    </div>
  );
}

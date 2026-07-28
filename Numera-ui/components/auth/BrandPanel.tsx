'use client';

import { useEffect, useState } from 'react';
import { GrainGradient } from '@paper-design/shaders-react';
import { cn } from '@/lib/cn';

/**
 * BrandPanel — the deep-blue half of the pre-auth screens.
 *
 * Shared by login and the registration/consent shell so the two never drift
 * apart; the only thing that changes between them is the headline.
 *
 * Hidden below lg on purpose: at that width it would push the form below the
 * fold, and getting into the account is the only job of these screens.
 */

/** True when the viewer has asked for reduced motion — the shader then holds
 *  still instead of animating. */
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

export default function BrandPanel({
  headline,
  side = 'right',
}: {
  headline: string;
  /** Which column the panel sits in. Login and sign-up sit on opposite sides,
   *  so moving between them reads as the panel sliding across rather than the
   *  page being replaced. */
  side?: 'left' | 'right';
}) {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <aside
      className={cn(
        'relative hidden overflow-hidden rounded-xl bg-focus-navy p-10 text-white lg:flex xl:p-14',
        side === 'left' ? 'lg:order-first' : 'lg:order-last',
      )}
    >
      {/* Live grain gradient in the brand blues. A flat CSS blend read as a
          plain panel; the shader gives it depth that moves.
          `speed={0}` under reduced motion so it renders as a still image. */}
      <GrainGradient
        speed={reducedMotion ? 0 : 0.6}
        scale={1}
        rotation={0}
        offsetX={0}
        offsetY={0}
        softness={0.5}
        intensity={0.45}
        noise={0.22}
        shape="corners"
        frame={2854.5}
        colors={['#0E1A33', '#4169E1', '#00B4D8', '#0E1A33']}
        colorBack="#0B1426"
        className="absolute inset-0"
      />

      {/* The signature: the sigma set enormous and bled off the corner, so the
          panel reads as a maths product before a single word is. */}
      <span
        className="pointer-events-none absolute -bottom-16 -right-4 select-none font-serif italic leading-none text-white/[0.09] text-[340px] xl:text-[420px]"
        aria-hidden
      >
        ∑
      </span>

      <div className="relative z-10 flex h-full w-full flex-col justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-ai-cyan text-lg font-bold text-white">
            N
          </span>
          <div className="leading-none">
            <div className="text-[17px] font-semibold tracking-[0.2px]">Numera</div>
            <div className="mt-1 text-[9px] uppercase tracking-[2px] text-white/60">by Nablix</div>
          </div>
        </div>

        <h2 className="max-w-[13ch] text-5xl font-medium leading-[1.0] tracking-[-0.04em] xl:text-[64px]">
          {headline}
        </h2>

        {/* Deliberately nothing here. The panel says one thing. */}
        <div aria-hidden />
      </div>
    </aside>
  );
}

'use client';

/**
 * BrandPanel — the deep-blue half of the pre-auth screens.
 *
 * Shared by login and the registration/consent shell so the two never drift
 * apart; the only thing that changes between them is the headline.
 *
 * Hidden below lg on purpose: at that width it would push the form below the
 * fold, and getting into the account is the only job of these screens.
 */

export default function BrandPanel({ headline }: { headline: string }) {
  return (
    <aside className="relative hidden overflow-hidden rounded-xl bg-focus-navy p-10 text-white lg:flex xl:p-14">
      {/* Depth built from the brand blues rather than a shader library — a WebGL
          dependency to light an auth background is weight this app (already
          carrying a 3D avatar and a canvas engine) shouldn't pay. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(120% 90% at 85% 8%, rgba(0,180,216,0.42) 0%, transparent 55%),' +
            'radial-gradient(110% 80% at 8% 95%, rgba(65,105,225,0.50) 0%, transparent 58%),' +
            'linear-gradient(160deg, #1B2A4A 0%, #16223c 55%, #101a2e 100%)',
        }}
        aria-hidden
      />
      {/* Grain, so the gradient reads as a printed surface rather than a flat
          CSS blend. */}
      <div
        className="absolute inset-0 opacity-[0.16] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E\")",
        }}
        aria-hidden
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

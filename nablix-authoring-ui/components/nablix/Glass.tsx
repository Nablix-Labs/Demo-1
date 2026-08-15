'use client';

import dynamic from 'next/dynamic';

// liquid-glass-react touches the DOM/canvas on mount — load it client-only.
const LiquidGlass = dynamic(() => import('liquid-glass-react'), { ssr: false });

/**
 * Real refractive liquid glass (liquid-glass-react). Best used as a floating
 * element over a vivid surface (the navy spotlight) so it has colour to lens.
 * The mouse-elasticity animates in real browsers; the static glass renders
 * regardless. `overLight` tunes contrast when the backdrop is dark.
 */
export function Glass({
  children,
  cornerRadius = 24,
  padding = '10px 16px',
  className,
  style,
}: {
  children: React.ReactNode;
  cornerRadius?: number;
  padding?: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <LiquidGlass
      cornerRadius={cornerRadius}
      padding={padding}
      displacementScale={70}
      blurAmount={0.02}
      saturation={135}
      aberrationIntensity={2}
      elasticity={0.28}
      mode="standard"
      className={className}
      style={style}
    >
      {children}
    </LiquidGlass>
  );
}

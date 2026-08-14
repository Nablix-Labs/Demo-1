'use client';

/**
 * Resolve a value that may be given per breakpoint.
 *
 * `useResponsive(196)` returns 196; `useResponsive({ sm: 120, lg: 196 })`
 * returns whichever matches the current viewport.
 *
 * Two changes from the version this was taken from. It initialises to the plain
 * value rather than `undefined` — the original returned undefined on the first
 * render, which for a width prop meant the element painted at zero width and
 * then jumped, and under SSR it rendered a book with no width at all. And the
 * resize listener is throttled to animation frames, because a bare `resize`
 * handler that calls `setState` fires dozens of times per drag.
 */

import { useEffect, useState } from 'react';

const BREAKPOINTS = { SM: 0, MD: 600, LG: 960, XL: 1200 } as const;

export interface ResponsiveProp<T> {
  sm?: T;
  md?: T;
  lg?: T;
  xl?: T;
}

function resolve<T>(styles: T | ResponsiveProp<T>, width: number): T | undefined {
  if (typeof styles !== 'object' || styles === null) return styles as T;

  const s = styles as ResponsiveProp<T>;
  let current: T | undefined;
  if (s.sm !== undefined && width >= BREAKPOINTS.SM) current = s.sm;
  if (s.md !== undefined && width >= BREAKPOINTS.MD) current = s.md;
  if (s.lg !== undefined && width >= BREAKPOINTS.LG) current = s.lg;
  if (s.xl !== undefined && width >= BREAKPOINTS.XL) current = s.xl;
  return current;
}

export function useResponsive<T>(styles: T | ResponsiveProp<T>): T | undefined {
  // Widest defined value on the server and for the first paint, so the layout
  // does not start collapsed and settle afterwards.
  const [value, setValue] = useState<T | undefined>(() =>
    resolve(styles, BREAKPOINTS.XL),
  );

  const key = JSON.stringify(styles);

  useEffect(() => {
    let frame = 0;
    const apply = () => setValue(resolve(styles, window.innerWidth));

    const onResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(apply);
    };

    apply();
    window.addEventListener('resize', onResize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
    };
    // `styles` is an object literal at most call sites, so a new identity every
    // render; the serialised form is what actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return value;
}

export default useResponsive;

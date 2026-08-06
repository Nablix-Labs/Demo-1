'use client';

/**
 * A book — a 3D cover with a visible spine, fore-edge and back board.
 *
 * The depth is real geometry rather than a drawn shadow: the spread is given a
 * `perspective`, the fore-edge is a panel rotated 90° on the Y axis, and the
 * back board is pushed away on Z. That is why it holds up when it tilts on
 * hover, which a painted-on shadow would not.
 *
 * Sizes are driven by container queries (`cqw`), so the title and padding scale
 * with the book rather than being fixed — one component works at 120px and at
 * 240px without a second set of type sizes.
 */

import type { ReactNode } from 'react';
import clsx from 'clsx';
import { useResponsive, type ResponsiveProp } from '@/components/ui/use-responsive';

interface BookProps {
  title: string;
  variant?: 'simple' | 'stripe';
  width?: number | ResponsiveProp<number>;
  color?: string;
  textColor?: string;
  illustration?: ReactNode;
  textured?: boolean;
  /** Small line under the title — for us, the file's type and size. */
  footnote?: string;
}

export function Book({
  title,
  variant = 'stripe',
  width = 196,
  color,
  textColor = '#2B2D42',
  illustration,
  textured = false,
  footnote,
}: BookProps) {
  const _width = useResponsive(width) ?? 196;
  const _color = color ?? (variant === 'simple' ? '#FAFAFA' : '#FF9F1C');

  return (
    <div className="inline-block w-fit" style={{ perspective: 900 }}>
      <div
        className="book-rotate relative aspect-[49/60] w-fit rotate-0 duration-[250ms]"
        style={{
          transformStyle: 'preserve-3d',
          minWidth: _width,
          containerType: 'inline-size',
        }}
      >
        {/* Front board */}
        <div
          className="relative flex h-full flex-col overflow-hidden rounded-l-md rounded-r bg-background-200 shadow-book after:absolute after:h-full after:w-full after:rounded-l-md after:rounded-r after:border after:border-gray-alpha-400 after:shadow-book-border"
          style={{ width: _width }}
        >
          <div
            className={clsx('relative w-full overflow-hidden', variant === 'stripe' && 'flex-1')}
            style={{ background: _color }}
          >
            {variant === 'stripe' && illustration && (
              <div className="absolute flex h-full w-full items-center justify-center">
                {illustration}
              </div>
            )}
            {/* The binding: the band of light and shade down the hinge. */}
            <div
              className="absolute h-full w-[8.2%] mix-blend-overlay"
              style={{ background: 'var(--ds-book-bind)' }}
            />
          </div>

          <div
            className={clsx(
              'relative flex-1',
              (variant === 'stripe' || (variant === 'simple' && color === undefined)) &&
                'bg-book-gradient',
            )}
            style={{
              background: variant === 'simple' && color !== undefined ? _color : undefined,
            }}
          >
            <div
              className="absolute h-full w-[8.2%] opacity-20"
              style={{ background: 'var(--ds-book-bind)' }}
            />
            <div
              className={clsx(
                'flex w-full flex-col p-[6.1%] pl-[14.3%]',
                variant === 'simple' ? 'gap-4' : 'justify-between',
              )}
              style={{ containerType: 'inline-size', gap: `calc((24 / 196) * ${_width}px)` }}
            >
              <span
                className={clsx(
                  'text-balance font-semibold leading-[1.25em] tracking-[-.02em]',
                  variant === 'simple' ? 'text-[12cqw]' : 'text-[10.5cqw]',
                )}
                style={{ color: textColor }}
              >
                {title}
              </span>

              {footnote && (
                <span
                  className="text-[7cqw] leading-tight opacity-70"
                  style={{ color: textColor }}
                >
                  {footnote}
                </span>
              )}

              {/* The source component printed a triangle here as its publisher
                  mark. Removed: a mark that stands for nothing is decoration,
                  and the kind icon in the cloth band already carries meaning. */}
              {variant === 'simple' && illustration}
            </div>
          </div>

          {textured && (
            <div
              aria-hidden="true"
              className="book-texture pointer-events-none absolute inset-0 left-0 top-0 rounded-l-md rounded-r opacity-[0.35] mix-blend-soft-light"
            />
          )}
        </div>

        {/* Fore-edge: the stacked paper you see down the open side. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-[3px] h-[calc(100%_-_2_*_3px)] w-[calc(29cqw_-_2px)]"
          style={{
            background:
              'linear-gradient(90deg, #eaeaea, transparent 70%), linear-gradient(#fff, #fafafa)',
            transform: `translateX(calc(${_width}px - 29cqw / 2 - 3px)) rotateY(90deg) translateX(calc(29cqw / 2))`,
          }}
        />

        {/* Back board */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-0 top-0 h-full rounded-l-md rounded-r bg-neutral-200"
          style={{ width: _width, transform: 'translateZ(calc(-1 * 29cqw))' }}
        />
      </div>
    </div>
  );
}

export default Book;

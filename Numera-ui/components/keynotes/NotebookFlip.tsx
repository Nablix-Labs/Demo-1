'use client';

/**
 * The open notebook, turned by StPageFlip (`react-pageflip`).
 *
 * This replaces a hand-rolled CSS `rotateY` flip. The hand-rolled one worked and
 * tracked a drag correctly, but a page turn is not a rotation — it is a sheet
 * bending, and the curl, the varying shadow along the fold and the way the leaf
 * catches light are what sell it. StPageFlip models the sheet properly, and gets
 * momentum, snap-back and touch for free.
 *
 * The cost is honest and worth stating: StPageFlip animates on
 * requestAnimationFrame. The Browser pane suppresses rAF, so the turn will look
 * frozen THERE while working normally in a real browser. That trade is the whole
 * reason the previous version was CSS-only; it is being spent deliberately to
 * get a better turn for actual students.
 *
 * StPageFlip measures and mutates the DOM on mount, so this module must only
 * ever load in the browser — the page imports it via `next/dynamic` with
 * `ssr: false`. Importing it directly would break the static export.
 *
 * Its children must be a flat list of real page elements, so a Spread (which
 * holds a left and a right side) is flattened into two leaves here. Spread N
 * therefore occupies leaves 2N and 2N+1, which is the mapping used to translate
 * between the library's page index and our spread index.
 */

import { forwardRef, useRef, useCallback, useEffect } from 'react';
import HTMLFlipBook from 'react-pageflip';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Spread } from '@/lib/keynotes-paginate';
import Page, { PAGE_WIDTH, PAGE_HEIGHT } from './Page';
import { cn } from '@/lib/cn';

/** A Spread occupies two leaves. */
export const leafOfSpread = (spread: number) => spread * 2;
export const spreadOfLeaf = (leaf: number) => Math.floor(leaf / 2);

/**
 * One sheet, wrapped for StPageFlip.
 *
 * The library assigns each child its own transforms and needs a real element it
 * can measure, so the page is wrapped rather than styled directly — and the
 * wrapper must forward its ref or StPageFlip cannot register the leaf at all.
 */
const Leaf = forwardRef<HTMLDivElement, { children: React.ReactNode }>(
  function Leaf({ children }, ref) {
    return (
      <div ref={ref} className="bg-[#FDFBF7]">
        {children}
      </div>
    );
  },
);

export default function NotebookFlip({
  spreads,
  spreadIndex,
  onSpreadChange,
  renderHeader,
  runningHead,
}: {
  spreads: Spread[];
  spreadIndex: number;
  onSpreadChange: (next: number) => void;
  /** Title + Read control, rendered at the top of each left-hand sheet. */
  renderHeader?: (spread: Spread) => React.ReactNode;
  runningHead?: (spread: Spread, side: 'left' | 'right') => string;
}) {
  // The library's own instance, reached through the wrapper component.
  const book = useRef<{
    pageFlip?: () => {
      flipNext: () => void;
      flipPrev: () => void;
      turnToPage: (page: number) => void;
    };
  } | null>(null);

  /**
   * Which spread the BOOK is on, as opposed to which one React thinks it is on.
   *
   * These are two different things and conflating them is what broke the
   * buttons: `startPage` is read once at mount, so changing `spreadIndex`
   * afterwards moved the counter and the contents ribbon while the book itself
   * sat still. Tracking the book's own position separately lets the effect below
   * drive it, and lets `onFlip` report back without the two fighting each other
   * in a loop.
   */
  const atSpread = useRef(spreadIndex);

  const onFlip = useCallback(
    (e: { data: number }) => {
      const next = spreadOfLeaf(e.data);
      atSpread.current = next;
      if (next !== spreadIndex) onSpreadChange(next);
    },
    [spreadIndex, onSpreadChange],
  );

  // Drive the book when something outside it moves — a nav button, or the
  // contents page jumping to a topic.
  useEffect(() => {
    if (spreadIndex === atSpread.current) return;
    const flip = book.current?.pageFlip?.();
    if (!flip) return;

    const delta = spreadIndex - atSpread.current;
    atSpread.current = spreadIndex;

    // Step moves animate; a jump across the book does not — turning six pages
    // one by one to reach a topic is slower than it is charming.
    if (delta === 1) flip.flipNext();
    else if (delta === -1) flip.flipPrev();
    else flip.turnToPage(leafOfSpread(spreadIndex));
  }, [spreadIndex]);

  return (
    <div className="flex flex-col items-center">
      <div className="relative">
        {/* The rest of the book: sheet edges stacked behind the open spread, so
            it reads as a notebook with pages left in it rather than two cards. */}
        {[11, 7, 3].map((inset, i) => (
          <div
            key={inset}
            aria-hidden="true"
            className="absolute rounded-[30px] bg-[#EFEAE0]"
            style={{ inset: -inset, opacity: 0.5 - i * 0.13 }}
          />
        ))}

        <div
          className="relative rounded-[28px] border-2 border-[#A9D3F2] bg-white p-[6px]"
          style={{ boxShadow: '0 30px 70px -34px rgba(27,42,74,0.45)' }}
        >
          <div className="overflow-hidden rounded-[22px]">
            <HTMLFlipBook
              ref={book}
              width={PAGE_WIDTH}
              height={PAGE_HEIGHT}
              size="fixed"
              // Fixed size, so the min/max bounds are the page's own dimensions
              // rather than a range the library is free to reflow within.
              minWidth={PAGE_WIDTH}
              maxWidth={PAGE_WIDTH}
              minHeight={PAGE_HEIGHT}
              maxHeight={PAGE_HEIGHT}
              // Two sheets side by side, always. This is a desk notebook, not a
              // paperback, and portrait mode would collapse it to one page and
              // break the left/right split the content is written against.
              usePortrait={false}
              showCover={false}
              autoSize={false}
              startZIndex={0}
              drawShadow
              maxShadowOpacity={0.28}
              flippingTime={780}
              useMouseEvents
              mobileScrollSupport
              // Without this, a press on the Read button is swallowed by the
              // drag handler and the page never speaks.
              clickEventForward
              // Clicking the page turns it as well as dragging — that is how a
              // book behaves, and it keeps the turn reachable without a drag.
              disableFlipByClick={false}
              showPageCorners
              swipeDistance={24}
              startPage={leafOfSpread(spreadIndex)}
              onFlip={onFlip}
              className="notebook-flip"
              style={{}}
            >
              {spreads.flatMap((spread) => [
                <Leaf key={`${spread.topicId}-${spread.page}-l`}>
                  <Page
                    side="left"
                    sections={spread.left}
                    header={renderHeader?.(spread)}
                    footer={<Footer spread={spread} />}
                    runningHead={runningHead?.(spread, 'left')}
                  />
                </Leaf>,
                <Leaf key={`${spread.topicId}-${spread.page}-r`}>
                  <Page
                    side="right"
                    sections={spread.right}
                    footer={<Footer spread={spread} />}
                    runningHead={runningHead?.(spread, 'right')}
                  />
                </Leaf>,
              ])}
            </HTMLFlipBook>
          </div>
        </div>
      </div>

      <nav className="mt-6 flex items-center gap-3" aria-label="Notebook pages">
        <Turn
          dir="prev"
          disabled={spreadIndex <= 0}
          onClick={() => onSpreadChange(spreadIndex - 1)}
        />
        <span className="text-[12px] tabular-nums text-slate-blue min-w-[70px] text-center">
          {spreadIndex + 1} / {spreads.length}
        </span>
        <Turn
          dir="next"
          disabled={spreadIndex >= spreads.length - 1}
          onClick={() => onSpreadChange(spreadIndex + 1)}
        />
      </nav>

      <p className="mt-2.5 text-[11px] text-slate-blue/60">
        Drag a corner to turn the page
      </p>
    </div>
  );
}

function Footer({ spread }: { spread: Spread }) {
  if (spread.pages <= 1) return null;
  return (
    <p className="mt-auto pt-4 text-[11px] text-slate-blue text-right tabular-nums">
      {spread.page} of {spread.pages}
    </p>
  );
}

function Turn({
  dir,
  disabled,
  onClick,
}: {
  dir: 'prev' | 'next';
  disabled: boolean;
  onClick: () => void;
}) {
  const Icon = dir === 'prev' ? ChevronLeft : ChevronRight;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === 'prev' ? 'Previous page' : 'Next page'}
      className={cn(
        'w-9 h-9 rounded-full border border-muted-gray bg-white text-ink',
        'flex items-center justify-center transition-colors',
        'hover:border-focus-navy disabled:opacity-35 disabled:hover:border-muted-gray',
      )}
    >
      <Icon size={17} strokeWidth={2} />
    </button>
  );
}

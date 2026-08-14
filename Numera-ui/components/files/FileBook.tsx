'use client';

/**
 * A file, opened as a book.
 *
 * The shelf shows every file as a closed book, so opening one should open that
 * same object rather than swapping it for a document viewer — the cover you
 * clicked is the cover that turns. `showCover` puts the front and back boards
 * on their own, the way a real book opens: one cover, then spreads, then the
 * back cover.
 *
 * Like the Key Notes notebook this runs on StPageFlip, which animates on
 * requestAnimationFrame. It therefore turns normally in a browser and sits
 * still in the embedded Browser pane, which suppresses rAF.
 */

import { forwardRef, useEffect, useRef } from 'react';
import HTMLFlipBook from 'react-pageflip';
import { X } from 'lucide-react';
import type { FileItem, FileSheet } from '@/lib/files';
import { KIND } from '@/lib/files';

const W = 400;
const H = 540;
const RULE = 28;

/** StPageFlip measures each child, so every leaf must forward a real ref. */
const Leaf = forwardRef<HTMLDivElement, { children: React.ReactNode; hard?: boolean }>(
  function Leaf({ children }, ref) {
    return (
      <div ref={ref} className="overflow-hidden">
        {children}
      </div>
    );
  },
);

export default function FileBook({ file, onClose }: { file: FileItem; onClose: () => void }) {
  const kind = KIND[file.kind];
  const panel = useRef<HTMLDivElement>(null);

  // Escape closes, and focus moves into the dialog so a keyboard user is not
  // left behind on the shelf underneath.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    panel.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#1B2A4A]/55 p-6 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${file.name}, open`}
      onClick={onClose}
    >
      <div
        ref={panel}
        tabIndex={-1}
        className="relative outline-none"
        // The backdrop closes; the book itself must not.
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          aria-label="Close file"
          className="absolute -top-12 right-0 inline-flex items-center gap-1.5 rounded-full bg-white/95 px-3.5 py-2 text-[12px] font-semibold text-ink shadow-lg transition-colors hover:bg-white"
        >
          <X size={14} strokeWidth={2.4} />
          Close
        </button>

        {/* @ts-expect-error HTMLFlipBook's ref type is `any` and its prop types
            require the full settings object, which is supplied below. */}
        <HTMLFlipBook
          width={W}
          height={H}
          size="fixed"
          minWidth={W}
          maxWidth={W}
          minHeight={H}
          maxHeight={H}
          // The point of the exercise: front and back boards get a page each,
          // so the book opens from a closed cover instead of mid-spread.
          showCover
          usePortrait={false}
          autoSize={false}
          startPage={0}
          startZIndex={30}
          drawShadow
          maxShadowOpacity={0.4}
          flippingTime={760}
          useMouseEvents
          mobileScrollSupport
          clickEventForward
          disableFlipByClick={false}
          showPageCorners
          swipeDistance={24}
          className="file-book"
          style={{}}
        >
          <Leaf hard>
            <Cover file={file} color={kind.color} textColor={kind.textColor} label={kind.label} />
          </Leaf>

          {file.sheets.map((sheet, i) => (
            <Leaf key={`${file.id}-${i}`}>
              <Sheet sheet={sheet} page={i + 1} of={file.sheets.length} />
            </Leaf>
          ))}

          <Leaf hard>
            <BackCover color={kind.color} />
          </Leaf>
        </HTMLFlipBook>
      </div>
    </div>
  );
}

/**
 * The front board, built the same way as the closed book on the shelf: a band
 * of coloured cloth over a titled paper panel. It has to be the same object —
 * the cover you clicked is the cover that opens, and a flat one-colour board
 * here would read as a different book entirely.
 */
function Cover({
  file,
  color,
  textColor,
  label,
}: {
  file: FileItem;
  color: string;
  textColor: string;
  label: string;
}) {
  return (
    <div
      className="relative flex h-full flex-col overflow-hidden rounded-r-md"
      style={{ width: W, height: H }}
    >
      {/* Cloth band. */}
      <div className="relative flex flex-1 items-center justify-center" style={{ background: color }}>
        <span
          className="text-[11px] font-semibold uppercase tracking-[1.6px] opacity-80"
          style={{ color: textColor }}
        >
          {label}
        </span>
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[8.2%] mix-blend-overlay"
          style={{ background: 'var(--ds-book-bind)' }}
        />
      </div>

      {/* Titled panel. */}
      <div className="relative flex flex-1 flex-col justify-between bg-book-gradient px-10 py-9 pl-14">
        <div
          aria-hidden="true"
          className="absolute inset-y-0 left-0 w-[8.2%] opacity-20"
          style={{ background: 'var(--ds-book-bind)' }}
        />
        <h2 className="text-[26px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink">
          {file.name}
        </h2>
        <div>
          <p className="text-[12px] text-slate-blue">{file.meta}</p>
          <p className="mt-1.5 text-[11px] text-slate-blue/70">
            Numera · saved from your session
          </p>
        </div>
      </div>

      <div
        aria-hidden="true"
        className="book-texture pointer-events-none absolute inset-0 opacity-[0.35] mix-blend-soft-light"
      />
    </div>
  );
}

function BackCover({ color }: { color: string }) {
  return (
    <div
      className="relative h-full overflow-hidden rounded-l-md"
      style={{ width: W, height: H, background: color }}
    >
      <div
        aria-hidden="true"
        className="absolute inset-y-0 right-0 w-[8.2%] mix-blend-overlay"
        style={{ background: 'var(--ds-book-bind)' }}
      />
      <div
        aria-hidden="true"
        className="book-texture pointer-events-none absolute inset-0 opacity-[0.35] mix-blend-soft-light"
      />
    </div>
  );
}

function Sheet({ sheet, page, of }: { sheet: FileSheet; page: number; of: number }) {
  return (
    <div
      className="relative flex h-full flex-col bg-[#FDFBF7] px-9 pb-7 pt-8"
      style={{ width: W, height: H }}
    >
      {sheet.heading && (
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[1.1px] text-slate-blue">
          {sheet.heading}
        </p>
      )}

      <div
        className="flex-1"
        style={{
          backgroundImage: `repeating-linear-gradient(to bottom, transparent 0, transparent ${RULE - 1}px, rgba(27,42,74,0.07) ${RULE - 1}px, rgba(27,42,74,0.07) ${RULE}px)`,
        }}
      >
        {sheet.lines.map((line, i) => (
          <p
            key={`${line}-${i}`}
            className="font-[Cambria_Math,Georgia,serif] text-[14px] text-ink"
            style={{ lineHeight: `${RULE}px` }}
          >
            {line || ' '}
          </p>
        ))}
      </div>

      <p className="mt-auto pt-3 text-right text-[10.5px] tabular-nums text-slate-blue/70">
        {page} / {of}
      </p>
    </div>
  );
}

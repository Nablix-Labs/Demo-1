'use client';

/**
 * One sheet of notebook paper, and the sections printed on it.
 *
 * The paper is built rather than drawn: tooth comes from an inline SVG
 * turbulence filter and the rules from a repeating gradient, so there is no
 * raster asset to ship, nothing to go blurry on a retina screen, and the sheet
 * scales to any page size. Body text sits ON the rules — line-height matches the
 * rule pitch exactly — because text floating between ruled lines is the detail
 * that makes a paper effect read as wallpaper instead of paper.
 */

import type { Section } from '@/lib/keynotes-paginate';
import { cn } from '@/lib/cn';

/**
 * The geometry the capacities in keynotes-paginate.ts are derived from.
 *
 * A sheet is a FIXED size. Letting it grow to its content was the first cut's
 * mistake: pages of different heights read as panels, not paper, and the ruled
 * lines stopped short wherever the text did.
 */
export const RULE = 30;
export const PAGE_WIDTH = 540;
export const PAGE_HEIGHT = 720;

/** 720 less 40px top and 28px bottom padding, floored to whole rules. */
export const WRITING_HEIGHT = RULE * 21;

/**
 * Paper tooth. Low-frequency turbulence at low opacity — enough to break up a
 * flat fill under a real screen, invisible as a pattern.
 */
export const NOISE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E\")";

export default function Page({
  side,
  sections,
  header,
  footer,
  runningHead,
}: {
  side: 'left' | 'right';
  sections: Section[];
  header?: React.ReactNode;
  footer?: React.ReactNode;
  /** Small standing line at the top of the sheet, as a printed book carries. */
  runningHead?: string;
}) {
  return (
    <div
      className={cn(
        'relative flex flex-col overflow-hidden bg-[#FDFBF7]',
        // The gutter edge is squared off and slightly shaded: a sheet bound at
        // the spine does not have a rounded corner there, and the shadow is what
        // sells the fold.
        side === 'left'
          ? 'rounded-l-[20px] rounded-r-[3px]'
          : 'rounded-r-[20px] rounded-l-[3px]',
      )}
      style={{ width: PAGE_WIDTH, height: PAGE_HEIGHT, backgroundImage: NOISE }}
    >
      {/*
        The fold.

        This is the whole binding now — there is no hardware. Two gradients do
        it: a broad, soft falloff reaching ~90px into the sheet, which is the
        page curving down toward the spine, and a tight dark one in the last few
        pixels, which is the crease itself. One gradient alone reads as a drop
        shadow stuck to an edge; the pair reads as paper bending.
      */}
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-y-0 w-[90px]',
          side === 'left' ? 'right-0' : 'left-0',
        )}
        style={{
          background: `linear-gradient(to ${side === 'left' ? 'right' : 'left'}, rgba(27,42,74,0) 0%, rgba(27,42,74,0.035) 55%, rgba(27,42,74,0.10) 88%, rgba(27,42,74,0.15) 100%)`,
        }}
      />
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-y-0 w-[7px]',
          side === 'left' ? 'right-0' : 'left-0',
        )}
        style={{
          background: `linear-gradient(to ${side === 'left' ? 'right' : 'left'}, rgba(27,42,74,0) 0%, rgba(27,42,74,0.22) 100%)`,
        }}
      />

      <div className="relative flex flex-col flex-1 px-12 pt-8 pb-7 min-h-0">
        {/* Running head: the standing line a printed book carries above its
            text block, on the outer edge of each sheet. Cheap, and it does more
            than decoration — it is where you are in the notebook, permanently
            on the page rather than only under it. */}
        {runningHead && (
          <p
            className={cn(
              'mb-3 text-[9.5px] font-semibold uppercase tracking-[1.1px] text-slate-blue/55',
              side === 'left' ? 'text-left' : 'text-right',
            )}
          >
            {runningHead}
          </p>
        )}

        {header}

        <div
          className="flex-1 min-h-0"
          style={{
            // The rules. Drawn under the text, stopping short of the last line
            // so the page does not end on a stray rule.
            backgroundImage:
              'repeating-linear-gradient(to bottom, transparent 0, transparent ' +
              (RULE - 1) +
              'px, rgba(27,42,74,0.07) ' +
              (RULE - 1) +
              'px, rgba(27,42,74,0.07) ' +
              RULE +
              'px)',
          }}
        >
          {sections.map((section) => (
            <SectionBlock key={section.kind} section={section} />
          ))}
        </div>

        {footer}
      </div>
    </div>
  );
}

/** Small-caps section label, sitting on its own rule. */
function Label({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[10.5px] font-semibold uppercase tracking-[0.9px] text-slate-blue"
      style={{ lineHeight: `${RULE}px` }}
    >
      {children}
    </p>
  );
}

const bodyStyle = { lineHeight: `${RULE}px` };

function SectionBlock({ section }: { section: Section }) {
  const { kind, label, body } = section;

  return (
    <section>
      {label && <Label>{label}</Label>}

      {/* The opening description, set a little larger — it is the answer to
          "what even is this topic", and a student scanning wants it first. */}
      {kind === 'meaning' && (
        <p className="text-[14.5px] text-ink" style={bodyStyle}>
          {body as string}
        </p>
      )}

      {/* The rule, in the reference's tinted card. This is the one thing on the
          page a student is most likely to be hunting for, so it is the one
          thing allowed to break the ruled grid. */}
      {kind === 'formula' && (
        <div className="my-1 rounded-[14px] bg-[#EEF2FB] px-5 py-4 text-center">
          <p className="font-[Cambria_Math,Georgia,serif] text-[16px] text-ink leading-snug">
            {body as string}
          </p>
        </div>
      )}

      {kind === 'example' && (
        <div className="font-[Cambria_Math,Georgia,serif] text-[14.5px] text-ink">
          {(body as string[]).map((line) => (
            <p key={line} style={bodyStyle}>
              {line}
            </p>
          ))}
        </div>
      )}

      {kind === 'steps' && (
        <ol className="text-[13.5px] text-ink">
          {(body as string[]).map((item, i) => (
            <li key={item} className="flex gap-2.5" style={bodyStyle}>
              <span className="flex-shrink-0 font-semibold text-learning-blue">{i + 1}.</span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      )}

      {(kind === 'beCareful' || kind === 'tips') && (
        <ul className="text-[13.5px] text-ink">
          {(body as string[]).map((item) => (
            <li key={item} className="flex gap-2.5" style={bodyStyle}>
              <span
                aria-hidden="true"
                className={cn(
                  'flex-shrink-0',
                  kind === 'tips' ? 'text-highlight-amber' : 'text-slate-blue',
                )}
              >
                {kind === 'tips' ? '✦' : '•'}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}

      {(kind === 'howToStart' || kind === 'examTip') && (
        <p className="text-[13.5px] text-ink" style={bodyStyle}>
          {body as string}
        </p>
      )}
    </section>
  );
}

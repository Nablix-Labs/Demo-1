import { Lightbulb } from 'lucide-react';

/**
 * A hint, as a sticky note stuck to the canvas.
 *
 * It used to be a white rounded card, which read as another piece of app
 * chrome — the same visual weight as the toolbar and the status pills. A hint
 * is not chrome: it is something the tutor has left for the student, and it
 * should look placed rather than rendered.
 *
 * Hence paper rather than a panel — warm stock, squared corners (post-its are
 * barely rounded), a slight rotation so it is not aligned to the grid, and a
 * shadow weighted to the bottom edge so the paper looks like it is lifting off
 * the surface. Amber matches the hint accent already used in the session trail,
 * so the two read as the same thing in different places.
 *
 * Positioning belongs entirely to the caller. The note deliberately sets no
 * position class of its own: an earlier version hardcoded `relative`, which
 * collided with the `absolute` callers pass in — same specificity, so the
 * winner came down to Tailwind's emit order rather than intent, and notes
 * silently ignored their placement. The decorations hang off an inner wrapper
 * instead.
 */
export default function HintNote({
  children,
  label = 'Gentle hint',
  className = '',
}: {
  children: React.ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <div
      className={`max-w-[19rem] select-none ${className}`}
      style={{
        transform: 'rotate(-1.6deg)',
        background: 'linear-gradient(180deg, #FFF1C9 0%, #FFE9AE 100%)',
        borderRadius: 3,
        // Two shadows: a tight contact shadow under the paper, and a softer
        // cast further out. One shadow alone reads as a floating rectangle.
        boxShadow: '0 1px 2px rgba(90,64,10,.18), 0 10px 22px -6px rgba(90,64,10,.30)',
      }}
      role="note"
    >
      <div style={{ position: 'relative', padding: '13px 15px 15px' }}>
        {/* The adhesive strip along the top — slightly darker stock, the way
            the glued band on a real pad shows through. */}
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            inset: '0 0 auto 0',
            height: 16,
            borderRadius: '3px 3px 0 0',
            background: 'linear-gradient(180deg, rgba(180,140,30,.14), rgba(180,140,30,0))',
            pointerEvents: 'none',
          }}
        />

        <div className="relative flex items-start gap-2.5">
          <Lightbulb size={15} strokeWidth={1.9} className="mt-[1px] flex-shrink-0 text-[#8A6407]" />
          <div className="min-w-0">
            <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-widest text-[#8A6407]">
              {label}
            </div>
            <p className="text-[12.5px] leading-snug text-[#3A2E10]">{children}</p>
          </div>
        </div>

        {/* Turned-up bottom-right corner. The lighter wedge is the underside of
            the paper; the shadow under it is what sells the lift. */}
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            right: 0,
            bottom: 0,
            width: 18,
            height: 18,
            background:
              'linear-gradient(135deg, rgba(0,0,0,.10) 0%, rgba(0,0,0,.02) 45%, #FFF6DA 46%)',
            borderRadius: '3px 0 3px 0',
            pointerEvents: 'none',
          }}
        />
      </div>
    </div>
  );
}

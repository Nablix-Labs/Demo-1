'use client';

/**
 * The tutor panel's drag edge.
 *
 * Pointer events rather than mouse events, so a pen or a touch drag works the
 * same way — this app is used on a tablet with a stylus, where a mouse-only
 * handle would simply not exist.
 *
 * `setPointerCapture` is what makes the drag survive leaving the handle. A
 * 5px-wide target is easy to outrun, and without capture the drag stops the
 * moment the pointer crosses onto the canvas — which is exactly where it is
 * going. Capture also means the canvas never sees these moves, so dragging the
 * edge cannot leave a stroke behind.
 */

import { useCallback, useRef } from 'react';
import { useNumeraStore, PANEL_WIDTH_MIN, panelWidthMax } from '@/store/useNumeraStore';
import { cn } from '@/lib/cn';

/** How far one arrow-key press moves the edge. Shift multiplies it. */
const STEP = 16;

export default function ResizeHandle({
  side,
  onDraggingChange,
}: {
  side: 'left' | 'right';
  /** Lets the panel drop its width transition while the edge is being dragged. */
  onDraggingChange: (dragging: boolean) => void;
}) {
  const panelWidth = useNumeraStore((s) => s.panelWidth);
  const setPanelWidth = useNumeraStore((s) => s.setPanelWidth);
  const resetPanelWidth = useNumeraStore((s) => s.resetPanelWidth);
  const draggingRef = useRef(false);

  const widthFor = useCallback(
    (clientX: number) => {
      // Measure from the window edge the panel is docked to, so the same
      // gesture means "make it wider" on both sides.
      const raw = side === 'left' ? clientX : window.innerWidth - clientX;
      setPanelWidth(raw);
    },
    [side, setPanelWidth],
  );

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    // Left button / primary contact only: a right-click drag would resize the
    // panel while the context menu is open.
    if (e.button !== 0) return;
    e.preventDefault();
    draggingRef.current = true;
    onDraggingChange(true);
    e.currentTarget.setPointerCapture(e.pointerId);
    // The cursor must not flicker back to default over the canvas mid-drag, and
    // text elsewhere on the page must not start selecting.
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [onDraggingChange]);

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return;
      widthFor(e.clientX);
    },
    [widthFor],
  );

  const endDrag = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    onDraggingChange(false);
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, [onDraggingChange]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const step = e.shiftKey ? STEP * 4 : STEP;
      // Arrow direction is screen direction, not "bigger/smaller" — pressing
      // right moves the edge right, whichever side the panel is docked to.
      const grow = side === 'left' ? 'ArrowRight' : 'ArrowLeft';
      const shrink = side === 'left' ? 'ArrowLeft' : 'ArrowRight';
      if (e.key === grow) setPanelWidth(panelWidth + step);
      else if (e.key === shrink) setPanelWidth(panelWidth - step);
      else if (e.key === 'Home') resetPanelWidth();
      else return;
      e.preventDefault();
    },
    [side, panelWidth, setPanelWidth, resetPanelWidth],
  );

  return (
    <div
      // `separator` with an orientation and value range is what tells a screen
      // reader this is a splitter and where it currently sits, rather than an
      // unlabelled div that happens to be draggable.
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize tutor panel"
      aria-valuenow={panelWidth}
      aria-valuemin={PANEL_WIDTH_MIN}
      aria-valuemax={panelWidthMax()}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onDoubleClick={resetPanelWidth}
      onKeyDown={onKeyDown}
      title="Drag to resize · double-click to reset"
      className={cn(
        // Narrow line, wide grab area: the visible affordance is 1px of glass
        // but the hit target is 9px, because a 1px target is a fight.
        'group absolute inset-y-0 z-20 w-[9px] cursor-col-resize touch-none',
        'flex items-center justify-center',
        'focus-visible:outline-none',
        side === 'left' ? '-right-[4px]' : '-left-[4px]',
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'h-10 w-[3px] rounded-full bg-slate-blue/25 opacity-0 transition-opacity duration-150',
          'group-hover:opacity-100 group-focus-visible:opacity-100 group-active:opacity-100',
        )}
      />
    </div>
  );
}

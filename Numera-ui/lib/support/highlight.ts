'use client';

/**
 * Nablix Assist — DOM highlighting.
 *
 * The Konva tutor layer highlights in normalised canvas coordinates, which
 * can't point at real UI controls — so support-mode highlighting is a DOM
 * overlay (driver.js) targeting elements tagged with data-support-id.
 *
 * Non-blocking by design: the spotlight auto-removes after a few seconds and
 * the highlighted element stays clickable, so the student can follow the
 * instruction while it's shown.
 */

import { driver, type Driver } from 'driver.js';
import 'driver.js/dist/driver.css';

const AUTO_REMOVE_MS = 8_000;

let active: Driver | null = null;
let removeTimer: ReturnType<typeof setTimeout> | null = null;

export function clearHighlight(): void {
  if (removeTimer) clearTimeout(removeTimer);
  removeTimer = null;
  active?.destroy();
  active = null;
}

/**
 * Spotlight the element tagged data-support-id={id}: scroll it into view,
 * pulse it under a dimmed overlay, auto-remove. Returns false when the
 * element isn't on the current screen so the caller can report "not found"
 * instead of failing silently.
 */
export function highlightBySupportId(id: string, text?: string): boolean {
  if (typeof document === 'undefined') return false;
  const el = document.querySelector<HTMLElement>(`[data-support-id="${id}"]`);
  if (!el) return false;

  clearHighlight();
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });

  active = driver({
    animate: true,
    overlayOpacity: 0.35,
    allowClose: true,
    stagePadding: 6,
    stageRadius: 10,
  });
  active.highlight({
    element: el,
    popover: text ? { description: text, showButtons: [] } : undefined,
  });

  removeTimer = setTimeout(clearHighlight, AUTO_REMOVE_MS);
  return true;
}
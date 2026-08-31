/**
 * Coming back from a rescue actually returns the student.
 *
 * Sanya's rescue handoff, item 3: "Final step: return focus to the original
 * problem and restore normal input." What shipped instead was
 * `console.log('[rescue] returning to', returnTarget)` — the panel closed and
 * nothing else happened, which is indistinguishable from the return working
 * right up until someone watches a student sit there.
 *
 * These assert the OUTCOME rather than that a function was called, because
 * "we invoked the return" is exactly the claim the console.log could also have
 * made.
 */

import { describe, expect, it, vi } from 'vitest';
import {
  returnToQuestion, findReturnSurfaces, COMPOSER_LABEL,
} from '@/lib/rescueReturn';

const surfaces = (over: Partial<Parameters<typeof returnToQuestion>[0]> = {}) => ({
  question: { scrollIntoView: vi.fn() },
  composer: { focus: vi.fn() },
  ...over,
});

describe('returning to the question', () => {
  it('puts the question back in view and the caret back in the input', () => {
    const s = surfaces();
    const outcome = returnToQuestion(s);

    expect(s.question!.scrollIntoView).toHaveBeenCalledOnce();
    expect(s.composer!.focus).toHaveBeenCalledOnce();
    expect(outcome).toEqual({ scrolledToQuestion: true, focusedComposer: true });
  });

  it('scrolls gently rather than yanking a settled page', () => {
    // The question is usually already visible; a centring scroll on every
    // return reads as a glitch rather than a return.
    const s = surfaces();
    returnToQuestion(s);
    expect(s.question!.scrollIntoView).toHaveBeenCalledWith({
      block: 'nearest', behavior: 'smooth',
    });
  });

  it('still focuses the input when there is no question element', () => {
    const s = surfaces({ question: null });
    const outcome = returnToQuestion(s);

    expect(s.composer!.focus).toHaveBeenCalledOnce();
    expect(outcome).toEqual({ scrolledToQuestion: false, focusedComposer: true });
  });

  it('still scrolls in a voice-only layout with no composer', () => {
    const s = surfaces({ composer: null });
    const outcome = returnToQuestion(s);

    expect(s.question!.scrollIntoView).toHaveBeenCalledOnce();
    expect(outcome).toEqual({ scrolledToQuestion: true, focusedComposer: false });
  });

  it('reports honestly when it could do neither', () => {
    // The value of the return type: a caller (or a test) can tell "returned"
    // from "found nothing to return to".
    expect(returnToQuestion({ question: null, composer: null }))
      .toEqual({ scrolledToQuestion: false, focusedComposer: false });
  });
});

describe('finding the surfaces', () => {
  const docWith = (html: string): Document => {
    const doc = document.implementation.createHTMLDocument('t');
    doc.body.innerHTML = html;
    return doc;
  };

  it('finds the question strip and the composer', () => {
    const doc = docWith(
      `<div data-question-text>Solve 3x + 6 = 18</div>
       <input aria-label="${COMPOSER_LABEL}" />`,
    );
    const found = findReturnSurfaces(doc);
    expect(found.question).not.toBeNull();
    expect(found.composer).not.toBeNull();
  });

  it('returns nulls rather than throwing when the layout has neither', () => {
    // A rescue on a screen without a composer must still be dismissable.
    const found = findReturnSurfaces(docWith('<main></main>'));
    expect(found.question).toBeNull();
    expect(found.composer).toBeNull();
  });

  it('does not mistake another input for the composer', () => {
    const found = findReturnSurfaces(docWith('<input aria-label="Search" />'));
    expect(found.composer).toBeNull();
  });
});

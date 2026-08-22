/**
 * The tutor points at things by id. These tests are about what happens when the
 * id resolves to nothing, and about the two things the tutor must never do.
 */

import { describe, expect, it } from 'vitest';
import {
  resolveTarget, actionMarks, revealsAnswer, showsWriteAffordance, memoryActionType, memoryActor,
  overlapsWriteArea, relocateWriteRequest, WRITE_AREA,
  type ResolveContext,
} from '@/lib/tutorCanvasActions';
import type { TutorCanvasAction, DrawnItem, TutorElement } from '@/store/useNumeraStore';

const action = (over: Partial<TutorCanvasAction> = {}): TutorCanvasAction => ({
  action_id: 'ACT-1',
  type: 'HIGHLIGHT',
  target_kind: 'CANVAS_OBJECT',
  target_object_id: 'item-1',
  confirmed_component_id: null,
  text: null,
  source_id: null,
  answer_reveal_allowed: false,
  ...over,
});

const ITEM: DrawnItem = {
  id: 'item-1', kind: 'rect', x: 100, y: 50, w: 200, h: 100, color: '#000', size: 2,
};

const CTX: ResolveContext = {
  anchors: [{ token_id: 'TOK-1', text: 'm', char_start: 0, char_end: 1 }],
  questionId: 'Q1',
  items: [ITEM],
  tutorElements: [{ id: 'tut-1', kind: 'text', x: 0.1, y: 0.2, text: 'n + 4' }],
  canvasSize: { width: 1000, height: 500 },
};

describe('resolving a target the client cannot see', () => {
  it('drops a canvas object the student has since erased', () => {
    // The alternative is placing the mark somewhere plausible, which puts the
    // tutor confidently pointing at the wrong thing — worse than not pointing.
    expect(resolveTarget(action({ target_object_id: 'gone' }), CTX)).toBeNull();
  });

  it('drops an anchor that is not on the current question', () => {
    expect(resolveTarget(
      action({ target_kind: 'QUESTION_ANCHOR', target_object_id: 'TOK-NOPE' }), CTX,
    )).toBeNull();
  });

  it('drops an action carrying no target id at all', () => {
    expect(resolveTarget(action({ target_object_id: null }), CTX)).toBeNull();
  });

  it('drops a canvas object when the canvas has not been measured yet', () => {
    // itemBBox refuses to divide by a zero size; a box built against a
    // placeholder would be a plausible-looking lie.
    expect(resolveTarget(action(), { ...CTX, canvasSize: { width: 0, height: 0 } })).toBeNull();
  });
});

describe('resolving a target that is there', () => {
  it('finds a student item and normalises it against the live canvas', () => {
    const target = resolveTarget(action(), CTX);
    expect(target).toEqual({ kind: 'box', box: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 } });
  });

  it('finds a question anchor by token id', () => {
    expect(resolveTarget(
      action({ target_kind: 'QUESTION_ANCHOR', target_object_id: 'TOK-1' }), CTX,
    )).toEqual({ kind: 'anchor', tokenId: 'TOK-1' });
  });

  it('treats STUDENT_ATTEMPT the same as CANVAS_OBJECT — both name drawn work', () => {
    expect(resolveTarget(action({ target_kind: 'STUDENT_ATTEMPT' }), CTX))
      .toEqual(resolveTarget(action({ target_kind: 'CANVAS_OBJECT' }), CTX));
  });

  it('resolves a WRITE_AREA without needing an id', () => {
    expect(resolveTarget(action({ target_kind: 'WRITE_AREA', target_object_id: null }), CTX))
      .toEqual({ kind: 'write-area' });
  });
});

describe('what must never be rendered', () => {
  it('never writes into the write area, even when text is supplied', () => {
    // The rule with teeth. WRITE_AREA is where the student is being asked to
    // commit the answer; writing it there hands over the thing being asked for,
    // while looking like ordinary tutor support.
    const write = action({
      target_kind: 'WRITE_AREA', type: 'INSERT_MATH', text: 'n + 4', target_object_id: null,
    });
    const target = resolveTarget(write, CTX)!;
    expect(actionMarks(write, target)).toEqual([]);
    expect(showsWriteAffordance(write)).toBe(true);
  });

  it('grants no answer reveal however the payload is flagged', () => {
    // The flag is the backend's own record, never our permission slip.
    expect(revealsAnswer()).toBe(false);
  });

  it('renders a flagged action exactly as it renders an unflagged one', () => {
    const target = resolveTarget(action(), CTX)!;
    expect(actionMarks(action({ answer_reveal_allowed: true }), target))
      .toEqual(actionMarks(action({ answer_reveal_allowed: false }), target));
  });

  it('puts no canvas mark on a question-text anchor', () => {
    // The label rides on the text, which is the only thing that knows where the
    // token wrapped to. A box on the board would mark something not on the board.
    const a = action({ target_kind: 'QUESTION_ANCHOR', target_object_id: 'TOK-1', type: 'INSERT_LABEL', text: 'changes' });
    expect(actionMarks(a, resolveTarget(a, CTX)!)).toEqual([]);
  });
});

describe('the marks themselves', () => {
  const boxTarget = { kind: 'box' as const, box: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 } };

  it('highlights on the tutor layer, leaving the student item untouched', () => {
    const marks = actionMarks(action({ type: 'HIGHLIGHT' }), boxTarget);
    expect(marks).toHaveLength(1);
    expect(marks[0].kind).toBe('highlight');
    // Student ink is never in the output — marks are additive, never edits.
    expect(CTX.items).toEqual([ITEM]);
  });

  it('draws GROUP as an outline, not a fill, so it stays legible over a highlight', () => {
    expect(actionMarks(action({ type: 'GROUP' }), boxTarget)[0].kind).toBe('rect');
  });

  it('points an ARROW at the target from clear of it', () => {
    const arrow = actionMarks(action({ type: 'ARROW' }), boxTarget)[0];
    expect(arrow.kind).toBe('arrow');
    expect(arrow.to).toEqual([boxTarget.box.x - 0.012, boxTarget.box.y - 0.012]);
    // Approaches from above-left, so it never crosses the work it points at.
    expect(arrow.from![0]).toBeLessThan(arrow.to![0]);
    expect(arrow.from![1]).toBeLessThan(arrow.to![1]);
  });

  it('writes INSERT_MATH below the work it comments on', () => {
    const mark = actionMarks(action({ type: 'INSERT_MATH', text: 'n + 4' }), boxTarget)[0];
    expect(mark.kind).toBe('math');
    expect(mark.text).toBe('n + 4');
    expect(mark.y!).toBeGreaterThan(boxTarget.box.y + boxTarget.box.h);
  });

  it('draws nothing for an INSERT with no text rather than an empty box', () => {
    expect(actionMarks(action({ type: 'INSERT_MATH', text: '   ' }), boxTarget)).toEqual([]);
  });

  it('draws nothing for FOCUS — it moves attention without leaving a mark', () => {
    expect(actionMarks(action({ type: 'FOCUS' }), boxTarget)).toEqual([]);
  });

  it('gives every mark an id derived from the action, so a replay overwrites', () => {
    expect(actionMarks(action({ type: 'HIGHLIGHT' }), boxTarget)[0].id).toContain('ACT-1');
  });
});

describe('the canvas-memory vocabulary', () => {
  it('renames OPEN_SCAFFOLD_STEP to the name ordered memory uses', () => {
    // The one name that differs between the two vocabularies. A caller that
    // assigned the raw value did not compile, which is how this was found.
    expect(memoryActionType('OPEN_SCAFFOLD_STEP')).toBe('SCAFFOLD_STEP');
  });

  it('passes every other type through unchanged', () => {
    for (const t of ['HIGHLIGHT', 'GROUP', 'ARROW', 'INSERT_MATH', 'INSERT_LABEL', 'FOCUS'] as const) {
      expect(memoryActionType(t)).toBe(t);
    }
  });

  it('files the support rungs against the system, not the tutor', () => {
    // A cue is the system serving support; it is not the tutor drawing.
    expect(memoryActor('SHOW_CUE')).toBe('SYSTEM_SUPPORT');
    expect(memoryActor('OPEN_SCAFFOLD_STEP')).toBe('SYSTEM_SUPPORT');
    expect(memoryActor('HIGHLIGHT')).toBe('TUTOR');
  });
});

describe('the reference label ladder', () => {
  const anchor = (position: number, text: string): TutorCanvasAction => ({
    action_id: `T${position}:CONFIRMED_SLOT:${position}:INSERT_LABEL`,
    type: 'INSERT_LABEL',
    target_kind: 'TUTOR_ANCHOR',
    target_object_id: `TUTOR_ANCHOR:WRITE_RULE:${position}`,
    confirmed_component_id: null,
    text,
    source_id: null,
    answer_reveal_allowed: false,
  });

  const confirmed = (turn: number, text: string): TutorCanvasAction => ({
    ...anchor(turn, text),
    action_id: `T${turn}:CONFIRMED_SLOT:1`,
    // Every turn numbers itself from 1 — that is the backend's actual output.
    target_object_id: `TUTOR_ANCHOR:CONFIRMED:${CTX.questionId}:1`,
  });

  /** Place a run of actions the way the store does: elements accumulate. */
  const place = (actions: TutorCanvasAction[]): TutorElement[] => {
    let tutorElements: TutorElement[] = [];
    for (const a of actions) {
      const target = resolveTarget(a, { ...CTX, tutorElements });
      if (target) tutorElements = [...tutorElements, ...actionMarks(a, target)];
    }
    return tutorElements;
  };

  /** The label's own footprint, generously sized so near-misses still count. */
  const footprint = (mark: { x?: number; y?: number }) => ({
    x: mark.x!, y: mark.y! - 0.03, w: 0.30, h: 0.06,
  });

  it('gives each confirmation its own row, however the backend numbers them', () => {
    // Sanya's m + 7 report: "m → changes", "7 → fixed" and "+ → addition"
    // arrive on three separate turns, each numbered position 1, and all three
    // were written on top of each other. Position is the backend's per-turn
    // counter; only the client knows what is already on the board.
    const marks = place([
      confirmed(1, 'm → changes'),
      confirmed(2, '7 → stays fixed'),
      confirmed(3, '+ → addition'),
    ]);
    expect(marks).toHaveLength(3);
    const ys = marks.map((m) => m.y!);
    expect(new Set(ys).size).toBe(3);
    expect(ys[0]).toBeLessThan(ys[1]);
    expect(ys[1]).toBeLessThan(ys[2]);
  });

  it('keeps confirmations and WRITE_RULE parts off each other', () => {
    // They share one ladder precisely so they cannot collide: confirmations
    // persist across turns, so a question with three of them that then reaches
    // a WRITE turn used to stack the rule parts straight through them.
    const marks = place([
      confirmed(1, 'm → changes'),
      confirmed(2, '7 → stays fixed'),
      confirmed(3, '+ → addition'),
      anchor(1, 'Start: m'),
      anchor(2, 'Gain: +7'),
    ]);
    const ys = marks.map((m) => m.y!).sort((a, b) => a - b);
    for (let i = 1; i < ys.length; i += 1) {
      expect(ys[i] - ys[i - 1], `rows ${i - 1} and ${i} overlap`).toBeGreaterThanOrEqual(0.06);
    }
  });

  it('never lands on the writing area or its prompt', () => {
    // The bug Sanya screenshotted: "Start: n" rendered on top of "Write your
    // rule here." and "Gain: +5" inside the highlight band. The labels are a
    // reference; the band is where the student answers. They cannot share space.
    for (const mark of place([1, 2, 3, 4, 5, 6, 7, 8].map((p) => anchor(p, 'Start: n')))) {
      expect(overlapsWriteArea(footprint(mark)), 'a slot overlaps the write area').toBe(false);
    }
  });

  it('reads top to bottom, in the order the backend listed the parts', () => {
    // Stacking upward put "Gain: +5" above "Start: n" — the rule read backwards.
    const ys = place([anchor(1, 'a'), anchor(2, 'b')]).map((m) => m.y!);
    expect(ys[0]).toBeLessThan(ys[1]);
  });

  it('never walks off the canvas, however many parts arrive', () => {
    for (const mark of place(Array.from({ length: 40 }, (_, i) => anchor(i + 1, 'x')))) {
      expect(mark.y!).toBeGreaterThanOrEqual(0);
      expect(mark.y!).toBeLessThanOrEqual(1);
    }
  });

  it('places the text at the slot itself, not offset beneath it', () => {
    const a = anchor(1, 'Start: n');
    const target = resolveTarget(a, CTX)!;
    const mark = actionMarks(a, target)[0];
    expect(target.kind).toBe('slot');
    expect(mark.y).toBe((target as { at: { y: number } }).at.y);
  });

  it('renders nothing for a slot with no text', () => {
    expect(actionMarks(anchor(1, '   '), resolveTarget(anchor(1, '   '), CTX)!)).toEqual([]);
  });

  it('does not count ordinary tutor marks as occupied rows', () => {
    // Only slot marks take a row. A highlight on the student's ink is not a
    // reference label and must not push the ladder down the canvas.
    const highlight: TutorElement = { id: 'X:hl', kind: 'highlight', points: [0, 0, 1, 1] };
    const first = resolveTarget(anchor(1, 'x'), CTX) as { at: { y: number } };
    const after = resolveTarget(anchor(1, 'x'), { ...CTX, tutorElements: [highlight] }) as { at: { y: number } };
    expect(after.at.y).toBe(first.at.y);
  });
});

describe('a HIGHLIGHT mark', () => {
  it('carries points, because that is the only thing the layer draws it from', () => {
    // TutorLayer's `highlight` case reads `el.points` and returns null without
    // them. Emitting x/y/w/h meant every highlight rendered nothing at all —
    // and highlighting is the most common action the tutor sends.
    const a = action({ type: 'HIGHLIGHT' });
    const mark = actionMarks(a, resolveTarget(a, CTX)!)[0];
    expect(mark.points?.length).toBeGreaterThanOrEqual(4);
  });

  it('draws a level band across the target, like a highlighter pen', () => {
    const a = action({ type: 'HIGHLIGHT' });
    const pts = actionMarks(a, resolveTarget(a, CTX)!)[0].points!;
    expect(pts[1]).toBe(pts[3]);      // same y at both ends
    expect(pts[2]).toBeGreaterThan(pts[0]);
    expect(actionMarks(a, resolveTarget(a, CTX)!)[0].strokeWidth).toBeGreaterThan(0);
  });
});

describe('the writing block on the left', () => {
  const backendWriteRequest = (turnId: string) => ([
    { id: `${turnId}:write-highlight`, kind: 'highlight' as const,
      points: [0.58, 0.62, 0.92, 0.62, 0.92, 0.74, 0.58, 0.74] },
    { id: `${turnId}:write-prompt`, kind: 'text' as const,
      x: 0.62, y: 0.66, text: 'Write your rule here.' },
    { id: `${turnId}:write-arrow`, kind: 'arrow' as const,
      from: [0.75, 0.56] as [number, number], to: [0.75, 0.62] as [number, number] },
  ]);

  it('moves the whole block off the right-hand column', () => {
    // The right column holds the cue card, the hint note and the "write it
    // down" note. The backend hardcodes the block at x 0.58-0.92, which put it
    // underneath them — the student had nowhere to write.
    for (const el of relocateWriteRequest(backendWriteRequest('T1'))) {
      const xs = [
        ...(el.points ?? []).filter((_, i) => i % 2 === 0),
        ...(el.from ? [el.from[0]] : []),
        ...(el.to ? [el.to[0]] : []),
        ...(el.x !== undefined ? [el.x] : []),
      ];
      for (const x of xs) expect(x, `${el.id} still at x=${x}`).toBeLessThan(0.5);
    }
  });

  it('keeps the arrow pointing into the band, not past it', () => {
    const arrow = relocateWriteRequest(backendWriteRequest('T1'))
      .find((e) => e.id.endsWith(':write-arrow'))!;
    expect(arrow.from![1]).toBeLessThan(arrow.to![1]);
    expect(arrow.to![1]).toBe(WRITE_AREA.y);
  });

  it('puts the prompt inside the band it labels', () => {
    const prompt = relocateWriteRequest(backendWriteRequest('T1'))
      .find((e) => e.id.endsWith(':write-prompt'))!;
    expect(prompt.x!).toBeGreaterThanOrEqual(WRITE_AREA.x);
    expect(prompt.x!).toBeLessThan(WRITE_AREA.x + WRITE_AREA.w);
    expect(prompt.y!).toBeGreaterThanOrEqual(WRITE_AREA.y);
    expect(prompt.y!).toBeLessThan(WRITE_AREA.y + WRITE_AREA.h);
  });

  it('leaves every other tutor element exactly as sent', () => {
    // Only the three hand-positioned elements are the client's business.
    const other = { id: 'T1:something-else', kind: 'text' as const, x: 0.8, y: 0.9, text: 'hi' };
    expect(relocateWriteRequest([other])).toEqual([other]);
  });

  it('keeps the reference labels clear of the relocated band', () => {
    for (const position of [1, 2, 3]) {
      const a: TutorCanvasAction = {
        action_id: `T:${position}`, type: 'INSERT_LABEL', target_kind: 'TUTOR_ANCHOR',
        target_object_id: `TUTOR_ANCHOR:WRITE_RULE:${position}`,
        confirmed_component_id: null, text: 'Start: n', source_id: null,
        answer_reveal_allowed: false,
      };
      const mark = actionMarks(a, resolveTarget(a, CTX)!)[0];
      expect(overlapsWriteArea({ x: mark.x!, y: mark.y! - 0.03, w: 0.30, h: 0.06 })).toBe(false);
    }
  });

  it('renders the labels bolder than an ordinary mark', () => {
    const a: TutorCanvasAction = {
      action_id: 'T:1', type: 'INSERT_LABEL', target_kind: 'TUTOR_ANCHOR',
      target_object_id: 'TUTOR_ANCHOR:WRITE_RULE:1',
      confirmed_component_id: null, text: 'Start: n', source_id: null,
      answer_reveal_allowed: false,
    };
    expect(actionMarks(a, resolveTarget(a, CTX)!)[0].fontStyle).toBe('bold');
  });
});

/**
 * The store half: idempotency, phase refusal, and the acknowledgement contract.
 *
 * These cannot live in lib/tutorCanvasActions because they are about state that
 * survives across turns — which action ids have been seen, and when that memory
 * is allowed to reset.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useNumeraStore, type TutorCanvasAction, type DrawnItem } from '@/store/useNumeraStore';

const ITEM: DrawnItem = {
  id: 'item-1', kind: 'rect', x: 100, y: 50, w: 200, h: 100, color: '#000', size: 2,
};

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

function ready() {
  const s = useNumeraStore.getState();
  s.reset();
  useNumeraStore.setState({
    currentPhase: 'GUIDED_PRACTICE',
    items: [ITEM],
    canvasSize: { width: 1000, height: 500 },
    activeQuestionId: 'Q1',
  });
  s.clearTutorMarks();
}

beforeEach(ready);

describe('idempotency', () => {
  it('renders a re-delivered action once', () => {
    // A reconnect replays the turn. Rendering twice would show the tutor
    // making the same teaching move again.
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    const after1 = useNumeraStore.getState().tutorElements.length;
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements).toHaveLength(after1);
    expect(after1).toBeGreaterThan(0);
  });

  it('lets the same action_id render again on a different question', () => {
    // The window is question-scoped. Held across the boundary, an id reused on
    // the next question is swallowed as a duplicate and the tutor goes silent.
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements.length).toBeGreaterThan(0);

    useNumeraStore.getState().applyBackendPhase({
      current_phase: 'GUIDED_PRACTICE', question_id: 'Q2', current_question: 'next',
    } as never);
    useNumeraStore.setState({ items: [ITEM], canvasSize: { width: 1000, height: 500 } });

    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements.length).toBeGreaterThan(0);
  });
});

describe('an action whose target is not on screen', () => {
  it('is dropped, and is not acknowledged as rendered', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    useNumeraStore.getState().applyTutorCanvasActions([action({ target_object_id: 'gone' })]);
    expect(useNumeraStore.getState().tutorElements).toHaveLength(0);
    // The ack means "this is on screen", so an unrendered action must not emit one.
    const acks = useNumeraStore.getState().canvasEvents.filter((e) => e.source_id === 'ACT-1');
    expect(acks).toHaveLength(0);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('renders later if the same action arrives once the object exists', () => {
    // Not marked seen when dropped: the object may simply not have been drawn
    // yet, and refusing it forever would lose the intervention entirely.
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    useNumeraStore.setState({ items: [] });
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements).toHaveLength(0);
    warn.mockRestore();

    useNumeraStore.setState({ items: [ITEM] });
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements.length).toBeGreaterThan(0);
  });
});

describe('the acknowledgement', () => {
  it('carries source_id = action_id and the resolved bounds', () => {
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    const ack = useNumeraStore.getState().canvasEvents.find((e) => e.source_id === 'ACT-1');
    expect(ack).toBeTruthy();
    expect(ack!.actor).toBe('TUTOR');
    expect(ack!.action_type).toBe('HIGHLIGHT');
    expect(ack!.active_state).toBe('ACTIVE');
    expect(ack!.bbox).toEqual({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  });

  it('files support rungs against SYSTEM_SUPPORT, not the tutor', () => {
    useNumeraStore.getState().applyTutorCanvasActions([
      action({ action_id: 'ACT-CUE', type: 'SHOW_CUE', target_kind: 'WRITE_AREA', target_object_id: null }),
    ]);
    const ack = useNumeraStore.getState().canvasEvents.find((e) => e.source_id === 'ACT-CUE');
    expect(ack!.actor).toBe('SYSTEM_SUPPORT');
  });
});

describe('Phase 3', () => {
  it('refuses tutor actions during an independent attempt', () => {
    // Same rule as applyCanvasDraw: refused on the way in, not hidden at the
    // render, so it cannot appear later when the phase changes.
    useNumeraStore.setState({ currentPhase: 'INDEPENDENT_PRACTICE' });
    useNumeraStore.getState().applyTutorCanvasActions([action()]);
    expect(useNumeraStore.getState().tutorElements).toHaveLength(0);
    expect(useNumeraStore.getState().canvasEvents.filter((e) => e.source_id === 'ACT-1')).toHaveLength(0);
  });
});

describe('student ink', () => {
  it('is never altered by a tutor action', () => {
    useNumeraStore.getState().applyTutorCanvasActions([
      action({ type: 'GROUP' }),
      action({ action_id: 'ACT-2', type: 'ARROW' }),
    ]);
    expect(useNumeraStore.getState().items).toEqual([ITEM]);
  });
});

describe('the write affordance', () => {
  it('is raised by a WRITE_AREA action but carries no answer', () => {
    const write = action({
      action_id: 'ACT-W', target_kind: 'WRITE_AREA', target_object_id: null,
      type: 'INSERT_MATH', text: 'n + 4',
    });
    useNumeraStore.getState().applyTutorCanvasActions([write]);
    expect(useNumeraStore.getState().writeAffordance).toBe(true);
    // The rule with teeth: the answer must not appear in the place the student
    // is being asked to write it.
    expect(useNumeraStore.getState().tutorElements).toHaveLength(0);
  });
});

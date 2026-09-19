/**
 * #329 — the red correction ring beside the student's `n + 5`, not around it.
 *
 * OCR places the ring as a fraction of the snapshot it read; student ink is
 * fixed in stage pixels. Scaled by whatever size the stage is NOW, the ring
 * drifts off the ink by exactly the ratio between the two sizes. These pin that
 * an ink-anchored mark keeps the frame of the snapshot its request carried.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore, type DrawnItem } from '@/store/useNumeraStore';
import { tipFor } from '@/lib/tutorTip';

const state = () => useNumeraStore.getState();

beforeEach(() => {
  useNumeraStore.setState({
    canvasEvents: [],
    items: [],
    tutorElements: [],
    canvasSize: { width: 800, height: 400 },
    currentTurnId: 'TURN-1',
    activeQuestionId: 'Q-T01-001',
    currentPhase: 'GUIDED_PRACTICE',
  });
  state().clearTutorMarks();
});

const ring = { kind: 'ellipse' as const, x: 0.5, y: 0.5, w: 0.2, h: 0.1 };
const correction = (step: string) => ({ actionId: `canvas-correction-${step}`, elements: [ring] });

describe('marks placed around OCR ink', () => {
  it('keep the frame of the snapshot their request carried', () => {
    state().applyCanvasDraw(correction('step-1'), { width: 810, height: 540 });
    expect(state().tutorElements[0].frame).toEqual({ width: 810, height: 540 });
  });

  it('each keep their own frame when two replies land out of order', () => {
    // Captured at 810×540 then 900×700; the SECOND reply arrives first.
    state().applyCanvasDraw(correction('step-2'), { width: 900, height: 700 });
    state().applyCanvasDraw(correction('step-1'), { width: 810, height: 540 });
    const byAction = (step: string) =>
      state().canvasEvents.find((e) => e.source_id === `canvas-correction-${step}`)!.target_object_id;
    const frameOf = (step: string) => state().tutorElements.find((el) => el.id === byAction(step))!.frame;
    expect(frameOf('step-1')).toEqual({ width: 810, height: 540 });
    expect(frameOf('step-2')).toEqual({ width: 900, height: 700 });
  });

  it('render at the ink, not at the live stage size, after a resize', () => {
    // Captured at 810×540, now shown on a 880×790 stage: the ring's centre
    // must stay at the pixel the ink occupies.
    state().applyCanvasDraw(
      { actionId: 'canvas-correction-step-1', elements: [{ ...ring, w: 0, h: 0 }] },
      { width: 810, height: 540 },
    );
    expect(tipFor(state().tutorElements[0], 0, 880, 790)).toEqual({ x: 405, y: 270 });
  });

  it('leave layout marks on the live stage', () => {
    state().applyCanvasDraw({ actionId: 'TURN-1:confirmed-tutor-work', elements: [ring] }, { width: 810, height: 540 });
    expect(state().tutorElements[0].frame).toBeUndefined();
  });

  it('fall back to the live stage when the request carried no snapshot', () => {
    state().applyCanvasDraw(correction('step-1'));
    expect(state().tutorElements[0].frame).toBeUndefined();
  });
});

describe('semantic marks on a student object', () => {
  it('carry the canvas size their box was measured against', () => {
    const item: DrawnItem = {
      id: 'S1', kind: 'stroke', tool: 'pen', points: [80, 40, 240, 120], color: '#000', size: 3,
    };
    useNumeraStore.setState({ items: [item] });
    state().applyTutorCanvasActions([{
      action_id: 'TURN-1:1:GROUP:S1',
      type: 'GROUP',
      target_kind: 'CANVAS_OBJECT',
      target_object_id: 'S1',
      confirmed_component_id: null,
      text: null,
      source_id: null,
      answer_reveal_allowed: false,
    }]);
    const mark = state().tutorElements.find((el) => el.id.endsWith(':grp'));
    expect(mark?.frame).toEqual({ width: 800, height: 400 });
  });
});

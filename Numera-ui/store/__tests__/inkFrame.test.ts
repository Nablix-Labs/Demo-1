/**
 * #329 — the red correction ring beside the student's `n + 5`, not around it.
 *
 * OCR places the ring as a fraction of the snapshot it read; student ink is
 * fixed in stage pixels. Scaled by whatever size the stage is NOW, the ring
 * drifts off the ink by exactly the ratio between the two sizes. These pin that
 * an ink-anchored mark keeps the frame it was measured in.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useNumeraStore, type DrawnItem } from '@/store/useNumeraStore';
import { recordCaptureFrame } from '@/lib/studentSnapshot';
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

describe('marks placed around OCR ink', () => {
  it('keep the frame of the snapshot OCR read', () => {
    recordCaptureFrame({ width: 810, height: 540 });
    state().applyCanvasDraw({ actionId: 'canvas-correction-step-1', elements: [ring] });
    expect(state().tutorElements[0].frame).toEqual({ width: 810, height: 540 });
  });

  it('render at the ink, not at the live stage size', () => {
    // Captured at 810×540, now shown on a 880×790 stage: the ring's centre
    // must stay at the pixel the ink occupies.
    recordCaptureFrame({ width: 810, height: 540 });
    state().applyCanvasDraw({ actionId: 'canvas-correction-step-1', elements: [{ ...ring, w: 0, h: 0 }] });
    const el = state().tutorElements[0];
    expect(tipFor(el, 0, 880, 790)).toEqual({ x: 405, y: 270 });
  });

  it('leave layout marks on the live stage', () => {
    recordCaptureFrame({ width: 810, height: 540 });
    state().applyCanvasDraw({ actionId: 'TURN-1:write-request', elements: [ring] });
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

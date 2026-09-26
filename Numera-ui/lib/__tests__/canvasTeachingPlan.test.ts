/**
 * What a canvas teaching beat turns into, and what it is refused
 * (docs/FRONTEND_CANVAS_TEACHING_HANDOFF.md).
 */

import { describe, expect, it } from 'vitest';
import {
  beatEffects, beatStart, nextTrailRow, operationPermitted, planMatchesResponse, planStillVisible,
  type CanvasTeachingBeat, type CanvasTeachingMode, type CanvasTeachingOperation, type CanvasTeachingPlan,
  type TeachingContext,
} from '@/lib/canvasTeachingPlan';
import { overlapsWriteArea, RESCUE_SUFFIX } from '@/lib/tutorCanvasActions';
import type { QuestionAnchor } from '@/lib/questionAnchors';
import type { TutorElement } from '@/store/useNumeraStore';

const op = (over: Partial<CanvasTeachingOperation> = {}): CanvasTeachingOperation => ({
  operation_id: 'op-1',
  kind: 'CIRCLE',
  target_kind: 'QUESTION_ANCHOR',
  target_ids: ['Q1:QTOKEN:1'],
  zone: 'QUESTION',
  persistence: 'PERSIST',
  evidence_ref: null,
  text: null,
  latex: null,
  color_role: 'AMBER',
  ...over,
});

const beat = (operations: CanvasTeachingOperation[], over: Partial<CanvasTeachingBeat> = {}): CanvasTeachingBeat => ({
  beat_id: 'b1',
  sequence: 1,
  speech_anchor: { start_char: 0, end_char: 19, text: 'Those first numbers' },
  operations,
  ...over,
});

const plan = (mode: CanvasTeachingMode = 'GUIDED', beats = [beat([op()])]): CanvasTeachingPlan => ({
  plan_id: 'Q1:TURN-1:canvas-teaching',
  question_id: 'Q1',
  source_turn_id: 'TURN-1',
  tutor_turn_id: 'TUTOR-1',
  scene_revision: 3,
  mode: 'append',
  teaching_mode: mode,
  beats,
});

const anchor = (token_id: string, over: Partial<QuestionAnchor> = {}): QuestionAnchor => ({
  token_id, text: 'n', char_start: 0, char_end: 1, ...over,
});

const ctx = (over: Partial<TeachingContext> = {}): TeachingContext => ({
  anchors: [anchor('Q1:QTOKEN:1'), anchor('Q1:QTOKEN:2', { char_start: 4, char_end: 5 })],
  items: [],
  tutorElements: [],
  canvasSize: { width: 1000, height: 600 },
  stripBottomPx: null,
  ...over,
});

const write = (over: Partial<CanvasTeachingOperation> = {}) => op({
  kind: 'WRITE_MATH', target_kind: 'CANVAS_ZONE', target_ids: ['ZONE:REASONING'], zone: 'REASONING',
  latex: '9 + 5 = 14', evidence_ref: 'DIRECT_EXPLANATION', ...over,
});

describe('which plan applies (rule 1)', () => {
  it('matches the response it arrived on', () => {
    expect(planMatchesResponse(plan(), { interaction_state_version: 3, accepted_turn_id: 'TURN-1' })).toBe(true);
  });

  it('refuses a plan for another revision or another turn', () => {
    expect(planMatchesResponse(plan(), { interaction_state_version: 4 })).toBe(false);
    expect(planMatchesResponse(plan(), { accepted_turn_id: 'TURN-2' })).toBe(false);
  });

  it('does not treat a field the response did not send as a mismatch', () => {
    expect(planMatchesResponse(plan(), {})).toBe(true);
  });

  it('never draws a parallel example', () => {
    expect(planMatchesResponse(plan('PARALLEL_EXAMPLE'), {})).toBe(false);
  });

  it('is only visible on its own question in Guided Practice', () => {
    const scene = { phase: 'GUIDED_PRACTICE', questionId: 'Q1', version: 3 };
    expect(planStillVisible(plan(), scene)).toBe(true);
    expect(planStillVisible(plan(), { ...scene, questionId: 'Q2' })).toBe(false);
    expect(planStillVisible(plan(), { ...scene, phase: 'INDEPENDENT_PRACTICE' })).toBe(false);
    expect(planStillVisible(plan(), { ...scene, version: 4 })).toBe(false);
  });
});

describe('beat timing', () => {
  it('starts at its phrase, as a fraction of the narration', () => {
    const b = beat([op()], { speech_anchor: { start_char: 50, end_char: 60, text: 'x' } });
    expect(beatStart(b, 100)).toBe(0.5);
    expect(beatStart(b, 0)).toBe(0);
  });
});

describe('mode rules', () => {
  it('keeps hint, visual cue and scaffold to attention marks', () => {
    for (const mode of ['HINT', 'VISUAL_CUE', 'SCAFFOLD'] as const) {
      expect(operationPermitted(op({ kind: 'CIRCLE' }), mode)).toBe(true);
      expect(operationPermitted(op({ kind: 'HIGHLIGHT' }), mode)).toBe(true);
      expect(operationPermitted(write(), mode)).toBe(false);
      expect(operationPermitted(op({ kind: 'CHECK' }), mode)).toBe(false);
    }
  });

  it('lets a direct explanation write only in the reasoning zone', () => {
    expect(operationPermitted(write(), 'DIRECT_EXPLANATION')).toBe(true);
    expect(operationPermitted(write({ zone: 'TUTOR_SOLUTION', target_ids: ['ZONE:TUTOR_SOLUTION'] }), 'DIRECT_EXPLANATION')).toBe(false);
  });

  it('never writes into the question', () => {
    expect(operationPermitted(write({ zone: 'QUESTION', target_ids: ['ZONE:QUESTION'] }), 'TUTOR_SOLVED')).toBe(false);
    expect(operationPermitted(write({ target_kind: 'QUESTION_ANCHOR', target_ids: ['Q1:QTOKEN:1'] }), 'TUTOR_SOLVED')).toBe(false);
  });

  it('lets a tutor-solved step write its line', () => {
    expect(operationPermitted(write({ zone: 'TUTOR_SOLUTION', target_ids: ['ZONE:TUTOR_SOLUTION'] }), 'TUTOR_SOLVED')).toBe(true);
  });
});

describe('question-anchor marks', () => {
  it('circles a rendered token', () => {
    const fx = beatEffects(plan(), beat([op()]), ctx());
    expect(fx.tokenMarks).toEqual([expect.objectContaining({ tokenId: 'Q1:QTOKEN:1', style: 'circle', color: 'AMBER', pulse: false })]);
    expect(fx.elements).toEqual([]);
  });

  it('drops an operation whose token is not on screen', () => {
    const fx = beatEffects(plan(), beat([op({ target_ids: ['Q1:QTOKEN:9'] })]), ctx());
    expect(fx.tokenMarks).toEqual([]);
  });

  it('drops the whole operation when one of its tokens is missing', () => {
    const fx = beatEffects(plan(), beat([op({ target_ids: ['Q1:QTOKEN:1', 'Q1:QTOKEN:9'] })]), ctx());
    expect(fx.tokenMarks).toEqual([]);
  });

  it('marks a PULSE as temporary, and FOCUS always is', () => {
    const fx = beatEffects(plan(), beat([
      op({ operation_id: 'a', kind: 'HIGHLIGHT', persistence: 'PULSE' }),
      op({ operation_id: 'b', kind: 'FOCUS', persistence: 'PERSIST', target_ids: ['Q1:QTOKEN:2'] }),
    ]), ctx());
    expect(fx.tokenMarks.every((m) => m.pulse)).toBe(true);
    expect(fx.pulseIds).toHaveLength(2);
  });

  it('connects tokens in order', () => {
    const fx = beatEffects(plan(), beat([op({ kind: 'CONNECT', target_ids: ['Q1:QTOKEN:1', 'Q1:QTOKEN:2'], color_role: 'TEAL' })]), ctx());
    expect(fx.connectors).toEqual([expect.objectContaining({ fromTokenId: 'Q1:QTOKEN:1', toTokenId: 'Q1:QTOKEN:2', color: 'TEAL' })]);
  });

  it('in a scaffold, points only at tokens the learner has confirmed', () => {
    const anchors = [anchor('Q1:QTOKEN:1', { confirmed: true }), anchor('Q1:QTOKEN:2', { char_start: 4, char_end: 5 })];
    const fx = beatEffects(plan('SCAFFOLD'), beat([
      op({ operation_id: 'a' }),
      op({ operation_id: 'b', target_ids: ['Q1:QTOKEN:2'] }),
    ]), ctx({ anchors }));
    expect(fx.tokenMarks.map((m) => m.tokenId)).toEqual(['Q1:QTOKEN:1']);
  });
});

describe('the reasoning trail', () => {
  it('writes clear of the student writing area', () => {
    const fx = beatEffects(plan('DIRECT_EXPLANATION'), beat([write()]), ctx());
    expect(fx.elements).toHaveLength(1);
    const el = fx.elements[0];
    expect(el).toMatchObject({ kind: 'math', tex: '9 + 5 = 14', color: '#FF9F1C' });
    expect(overlapsWriteArea({ x: el.x!, y: el.y!, w: 0.26, h: 0.06 })).toBe(false);
  });

  it('stacks lines downward within a beat and across beats', () => {
    const first = beatEffects(plan('DIRECT_EXPLANATION'), beat([
      write({ operation_id: 'a' }),
      write({ operation_id: 'b', latex: '14 + 5 = 19' }),
    ]), ctx());
    expect(first.elements[1].y!).toBeGreaterThan(first.elements[0].y!);
    const second = beatEffects(plan('DIRECT_EXPLANATION'), beat([write({ operation_id: 'c' })], { beat_id: 'b2' }),
      ctx({ tutorElements: first.elements }));
    expect(second.elements[0].y!).toBeGreaterThan(first.elements[1].y!);
  });

  it('goes below a rescue step already in the column', () => {
    const rescue: TutorElement = { id: `R1${RESCUE_SUFFIX}`, kind: 'text', x: 0.44, y: 0.3, text: 'Step 1' };
    expect(nextTrailRow([rescue])).toBeCloseTo(0.41);
  });

  it('ticks the latest line with CHECK', () => {
    const first = beatEffects(plan('TUTOR_SOLVED'), beat([write({ zone: 'TUTOR_SOLUTION', target_ids: ['ZONE:TUTOR_SOLUTION'] })]), ctx());
    const tick = beatEffects(plan('TUTOR_SOLVED'), beat([op({
      operation_id: 'chk', kind: 'CHECK', target_kind: 'CANVAS_ZONE', target_ids: ['ZONE:TUTOR_SOLUTION'], zone: 'TUTOR_SOLUTION',
    })], { beat_id: 'b2' }), ctx({ tutorElements: first.elements }));
    expect(tick.elements).toEqual([expect.objectContaining({ text: '✓', y: first.elements[0].y })]);
  });

  it('draws nothing for a hint that tries to write', () => {
    const fx = beatEffects(plan('HINT'), beat([write()]), ctx());
    expect(fx.elements).toEqual([]);
  });
});

describe('student tokens', () => {
  it('rings the student ink it names, in the frame it was measured in', () => {
    const items = [{ id: 'ink-1', kind: 'rect', x: 100, y: 300, w: 200, h: 60, color: '#000', size: 2 }] as TeachingContext['items'];
    const fx = beatEffects(plan(), beat([op({ target_kind: 'STUDENT_TOKEN', target_ids: ['ink-1'], zone: 'REASONING' })]), ctx({ items }));
    expect(fx.elements).toEqual([expect.objectContaining({ kind: 'ellipse', frame: { width: 1000, height: 600 } })]);
  });

  it('ignores ink that is not on the board', () => {
    const fx = beatEffects(plan(), beat([op({ target_kind: 'STUDENT_TOKEN', target_ids: ['gone'], zone: 'REASONING' })]), ctx());
    expect(fx.elements).toEqual([]);
  });
});

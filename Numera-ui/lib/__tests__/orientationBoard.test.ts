import { describe, expect, it } from 'vitest';
import { mergeWorkedExampleRuns } from '@/lib/orientationBoard';
import type { SchemaOrientationItem } from '@/lib/api';

const video: SchemaOrientationItem = {
  sequence_no: 1, content_type: 'ORIENTATION_VIDEO', worked_example: null,
  video: { video_id: 'VID-1', title: 'The Secret Language of Algebra', asset_url: null, duration_seconds: 78 },
};

function we(n: number, title: string, content: string): SchemaOrientationItem {
  return {
    sequence_no: n + 1, content_type: 'WORKED_EXAMPLE', video: null,
    worked_example: {
      worked_example_id: `WE-${n}`, title, final_answer: null, student_answer_required: false,
      steps: [{ step_id: 'S1', sequence_no: 1, screen_content: content, narration_text: `say ${n}` }],
    },
  };
}

describe('mergeWorkedExampleRuns', () => {
  // The live ALG-ORI-02 shape: one-step examples that share a title.
  const live = [
    video,
    we(1, 'Decoding Compact Algebraic Notation', '3y = 3 × y = y + y + y'),
    we(2, 'Decoding Compact Algebraic Notation', 'a × b → ab'),
    we(3, 'decoding compact algebraic notation ', '½x = ½ × x'),
  ];

  it('folds same-titled one-step examples into one board', () => {
    const out = mergeWorkedExampleRuns(live);
    expect(out.map((i) => i.content_type)).toEqual(['ORIENTATION_VIDEO', 'WORKED_EXAMPLE']);
    expect(out[1].worked_example!.steps.map((s) => s.screen_content)).toEqual([
      '3y = 3 × y = y + y + y', 'a × b → ab', '½x = ½ × x',
    ]);
  });

  it('remembers every original id so completion still reports all of them', () => {
    expect(mergeWorkedExampleRuns(live)[1].workedExampleIds).toEqual(['WE-1', 'WE-2', 'WE-3']);
  });

  it('gives merged steps unique ids and a continuous order', () => {
    const steps = mergeWorkedExampleRuns(live)[1].worked_example!.steps;
    expect(new Set(steps.map((s) => s.step_id)).size).toBe(3);
    expect(steps.map((s) => s.sequence_no)).toEqual([1, 2, 3]);
  });

  it('keeps examples with different titles apart', () => {
    const out = mergeWorkedExampleRuns([we(1, 'Notation', 'a'), we(2, 'Powers', 'b')]);
    expect(out).toHaveLength(2);
  });

  it('does not merge across a video', () => {
    const out = mergeWorkedExampleRuns([we(1, 'Same', 'a'), video, we(2, 'Same', 'b')]);
    expect(out.map((i) => i.content_type)).toEqual(['WORKED_EXAMPLE', 'ORIENTATION_VIDEO', 'WORKED_EXAMPLE']);
  });

  it('does not mutate the session record it was given', () => {
    const input = [we(1, 'Same', 'a'), we(2, 'Same', 'b')];
    mergeWorkedExampleRuns(input);
    expect(input[0].worked_example!.steps).toHaveLength(1);
    expect(input[0].worked_example!.steps[0].step_id).toBe('S1');
  });
});

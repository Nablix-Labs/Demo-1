import { describe, expect, it, vi } from 'vitest';
import { captureStudentLayers, TUTOR_LAYER_NAME } from '@/lib/studentSnapshot';

function fakeStage(onCapture?: () => void) {
  const events: string[] = [];
  const layer = {
    hide: () => events.push('hide'),
    show: () => events.push('show'),
  };
  const stage = {
    find: (selector: string) => {
      events.push(`find:${selector}`);
      return [layer];
    },
    toDataURL: () => {
      events.push('capture');
      onCapture?.();
      return 'data:image/png;base64,STUDENT';
    },
  };
  return { stage, events };
}

describe('capturing the student canvas', () => {
  it('hides the tutor layer before the capture and restores it after', () => {
    // The bug: toDataURL renders the whole stage, so the tutor's own labels
    // were photographed and OCR read them back as the student's answer.
    const { stage, events } = fakeStage();
    expect(captureStudentLayers(stage)).toBe('data:image/png;base64,STUDENT');
    expect(events).toEqual([`find:.${TUTOR_LAYER_NAME}`, 'hide', 'capture', 'show']);
  });

  it('restores the tutor layer even when the capture throws', () => {
    // Left hidden, a failed submission would silently wipe the tutor's marks
    // off the student's screen.
    const { stage, events } = fakeStage(() => { throw new Error('tainted canvas'); });
    expect(() => captureStudentLayers(stage)).toThrow('tainted canvas');
    expect(events.at(-1)).toBe('show');
  });

  it('captures at all when there is no tutor layer to hide', () => {
    const stage = {
      find: () => [],
      toDataURL: () => 'data:image/png;base64,PLAIN',
    };
    expect(captureStudentLayers(stage)).toBe('data:image/png;base64,PLAIN');
  });

  it('hides every tutor layer, not just the first', () => {
    const hidden: number[] = [];
    const stage = {
      find: () => [0, 1, 2].map((i) => ({ hide: () => hidden.push(i), show: () => {} })),
      toDataURL: () => 'x',
    };
    captureStudentLayers(stage);
    expect(hidden).toEqual([0, 1, 2]);
  });
});

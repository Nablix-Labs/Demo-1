/**
 * The tutor's notes survive a reload of the same question, and only that
 * question (live, 28 Sep 2026: `c/d = c ÷ d` vanished on refresh).
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { layerKey, layerOf, restoreLayer } from '@/lib/teachingLayerPersistence';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';

const NOTE: TutorElement = { id: 'ctp:scene:Q1:generic_confirmation:C4:note', kind: 'text', x: 0.44, y: 0.14, text: 'c/d = c ÷ d' };
const OTHER: TutorElement = { id: 'canvas-correction-1:ring', kind: 'ellipse', x: 0.2, y: 0.2, w: 0.1, h: 0.1 };

function save(sessionId: string, questionId: string) {
  const s = useNumeraStore.getState();
  window.sessionStorage.setItem(layerKey(sessionId, questionId)!, JSON.stringify(layerOf(s)));
}

beforeEach(() => {
  window.sessionStorage.clear();
  useNumeraStore.getState().reset();
  useNumeraStore.setState({
    sessionId: 'S1', activeQuestionId: 'Q1',
    tutorElements: [NOTE, OTHER],
    teachingMarks: [
      { id: 'm1', tokenId: 'T1', style: 'circle', color: 'AMBER', pulse: false },
      { id: 'm2', tokenId: 'T2', style: 'highlight', color: 'AMBER', pulse: true },
    ],
  });
});

describe('teaching layer persistence', () => {
  it('keeps only the plan\'s own, persistent marks', () => {
    const layer = layerOf(useNumeraStore.getState());
    expect(layer.elements.map((e) => e.id)).toEqual([NOTE.id]);
    expect(layer.marks.map((m) => m.id)).toEqual(['m1']);
  });

  it('restores the same question after a reload', () => {
    save('S1', 'Q1');
    useNumeraStore.setState({ tutorElements: [], teachingMarks: [] }); // the reload
    expect(restoreLayer()).toBe(true);
    expect(useNumeraStore.getState().tutorElements.map((e) => e.id)).toEqual([NOTE.id]);
    expect(useNumeraStore.getState().teachingMarks.map((m) => m.id)).toEqual(['m1']);
  });

  it('never puts one question\'s notes on another', () => {
    save('S1', 'Q1');
    useNumeraStore.setState({ tutorElements: [], teachingMarks: [], activeQuestionId: 'Q2' });
    expect(restoreLayer()).toBe(false);
    expect(useNumeraStore.getState().tutorElements).toEqual([]);
  });

  it('does not overwrite marks the live store already has', () => {
    save('S1', 'Q1');
    expect(restoreLayer()).toBe(false);
  });
});

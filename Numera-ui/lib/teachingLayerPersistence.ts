/**
 * Keep the canvas teaching plan's marks across a reload of the same question.
 *
 * A plan is delivered once, on the turn it belongs to, and the session record
 * does not carry it. So a refresh or reconnect mid-question reopened the
 * question with the tutor's notes gone: `c/d = c ÷ d`, written two turns
 * earlier, simply vanished (live, 28 Sep 2026). The tutor still refers to them.
 *
 * Stored per tab (sessionStorage) and per session + question, so nothing can
 * leak onto a different question: a question change clears the store, and the
 * next question reads its own (normally empty) key. Only persistent marks are
 * kept; a PULSE is over by the time anyone reloads.
 */

import { useEffect } from 'react';
import { TEACHING_ID_PREFIX, type TeachingConnector, type TeachingTokenMark } from '@/lib/canvasTeachingPlan';
import { useNumeraStore, type TutorElement } from '@/store/useNumeraStore';

interface SavedLayer {
  marks: TeachingTokenMark[];
  connectors: TeachingConnector[];
  elements: TutorElement[];
}

export function layerKey(sessionId: string | null, questionId: string | null): string | null {
  return sessionId && questionId ? `numera:teaching-layer:${sessionId}:${questionId}` : null;
}

function storage(): Storage | null {
  try { return typeof window === 'undefined' ? null : window.sessionStorage; } catch { return null; }
}

/** What of the current store is worth keeping. */
export function layerOf(s: {
  teachingMarks: TeachingTokenMark[];
  teachingConnectors: TeachingConnector[];
  tutorElements: TutorElement[];
}): SavedLayer {
  return {
    marks: s.teachingMarks.filter((m) => !m.pulse),
    connectors: s.teachingConnectors.filter((c) => !c.pulse),
    elements: s.tutorElements.filter((el) => el.id.startsWith(TEACHING_ID_PREFIX)),
  };
}

function isEmpty(layer: SavedLayer): boolean {
  return !layer.marks.length && !layer.connectors.length && !layer.elements.length;
}

export function readLayer(key: string): SavedLayer | null {
  try {
    const raw = storage()?.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SavedLayer>;
    const layer = {
      marks: Array.isArray(parsed.marks) ? parsed.marks : [],
      connectors: Array.isArray(parsed.connectors) ? parsed.connectors : [],
      elements: Array.isArray(parsed.elements) ? parsed.elements : [],
    };
    return isEmpty(layer) ? null : layer;
  } catch {
    return null;
  }
}

/**
 * Put a saved layer back if the store has none of its own for this question.
 * Returns whether anything was restored.
 */
export function restoreLayer(): boolean {
  const s = useNumeraStore.getState();
  const key = layerKey(s.sessionId, s.activeQuestionId);
  if (!key || !isEmpty(layerOf(s))) return false;
  const saved = readLayer(key);
  if (!saved) return false;
  const known = new Set(s.tutorElements.map((el) => el.id));
  useNumeraStore.setState({
    teachingMarks: saved.marks,
    teachingConnectors: saved.connectors,
    tutorElements: [...s.tutorElements, ...saved.elements.filter((el) => !known.has(el.id))],
  });
  return true;
}

/** Mount once, with the canvas. Saves on every change; restores on (re)open. */
export function useTeachingLayerPersistence(): void {
  useEffect(() => {
    restoreLayer();
    let lastKey = layerKey(useNumeraStore.getState().sessionId, useNumeraStore.getState().activeQuestionId);
    return useNumeraStore.subscribe((s, prev) => {
      const key = layerKey(s.sessionId, s.activeQuestionId);
      if (key !== lastKey) {
        lastKey = key;
        restoreLayer();
        return;
      }
      if (!key) return;
      if (s.teachingMarks === prev.teachingMarks
        && s.teachingConnectors === prev.teachingConnectors
        && s.tutorElements === prev.tutorElements) return;
      const layer = layerOf(s);
      try {
        // Only ever write a non-empty layer. The store is emptied on a question
        // change before the new question's id lands, and writing that empty
        // state would erase the saved notes of the question being left.
        if (!isEmpty(layer)) storage()?.setItem(key, JSON.stringify(layer));
      } catch { /* storage full or blocked: the marks just will not survive a reload */ }
    });
  }, []);
}

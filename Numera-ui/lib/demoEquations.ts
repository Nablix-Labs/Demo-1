/**
 * Demo equations — the set the tutor session can be (re)started with, so the
 * backend can be exercised against different questions straight from the UI.
 *
 * `conceptId` / `questionId` must match questions the backend actually serves;
 * the equation the student sees is whatever the backend returns for them (the
 * `label` is only the picker hint / the displayed question in mock mode).
 *
 * demo1 is the known-good pair (backend "demo1" → x + 4 = 9). The others follow
 * the same naming; confirm the ids against the backend, or use the picker's
 * Custom field to test any concept_id / question_id.
 */
import { DEMO_CONCEPT_ID, DEMO_QUESTION_ID } from './api';

export interface DemoEquation {
  id: string;
  label: string;
  conceptId: string;
  questionId: string;
}

export const DEMO_EQUATIONS: DemoEquation[] = [
  { id: 'demo1', label: 'x + 4 = 9', conceptId: DEMO_CONCEPT_ID, questionId: DEMO_QUESTION_ID },
  { id: 'demo2', label: 'x − 3 = 5', conceptId: DEMO_CONCEPT_ID, questionId: 'ALG_EQ_DIAG_002' },
  { id: 'demo3', label: 'x + 7 = 12', conceptId: DEMO_CONCEPT_ID, questionId: 'ALG_EQ_DIAG_003' },
];

export const DEFAULT_EQUATION = DEMO_EQUATIONS[0];

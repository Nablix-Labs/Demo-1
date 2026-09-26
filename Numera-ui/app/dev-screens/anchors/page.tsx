'use client';

/**
 * /dev-screens/anchors — question anchors across every layout.
 *
 * The layouts are the reason this screen exists. The offsets index
 * `current_question`, but a bare equation is rendered inside an added lead-in
 * and a comma-separated run of cases is split into a grid, so the string on
 * screen is fragments of the original rather than the original. Each case below
 * is one that resolves differently, including the two that must NOT highlight.
 */

import { useEffect } from 'react';
import Link from 'next/link';
import QuestionDisplay from '@/components/QuestionDisplay';
import TeachingConnectors from '@/components/TeachingConnectors';
import type { QuestionAnchor } from '@/lib/questionAnchors';
import type { TeachingConnector, TeachingTokenMark } from '@/lib/canvasTeachingPlan';
import { useNumeraStore } from '@/store/useNumeraStore';

const CASES: Array<{ title: string; note: string; question: string; anchors: QuestionAnchor[] }> = [
  {
    title: 'Prose — Chiru’s example',
    note: 'The variable, plus the fixed number.',
    question: 'Ravi scores n points and then scores 4 more. Write the new-score rule.',
    anchors: [
      { token_id: 'A', text: 'n', char_start: 12, char_end: 13, label: 'changes' },
      { token_id: 'B', text: '4', char_start: 37, char_end: 38, label: 'stays fixed' },
    ],
  },
  {
    title: 'Prose — where a search would be wrong',
    note: 'The first “n” is inside “Nina” and the first “4” is the wrong one of two.',
    question: 'Nina scores n points, then scores 4 more after 4 rounds.',
    anchors: [
      { token_id: 'C', text: 'n', char_start: 12, char_end: 13, label: 'changes' },
      { token_id: 'D', text: '4', char_start: 47, char_end: 48, label: 'stays fixed' },
    ],
  },
  {
    title: 'Cases — split into a grid',
    note: 'Anchors land in grid cells, and “+ 5” repeats three times.',
    question: '3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.',
    anchors: [
      { token_id: 'E', text: '3', char_start: 0, char_end: 1, label: 'changes' },
      { token_id: 'F', text: '5', char_start: 19, char_end: 20, label: 'stays fixed' },
      { token_id: 'G', text: 'n', char_start: 26, char_end: 27, label: null },
    ],
  },
  {
    title: 'Equation — lead-in is added text',
    note: '“Solve for x:” carries no anchors; the equation does.',
    question: 'x + 4 = 9',
    anchors: [{ token_id: 'H', text: '4', char_start: 4, char_end: 5, label: 'stays fixed' }],
  },
  {
    title: 'No anchors',
    note: 'The ordinary turn. Must render with no extra markup at all.',
    question: 'Write a rule for the pattern you can see.',
    anchors: [],
  },
  {
    title: 'Expression — the label lands inside the maths',
    note: 'Manjusha, 19 Sep 2026. An inline chip between "m" and "+ 7" breaks the expression apart.',
    question: 'In m + 7, identify the changing quantity and the operation.',
    anchors: [{ token_id: 'J', text: 'm', char_start: 3, char_end: 4, label: 'changes' }],
  },
  {
    title: 'Canvas teaching plan marks',
    note: 'Sanya, PR #364. Amber circle on the changing values, teal boxes on the fixed +5, an arrow from 9 down to n, navy check on n. Not labels — marks.',
    question: '3 + 5, 9 + 5, 14 + 5. Use n for the changing starting number.',
    anchors: [
      { token_id: 'T1', text: '3', char_start: 0, char_end: 1 },
      { token_id: 'T2', text: '9', char_start: 7, char_end: 8 },
      { token_id: 'T3', text: '5', char_start: 4, char_end: 5 },
      { token_id: 'T4', text: '5', char_start: 11, char_end: 12 },
      { token_id: 'T5', text: 'n', char_start: 26, char_end: 27 },
    ],
  },
  {
    title: 'A span that does not slice back',
    note: 'Contract breach — dropped, warned to console, question still renders.',
    question: 'Ravi scores n points and then scores 4 more.',
    anchors: [{ token_id: 'I', text: 'n', char_start: 4, char_end: 5, label: 'changes' }],
  },
];

/** What a plan's beats leave on the teaching-marks case above. */
const TEACHING_MARKS: TeachingTokenMark[] = [
  { id: 'm1', tokenId: 'T1', style: 'circle', color: 'AMBER', pulse: false },
  { id: 'm2', tokenId: 'T2', style: 'circle', color: 'AMBER', pulse: false },
  { id: 'm3', tokenId: 'T3', style: 'box', color: 'TEAL', pulse: false },
  { id: 'm4', tokenId: 'T4', style: 'box', color: 'TEAL', pulse: false },
  { id: 'm5', tokenId: 'T5', style: 'highlight', color: 'AMBER', pulse: false },
  { id: 'm6', tokenId: 'T5', style: 'check', color: 'NAVY', pulse: false },
];
const TEACHING_CONNECTORS: TeachingConnector[] = [
  { kind: 'token', id: 'c1', fromTokenId: 'T3', toTokenId: 'T4', color: 'TEAL', pulse: false },
  { kind: 'token', id: 'c2', fromTokenId: 'T2', toTokenId: 'T5', color: 'AMBER', pulse: false },
];

export default function AnchorsDevScreen() {
  useEffect(() => {
    useNumeraStore.setState({ teachingMarks: TEACHING_MARKS, teachingConnectors: TEACHING_CONNECTORS });
    return () => { useNumeraStore.setState({ teachingMarks: [], teachingConnectors: [] }); };
  }, []);

  return (
    <div className="min-h-screen w-full bg-white p-6">
      <Link href="/dev-screens" className="text-[12px] font-semibold text-slate-blue hover:text-ink">
        ← Dev screens
      </Link>
      <h1 className="text-[19px] font-semibold text-ink mt-3 mb-1">Question anchors</h1>
      <p className="text-[12.5px] text-slate-blue mb-6">
        Chirudeva handoff §1. Spans are sliced from the question, never searched for.
      </p>

      <div className="flex flex-col gap-3 max-w-[820px]">
        {CASES.map((c) => (
          <section key={c.title} className="rounded-lg border border-muted-gray bg-white overflow-hidden">
            <header className="px-5 py-2.5 border-b border-muted-gray bg-reading-surface">
              <div className="text-[10px] tracking-widest uppercase text-slate-blue">{c.title}</div>
              <div className="text-[11.5px] text-slate-blue mt-0.5">{c.note}</div>
            </header>
            <div className="px-5 py-4">
              <QuestionDisplay question={c.question} anchors={c.anchors} size="lesson" />
            </div>
          </section>
        ))}
      </div>
      <TeachingConnectors />
    </div>
  );
}

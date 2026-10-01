'use client';

/**
 * /dev-screens/canvas-plan — where the teaching plan's notes land on the canvas.
 *
 * The real canvas, with the plans the live backend sent for the counter
 * question, played beat by beat through the real store action. Each note should sit under the
 * question token its arrow starts from, right of the student's writing area,
 * with no arrow that starts from empty canvas (Sanya, 1 Oct 2026).
 */

import { useEffect } from 'react';
import Link from 'next/link';
import CanvasStage from '@/components/Canvas';
import type { CanvasTeachingOperation, CanvasTeachingPlan } from '@/lib/canvasTeachingPlan';
import type { QuestionAnchor } from '@/lib/questionAnchors';
import { useNumeraStore } from '@/store/useNumeraStore';

const QUESTION_ID = 'Q-T01-006';
const QUESTION = 'A counter starts at any value c and increases by 4. Write the general rule and state what changes and what stays fixed.';
const ANCHORS: QuestionAnchor[] = [
  { token_id: `${QUESTION_ID}:QTOKEN:7`, text: 'c', char_start: 30, char_end: 31 },
  { token_id: `${QUESTION_ID}:QTOKEN:11`, text: '4', char_start: 49, char_end: 50 },
];
const [C, FOUR] = ANCHORS.map((a) => a.token_id);

function connect(id: string, tokens: string[], slot: string, color: 'AMBER' | 'TEAL'): CanvasTeachingOperation {
  return {
    operation_id: id, kind: 'CONNECT', target_kind: 'QUESTION_ANCHOR', target_ids: tokens,
    zone: 'QUESTION', persistence: 'PERSIST', color_role: color, scene_slot: slot,
  };
}

function note(id: string, text: string, slot: string, kind: 'WRITE_TEXT' | 'WRITE_MATH' = 'WRITE_TEXT'): CanvasTeachingOperation {
  return {
    operation_id: id, kind, target_kind: 'CANVAS_ZONE', target_ids: ['ZONE:REASONING'],
    zone: 'REASONING', persistence: 'PERSIST', color_role: 'NAVY', scene_slot: slot,
    text: kind === 'WRITE_TEXT' ? text : null, latex: kind === 'WRITE_MATH' ? text : null,
  };
}

function mark(id: string, kind: 'CIRCLE' | 'HIGHLIGHT', tokens: string[], color: 'AMBER' | 'TEAL'): CanvasTeachingOperation {
  return {
    operation_id: id, kind, target_kind: 'QUESTION_ANCHOR', target_ids: tokens,
    zone: 'QUESTION', persistence: 'PERSIST', color_role: color,
  };
}

/**
 * The three plans the live backend sent on Q-T01-006, 1 Oct 2026, in order
 * (answers "c represents a changing number", "c+4", "+4 stays the same").
 */
const TURNS: CanvasTeachingOperation[][] = [
  [note('op-1', 'c: changing value', 'generic_confirmation:REQUIRED_COMPONENT_2')],
  [
    note('op-1', 'c+4', 'generic_confirmation:REQUIRED_COMPONENT_1', 'WRITE_MATH'),
    { ...connect('op-2', [C, FOUR], 'generic_confirmation:REQUIRED_COMPONENT_1', 'AMBER'), color_role: 'NAVY', zone: 'REASONING' },
  ],
  [
    { ...mark('op-1', 'HIGHLIGHT', [FOUR], 'TEAL'), color_role: undefined },
    note('op-2', '\\Delta=4', 'generic_confirmation:REQUIRED_COMPONENT_3', 'WRITE_MATH'),
  ],
];

function plan(turn: number): CanvasTeachingPlan {
  return {
    plan_id: `${QUESTION_ID}:TURN-${turn}`, question_id: QUESTION_ID, source_turn_id: `TURN-${turn}`,
    scene_revision: turn, mode: 'append', teaching_mode: 'GUIDED',
    beats: [{
      beat_id: 'b1', sequence: 1,
      speech_anchor: { start_char: 0, end_char: 1, text: 'Y' },
      operations: TURNS[turn],
    }],
  };
}

export default function CanvasPlanDevScreen() {
  useEffect(() => {
    const load = () => {
      useNumeraStore.setState({
        currentPhase: 'GUIDED_PRACTICE',
        activeQuestionId: QUESTION_ID,
        questionText: QUESTION,
        questionAnchors: ANCHORS,
      });
      useNumeraStore.getState().replaceTeachingLayer();
    };
    // After the persisted store rehydrates, or it overwrites the question.
    if (useNumeraStore.persist.hasHydrated()) load();
    return useNumeraStore.persist.onFinishHydration(load);
  }, []);

  const playTurn = (turn: number) => {
    const p = plan(turn);
    useNumeraStore.getState().applyTeachingBeat(p, p.beats[0]);
  };

  return (
    <div className="h-screen w-full flex flex-col bg-white">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-muted-gray text-[12px]">
        <Link href="/dev-screens" className="font-semibold text-slate-blue hover:text-ink">← Dev screens</Link>
        <span className="text-slate-blue">Canvas teaching plan — note placement</span>
        {TURNS.map((_, i) => (
          <button
            key={i}
            data-turn={i}
            onClick={() => playTurn(i)}
            className="rounded-full border border-muted-gray px-3 py-1 font-semibold text-ink hover:bg-reading-surface"
          >
            Turn {i + 1}
          </button>
        ))}
        <button
          onClick={() => useNumeraStore.getState().replaceTeachingLayer()}
          className="rounded-full border border-muted-gray px-3 py-1 text-slate-blue hover:bg-reading-surface"
        >
          Clear
        </button>
      </div>
      <div className="flex-1 flex min-h-0">
        <CanvasStage />
      </div>
    </div>
  );
}

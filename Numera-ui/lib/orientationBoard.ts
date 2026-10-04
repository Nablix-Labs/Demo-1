/**
 * One board for a worked example the content splits into many.
 *
 * ── What the live content looks like ───────────────────────────────────────
 *
 * ALG-ORI-02's "Decoding Compact Algebraic Notation" is authored as EIGHT
 * worked examples (WE-KS3-T02-01 … -08), each with the same title and a single
 * step. The delivery sequence serves them one after another, so the screen
 * played eight one-step examples: "Step 1 of 1" eight times, the board cleared
 * between each, and the student never saw more than one line of working
 * (live run, 4 Oct 2026). That is the opposite of Manjusha's ask — tutor
 * writing that builds up like the Phase 4 review board.
 *
 * The row-per-step sheet in lib/workedExampleSheet.ts already leaves earlier
 * steps up; it just never got more than one step to lay out. So consecutive
 * worked examples sharing a title are merged here into one example whose steps
 * are all of theirs, in order, and the existing sheet does the rest.
 *
 * Completion is unaffected: the merged item remembers every original id, and
 * /orientation/complete is sent all of them, exactly as if each had been
 * played on its own.
 */

import type { SchemaOrientationItem, SchemaWorkedExampleStep } from '@/lib/api';

export interface BoardOrientationItem extends SchemaOrientationItem {
  /** Every worked_example_id folded into this item (one entry when unmerged). */
  workedExampleIds: string[];
}

function sameBoard(a: string | undefined, b: string | undefined): boolean {
  const norm = (s: string | undefined) => (s ?? '').trim().toLowerCase();
  return norm(a) !== '' && norm(a) === norm(b);
}

export function mergeWorkedExampleRuns(items: SchemaOrientationItem[]): BoardOrientationItem[] {
  const out: BoardOrientationItem[] = [];
  for (const item of items) {
    const we = item.worked_example;
    const prev = out[out.length - 1];
    const prevWe = prev?.worked_example;
    if (
      item.content_type === 'WORKED_EXAMPLE' && we &&
      prev?.content_type === 'WORKED_EXAMPLE' && prevWe &&
      sameBoard(prevWe.title, we.title)
    ) {
      prevWe.steps = [...prevWe.steps, ...tagSteps(we.worked_example_id, we.steps, prevWe.steps.length)];
      // The hand-off answer, if any, is the last example's.
      prevWe.final_answer = we.final_answer ?? prevWe.final_answer;
      prevWe.student_answer_required = prevWe.student_answer_required || we.student_answer_required;
      prev.workedExampleIds.push(we.worked_example_id);
      continue;
    }
    out.push({
      ...item,
      worked_example: we
        ? { ...we, steps: tagSteps(we.worked_example_id, we.steps, 0) }
        : we,
      workedExampleIds: we ? [we.worked_example_id] : [],
    });
  }
  return out;
}

/**
 * Step ids are only unique inside their own example (every one-step example
 * calls its step S1), and the canvas uses `${exampleId}-${stepId}` as the
 * draw's idempotency key — so merged steps would collide and the second S1
 * would be dropped as a duplicate. Prefix each with the id it came from.
 */
function tagSteps(
  exampleId: string,
  steps: SchemaWorkedExampleStep[],
  offset: number,
): SchemaWorkedExampleStep[] {
  return [...(steps ?? [])]
    .sort((a, b) => a.sequence_no - b.sequence_no)
    .map((step, i) => ({ ...step, step_id: `${exampleId}:${step.step_id}`, sequence_no: offset + i + 1 }));
}

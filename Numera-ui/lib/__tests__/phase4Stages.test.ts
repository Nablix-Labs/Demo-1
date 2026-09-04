/**
 * The stage strip and the transport timeline.
 *
 * Both exist to say where the student is. The failure worth guarding is not a
 * crash — it is either of them confidently pointing at the wrong place: five
 * named stages over a replay that has three, or a clock that runs out while
 * the tutor is still talking.
 */

import { describe, it, expect } from 'vitest';
import { stagesFrom, totalDurationMs, elapsedMsAt, clock } from '@/lib/phase4Stages';
import { patternSentence } from '@/lib/phase4Review';
import type { Phase4Review } from '@/lib/api';

const labelled = [
  { stage_label: 'Spot the pattern' },
  { stage_label: 'Find the error' },
  { stage_label: 'Find the error' },
  { stage_label: 'Build the rule' },
];

describe('stages from steps', () => {
  it('collapses consecutive steps that share a label into one stage', () => {
    // A stage is a phase of the explanation, not a step: "Find the error"
    // spread over three steps is still one thing the student is doing.
    expect(stagesFrom(labelled, 0).map((s) => s.label))
      .toEqual(['Spot the pattern', 'Find the error', 'Build the rule']);
  });

  it('marks the stage the player is inside, and only that one', () => {
    const stages = stagesFrom(labelled, 2);   // second step of "Find the error"
    expect(stages.map((s) => s.current)).toEqual([false, true, false]);
  });

  it('ticks a stage only once the player is past its last step', () => {
    // At index 1 the student is on the FIRST step of "Find the error", so it is
    // not done — ticking it there would say they had finished something they
    // had just started.
    expect(stagesFrom(labelled, 1).map((s) => s.done)).toEqual([true, false, false]);
    expect(stagesFrom(labelled, 3).map((s) => s.done)).toEqual([true, true, false]);
  });

  it('falls back to numbered steps when the backend labelled nothing', () => {
    // The alternative — five hardcoded names — puts stages on screen the
    // student never reaches when a replay has three steps, and strands them on
    // the last name when it has seven.
    expect(stagesFrom([{}, {}, {}], 0).map((s) => s.label))
      .toEqual(['Step 1', 'Step 2', 'Step 3']);
  });

  it('drops an unlabelled step rather than folding it into the stage before it', () => {
    // Folding it in would silently lengthen that stage, so the tick would come
    // one step late.
    const stages = stagesFrom(
      [{ stage_label: 'Spot the pattern' }, { stage_label: null }, { stage_label: 'Build the rule' }],
      0,
    );
    expect(stages.map((s) => s.label)).toEqual(['Spot the pattern', 'Build the rule']);
  });

  it('starts a new stage when a label comes back after a different one', () => {
    const stages = stagesFrom(
      [{ stage_label: 'A' }, { stage_label: 'B' }, { stage_label: 'A' }],
      2,
    );
    // Three stages, not two — reopening the first would move the tick backwards.
    expect(stages).toHaveLength(3);
    expect(stages[0].done).toBe(true);
  });
});

describe('the transport timeline', () => {
  it('totals the steps when every one is timed', () => {
    expect(totalDurationMs([{ duration_ms: 1000 }, { duration_ms: 2000 }])).toBe(3000);
  });

  it('treats a PARTIALLY timed replay as untimed', () => {
    // Summing only the timed steps gives a total shorter than the replay, and a
    // bar that fills before the tutor stops talking is worse than no bar.
    expect(totalDurationMs([{ duration_ms: 1000 }, {}])).toBeNull();
    expect(totalDurationMs([{ duration_ms: 1000 }, { duration_ms: 0 }])).toBeNull();
  });

  it('is null for an untimed or empty replay', () => {
    expect(totalDurationMs([])).toBeNull();
    expect(totalDurationMs([{}, {}])).toBeNull();
  });

  it('measures elapsed time to the START of the current step', () => {
    const steps = [{ duration_ms: 1000 }, { duration_ms: 2000 }, { duration_ms: 500 }];
    expect(elapsedMsAt(steps, 0)).toBe(0);
    expect(elapsedMsAt(steps, 2)).toBe(3000);
  });

  it('floors the clock, so it never shows its end early', () => {
    expect(clock(0)).toBe('0:00');
    expect(clock(108_000)).toBe('1:48');
    expect(clock(271_999)).toBe('4:31');
  });
});

describe('the repeated-pattern sentence', () => {
  const review = (error_pattern: Phase4Review['error_pattern']): Phase4Review =>
    ({ error_pattern } as Phase4Review);

  it('counts the other questions', () => {
    expect(patternSentence(review({ signature: 'n × 4', occurrence_count: 2 })))
      .toBe('This “n × 4” error has appeared in 2 other questions.');
  });

  it('says "question" for one', () => {
    expect(patternSentence(review({ signature: 'n × 4', occurrence_count: 1 })))
      .toContain('1 other question.');
  });

  it('says nothing when the engine asserted no pattern', () => {
    // §7.6C — a single isolated occurrence must produce null rather than a
    // claim. Zero is the engine reporting no repeat, and printing "0 other
    // questions" would turn an absence into a finding.
    expect(patternSentence(review(null))).toBeNull();
    expect(patternSentence(review({ signature: '', occurrence_count: 3 }))).toBeNull();
    expect(patternSentence(review({ signature: 'n × 4', occurrence_count: 0 }))).toBeNull();
  });
});

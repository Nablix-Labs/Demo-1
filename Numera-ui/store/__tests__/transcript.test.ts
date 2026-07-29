/**
 * The live caption must never leave a stale bubble behind.
 *
 * Manjusha's recording (2026-07-29) showed every student turn appearing twice:
 * a grey "…transcribing" bubble that never went away, and the same words again
 * as a committed turn below it. The cause was that finalising only looked at
 * the LAST transcript entry, so a tutor reply arriving mid-sentence orphaned
 * the partial. These tests pin the invariant rather than that one sequence:
 * at most one partial exists, and it is always last.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const transcript = () => useNumeraStore.getState().transcript;
const partials = () => transcript().filter((m) => m.partial);

describe('partial transcript handling', () => {
  beforeEach(() => useNumeraStore.setState({ transcript: [] }));

  it('updates the live bubble in place instead of stacking them', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('what is');
    s.updatePartialTranscript('what is two');
    s.updatePartialTranscript('what is two x');
    expect(transcript()).toHaveLength(1);
    expect(transcript()[0].text).toBe('what is two x');
  });

  it('keeps the same bubble id while updating, so it does not remount', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('sub');
    const firstId = transcript()[0].id;
    s.updatePartialTranscript('subtract five');
    expect(transcript()[0].id).toBe(firstId);
  });

  it('finalises the live bubble rather than appending a duplicate', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('subtract five');
    s.commitPartialTranscript('Subtract five from both sides.');
    expect(transcript()).toHaveLength(1);
    expect(partials()).toHaveLength(0);
    expect(transcript()[0].text).toBe('Subtract five from both sides.');
  });

  it('finalises even when a tutor reply lands mid-sentence — the reported bug', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('the answer is four');
    // Tutor replies before the student's speech is finalised, so the partial
    // is no longer the last entry. This is what used to orphan it.
    s.addTranscriptMessage({ role: 'ai', text: 'Go on.' });
    s.commitPartialTranscript('The answer is four.');

    expect(partials()).toHaveLength(0);
    expect(transcript().filter((m) => m.role === 'student')).toHaveLength(1);
    expect(transcript().map((m) => m.text)).toEqual(['Go on.', 'The answer is four.']);
  });

  it('never accumulates partials across several interrupted turns', () => {
    const s = useNumeraStore.getState();
    for (const turn of ['one', 'two', 'three']) {
      s.updatePartialTranscript(`${turn} partial`);
      s.addTranscriptMessage({ role: 'ai', text: `reply to ${turn}` });
      s.commitPartialTranscript(`${turn} final`);
    }
    expect(partials()).toHaveLength(0);
    expect(transcript().filter((m) => m.role === 'student')).toHaveLength(3);
  });
});

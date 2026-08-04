import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

/**
 * A student's final transcript replaces the partial bubble it has been growing.
 *
 * Manjusha, 4 Aug: "during guided practice chat ui displays both partial
 * (dotted box) and final (blue box) transcripts, wherein sometimes it's diff" —
 * with a screenshot showing "How to put this" sitting above "How to do this
 * question?".
 *
 * Both halves of that matter. The duplicate is the visible bug; the two bubbles
 * DISAGREEING is why it is confusing rather than merely untidy — Deepgram
 * revises its guess as more audio arrives, so the abandoned partial is often an
 * earlier, wrong reading of the same sentence.
 */
beforeEach(() => {
  useNumeraStore.setState({ transcript: [] });
});

const texts = () => useNumeraStore.getState().transcript.map((m) => m.text);
const partials = () => useNumeraStore.getState().transcript.filter((m) => m.partial);

describe('partial → final leaves exactly one bubble', () => {
  it('replaces the partial rather than appending beside it', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('How to put this');
    s.commitPartialTranscript('How to do this question?');

    expect(texts()).toEqual(['How to do this question?']);
    expect(partials()).toHaveLength(0);
  });

  it('keeps growing one bubble while the student is still speaking', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('How');
    s.updatePartialTranscript('How to');
    s.updatePartialTranscript('How to do this');

    expect(texts()).toEqual(['How to do this']);
    expect(partials()).toHaveLength(1);
  });

  it('keeps the bubble in place when the final revises the wording', () => {
    // Same bubble id and timestamp, so it settles rather than jumping to the
    // bottom of the transcript.
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('How to put this');
    const before = useNumeraStore.getState().transcript[0];
    s.commitPartialTranscript('How to do this question?');
    const after = useNumeraStore.getState().transcript[0];

    expect(after.id).toBe(before.id);
    expect(after.timestamp).toBe(before.timestamp);
    expect(after.partial).toBeFalsy();
  });

  it('does not disturb earlier messages', () => {
    const s = useNumeraStore.getState();
    s.addTranscriptMessage({ role: 'ai', text: 'Resuming Guided Learning at Q-T01-001.' });
    s.updatePartialTranscript('How to put this');
    s.commitPartialTranscript('How to do this question?');

    expect(texts()).toEqual([
      'Resuming Guided Learning at Q-T01-001.',
      'How to do this question?',
    ]);
  });

  it('still records the turn when no partial ever arrived', () => {
    // Short utterances can finalise with no interim result at all.
    useNumeraStore.getState().commitPartialTranscript('Addition.');
    expect(texts()).toEqual(['Addition.']);
    expect(partials()).toHaveLength(0);
  });

  it('two consecutive turns leave two bubbles, not four', () => {
    const s = useNumeraStore.getState();
    s.updatePartialTranscript('n minus');
    s.commitPartialTranscript('n minus 5');
    s.updatePartialTranscript('n plus');
    s.commitPartialTranscript('n plus 5');

    expect(texts()).toEqual(['n minus 5', 'n plus 5']);
    expect(partials()).toHaveLength(0);
  });
});

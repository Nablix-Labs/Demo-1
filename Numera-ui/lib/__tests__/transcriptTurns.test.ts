/**
 * One spoken turn is one message.
 *
 * Streaming ASR emits a FINAL at every speech-final point — in practice, every
 * breath. Committing each as its own message turned a single spoken answer into
 * six bubbles: "Okay. I think the answer for this question is" / "option b." /
 * "Again, plus four." / "Because 12 plus four is" / … (Manjusha, 6 Aug).
 *
 * How many bubbles a turn becomes is a presentation decision, so it belongs
 * here rather than being blamed on the transcriber. The tutor replying is what
 * ends the turn, because that is the only honest signal that it is over.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useNumeraStore } from '@/store/useNumeraStore';

const reset = () => useNumeraStore.setState({ transcript: [] });
const t = () => useNumeraStore.getState().transcript;
const { getState } = useNumeraStore;

describe('one spoken turn is one message', () => {
  beforeEach(reset);

  it('joins the finals of a single answer into one bubble', () => {
    const { commitPartialTranscript } = getState();
    commitPartialTranscript('Okay. I think the answer for this question is');
    commitPartialTranscript('option b.');
    commitPartialTranscript('Again, plus four.');

    expect(t()).toHaveLength(1);
    expect(t()[0].role).toBe('student');
    expect(t()[0].text).toBe(
      'Okay. I think the answer for this question is option b. Again, plus four.',
    );
  });

  it('starts a new bubble once the tutor has replied', () => {
    const { commitPartialTranscript, addTranscriptMessage } = getState();
    commitPartialTranscript('option b.');
    addTranscriptMessage({ role: 'ai', text: 'Why that one?' });
    commitPartialTranscript('Because n can be any number.');

    expect(t().map((m) => m.role)).toEqual(['student', 'ai', 'student']);
    expect(t()[0].text).toBe('option b.');
    expect(t()[2].text).toBe('Because n can be any number.');
  });

  it('leaves no turn open once the tutor speaks', () => {
    const { commitPartialTranscript, addTranscriptMessage } = getState();
    commitPartialTranscript('first');
    addTranscriptMessage({ role: 'ai', text: 'reply' });
    expect(t().some((m) => m.open)).toBe(false);
  });

  it('does not swallow a segment when joining', () => {
    const { commitPartialTranscript } = getState();
    const parts = ['one', 'two', 'three', 'four'];
    parts.forEach(commitPartialTranscript);
    for (const p of parts) expect(t()[0].text).toContain(p);
  });

  it('does not run words together across segments', () => {
    const { commitPartialTranscript } = getState();
    commitPartialTranscript('twelve plus four is');
    commitPartialTranscript('not the general one.');
    expect(t()[0].text).toBe('twelve plus four is not the general one.');
    expect(t()[0].text).not.toMatch(/isnot/);
  });

  it('replaces the in-flight partial rather than leaving it behind', () => {
    const { updatePartialTranscript, commitPartialTranscript } = getState();
    updatePartialTranscript('How to put this');
    commitPartialTranscript('How to do this question?');
    expect(t()).toHaveLength(1);
    expect(t()[0].partial).toBeFalsy();
    expect(t()[0].text).toBe('How to do this question?');
  });
});

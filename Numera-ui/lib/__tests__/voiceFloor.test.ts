/**
 * Handing the microphone back after a submission that wasn't spoken.
 *
 * `submitVoiceTurn` has always driven the voice turn machine by hand:
 * PROCESSING while the request is out, SPEAKING while the reply is voiced, a
 * fresh LISTENING turn once the audio ends. None of the other five submissions
 * did. A typed answer, an option pick, "Check my work", Explain Again and
 * Explain-it-back all mint a submission turn and never touch `voiceStatus`
 * again.
 *
 * So the mic stayed OPEN across the request — app/page.tsx transmits on
 * `voiceStatus === 'listening'` — and afterwards `currentTurnId` was still the
 * submission turn the server had already resolved. The student's next
 * utterance was attributed to a closed turn and nothing came back: an open mic,
 * a moving level meter, and a tutor that never answers. That is Manjusha's
 * "when this input option in the canvas is pressed, voice is not listening"
 * (26 Aug), and the same shape as rows 5 and 36.
 *
 * penDownFloor.test.ts pins the sibling case — the pen silencing the tutor —
 * and its own header notes that "Check my work" could not recover from it
 * because submitCanvasWork never touched voiceStatus. It does now.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

vi.mock('@/lib/tts', () => ({
  speakTutor: vi.fn(),
  stopTutorSpeech: vi.fn(),
}));

const { useNumeraStore } = await import('@/store/useNumeraStore');
const {
  closeMicForSubmission, takeFloorForReply, reopenFloorAfterFailure,
} = await import('@/lib/tutorSpeech');

const status = () => useNumeraStore.getState().voiceStatus;
const turnId = () => useNumeraStore.getState().currentTurnId;

beforeEach(() => {
  useNumeraStore.setState({
    voiceStatus: 'idle',
    currentTurnId: null,
    expectsStudentResponse: true,
    allowVoiceInput: true,
  });
});

describe('closeMicForSubmission', () => {
  it('closes the mic while the request is out', () => {
    useNumeraStore.setState({ voiceStatus: 'listening' });
    closeMicForSubmission();
    expect(status()).toBe('processing');
  });

  it('leaves a session that has no voice alone', () => {
    closeMicForSubmission();
    expect(status()).toBe('idle');
  });
});

describe('takeFloorForReply', () => {
  it('speaks, then mints a fresh listening turn', () => {
    useNumeraStore.setState({ voiceStatus: 'processing' });
    const handBack = takeFloorForReply();
    expect(status()).toBe('speaking');
    handBack!();
    expect(status()).toBe('listening');
    // The socket subscribes to this id to re-send turn context; without a new
    // one the server evaluates the student against a turn it has closed.
    expect(turnId()).toBeTruthy();
  });

  it('parks in waiting when the reply expects no answer', () => {
    useNumeraStore.setState({ voiceStatus: 'processing', expectsStudentResponse: false });
    takeFloorForReply()!();
    expect(status()).toBe('waiting');
  });

  it('parks in waiting when the backend forbids voice for the next turn', () => {
    useNumeraStore.setState({ voiceStatus: 'processing', allowVoiceInput: false });
    takeFloorForReply()!();
    expect(status()).toBe('waiting');
  });

  it('does nothing once something else has taken the floor', () => {
    useNumeraStore.setState({ voiceStatus: 'processing' });
    const handBack = takeFloorForReply();
    useNumeraStore.setState({ voiceStatus: 'processing' }); // a newer submission
    handBack!();
    expect(status()).toBe('processing');
  });

  it('returns nothing at all when no voice session is running', () => {
    expect(takeFloorForReply()).toBeUndefined();
    expect(status()).toBe('idle');
  });
});

describe('reopenFloorAfterFailure', () => {
  it('gives the turn back when the submission failed', () => {
    useNumeraStore.setState({ voiceStatus: 'processing' });
    reopenFloorAfterFailure();
    expect(status()).toBe('listening');
  });

  it('only acts on the state closeMicForSubmission caused', () => {
    useNumeraStore.setState({ voiceStatus: 'speaking' });
    reopenFloorAfterFailure();
    expect(status()).toBe('speaking');
  });
});

/**
 * The rule, asserted against the source rather than against behaviour.
 *
 * Every one of these paths is a whole hook call away from a unit test, and the
 * failure they share is invisible in the UI — nothing throws, nothing looks
 * wrong, the student just stops being heard. Counting the calls is what stops a
 * sixth submission path being added without the handback, which is exactly how
 * the first five came to be missing it.
 */
describe('every submission hands the floor back', () => {
  const source = readFileSync(resolve(process.cwd(), 'hooks/useDemoTutor.ts'), 'utf8');
  const count = (needle: string) => source.split(needle).length - 1;

  it('closes the mic once per submission turn it mints', () => {
    const submissions = count('beginSubmissionTurn()');
    expect(submissions).toBeGreaterThan(0);
    // submitVoiceTurn is the one exemption: it drives the machine itself, and
    // its `currentTurnId ?? beginSubmissionTurn()` is a fallback for a turn the
    // listening state already opened, not a new submission.
    expect(count('closeMicForSubmission()')).toBe(submissions - 1);
  });

  it('reopens on every failure path that closed it', () => {
    expect(count('reopenFloorAfterFailure()')).toBe(count('closeMicForSubmission()'));
  });

  it('hands back after every reply it speaks', () => {
    expect(count('takeFloorForReply()')).toBe(count('closeMicForSubmission()'));
  });
});

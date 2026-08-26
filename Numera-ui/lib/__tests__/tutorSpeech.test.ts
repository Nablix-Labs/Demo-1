import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  tutorSay,
  setStudentWriting,
  isStudentWriting,
  resetTutorSpeech,
  MARK_SETTLE_MS,
} from '@/lib/tutorSpeech';

// tts pulls in stores and audio; the module under test only needs the two calls.
const stopTutorSpeech = vi.fn();
vi.mock('@/lib/tts', () => ({
  speakTutor: (t: string, onEnd?: () => void) => {
    spoken.push(t);
    onEnd?.(); // the real pipeline calls back when the audio finishes
  },
  stopTutorSpeech: () => stopTutorSpeech(),
}));

let spoken: string[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  spoken = [];
  stopTutorSpeech.mockClear();
  resetTutorSpeech();
});

afterEach(() => {
  resetTutorSpeech();
  vi.useRealTimers();
});

describe('silence while the student writes (§1)', () => {
  it('speaks normally when the student is not writing', () => {
    expect(tutorSay('Which part changes?')).toBe(true);
    expect(spoken).toEqual(['Which part changes?']);
  });

  it('drops the utterance while the student has the floor', () => {
    setStudentWriting(true);
    expect(tutorSay('Which part changes?')).toBe(false);
    expect(spoken).toEqual([]);
  });

  it('stops speech already in progress the moment writing starts', () => {
    tutorSay('Look across the three cases.');
    setStudentWriting(true);
    expect(stopTutorSpeech).toHaveBeenCalled();
  });

  it('does NOT replay the dropped line when writing stops', () => {
    setStudentWriting(true);
    tutorSay('Which part changes?');
    setStudentWriting(false);
    vi.advanceTimersByTime(10_000);
    // The spec says wait for the student to submit or ask — not resume talking.
    expect(spoken).toEqual([]);
  });

  it('reports who has the floor', () => {
    expect(isStudentWriting()).toBe(false);
    setStudentWriting(true);
    expect(isStudentWriting()).toBe(true);
    setStudentWriting(false);
    expect(isStudentWriting()).toBe(false);
  });

  it('only silences once for repeated writing signals', () => {
    setStudentWriting(true);
    setStudentWriting(true);
    expect(stopTutorSpeech).toHaveBeenCalledTimes(1);
  });
});

describe('highlight first, pause, then speak (§1)', () => {
  it('holds the words back until the mark has settled', () => {
    tutorSay('The n is right, and the 5 is right.', { afterMarks: true });
    expect(spoken).toEqual([]);

    vi.advanceTimersByTime(MARK_SETTLE_MS - 1);
    expect(spoken).toEqual([]);

    vi.advanceTimersByTime(1);
    expect(spoken).toEqual(['The n is right, and the 5 is right.']);
  });

  it('abandons the pending line if the student starts writing during the pause', () => {
    tutorSay('Let us check only the sign.', { afterMarks: true });
    setStudentWriting(true);
    vi.advanceTimersByTime(MARK_SETTLE_MS * 3);
    expect(spoken).toEqual([]);
  });

  it('a newer line supersedes one still waiting out its pause', () => {
    tutorSay('first', { afterMarks: true });
    tutorSay('second', { afterMarks: true });
    vi.advanceTimersByTime(MARK_SETTLE_MS);
    expect(spoken).toEqual(['second']);
  });

  it('speaks immediately when the turn drew nothing', () => {
    tutorSay('Addition.', { afterMarks: false });
    expect(spoken).toEqual(['Addition.']);
  });
});

// The voice turn machine reopens the mic from onEnd (half-duplex, voice
// contract §12). If a silenced utterance swallowed its callback the student
// would be unable to speak for the rest of the session — worse than the tutor
// talking over their pen. These are the tests that keep that from regressing.
describe('onEnd is never swallowed by silence', () => {
  it('fires immediately when the line is dropped for writing', () => {
    const onEnd = vi.fn();
    setStudentWriting(true);
    expect(tutorSay('anything', { onEnd })).toBe(false);
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(spoken).toEqual([]);
  });

  it('fires when a pending line is silenced mid-pause', () => {
    const onEnd = vi.fn();
    tutorSay('waiting on the mark', { afterMarks: true, onEnd });
    expect(onEnd).not.toHaveBeenCalled();

    setStudentWriting(true);
    expect(onEnd).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(MARK_SETTLE_MS * 2);
    expect(onEnd).toHaveBeenCalledTimes(1); // exactly once, not again on timeout
    expect(spoken).toEqual([]);
  });

  it('fires when the student starts writing during the pause and the timer then runs', () => {
    const onEnd = vi.fn();
    tutorSay('x', { afterMarks: true, onEnd });
    // Silencing already settles it; the timer must not double-fire.
    setStudentWriting(true);
    vi.runAllTimers();
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('fires on empty text rather than hanging the turn', () => {
    const onEnd = vi.fn();
    expect(tutorSay('', { onEnd })).toBe(false);
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('does NOT fire for a line superseded by a newer one', () => {
    // The newer line owns the turn; reopening the mic from the old callback
    // would race it. speakTutor's own supersede token behaves the same way.
    const stale = vi.fn();
    const fresh = vi.fn();
    tutorSay('stale', { afterMarks: true, onEnd: stale });
    tutorSay('fresh', { afterMarks: true, onEnd: fresh });
    vi.advanceTimersByTime(MARK_SETTLE_MS);
    expect(stale).not.toHaveBeenCalled();
    expect(fresh).toHaveBeenCalledTimes(1);
    expect(spoken).toEqual(['fresh']);
  });

  it('passes through normally when nothing interferes', () => {
    const onEnd = vi.fn();
    tutorSay('spoken aloud', { onEnd });
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(spoken).toEqual(['spoken aloud']);
  });
});

describe('guards', () => {
  it('ignores empty text', () => {
    expect(tutorSay('')).toBe(false);
    expect(spoken).toEqual([]);
  });

  it('reset drops a pending utterance', () => {
    tutorSay('pending', { afterMarks: true });
    resetTutorSpeech();
    vi.advanceTimersByTime(MARK_SETTLE_MS * 2);
    expect(spoken).toEqual([]);
  });
});

describe('speaking hands the floor back (Manjusha, 22 Aug 2026)', () => {
  it('a student who writes then talks does not mute the tutor forever', () => {
    // The report: wrote "n + 5", said "I fully written that in the Canvas",
    // and the tutor rendered text it never spoke for the rest of the question.
    //
    // Pen-down takes the floor, and before this the ONLY things that gave it
    // back were the Check button, Explain Again, and a fresh question — none of
    // which a student who answers by voice ever touches.
    setStudentWriting(true);
    expect(tutorSay('silenced while the pen is down')).toBe(false);

    // What useWebSocket now does on a student transcript_final.
    setStudentWriting(false);
    expect(tutorSay('and the tutor can answer again')).toBe(true);
  });
});

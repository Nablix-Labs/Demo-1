/**
 * Reading the Student Model Schema 3.0 payload off a session record.
 *
 * Fixtures are trimmed from real responses captured against the live backend on
 * 2026-07-28 (topic ALG-ORI-02, session SESSION002) — not invented shapes. The
 * two facts that drive the UI and are easy to regress:
 *   - a diagnostic set has MANY questions, while `current_question` has only the
 *     first, so anything reading the record directly shows one question of eight
 *   - the orientation video record arrives with `asset_url: null`
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  diagnosticQuestions,
  orientationSequence,
  requiredOrientationContent,
  completeOrientation,
  api,
  sessionTopicCode,
  type SessionRecord,
} from '@/lib/api';
import { orientationVideoForTopicCode } from '@/lib/demoContent';

const record = (phasePayload: unknown, topicId = 'ALG-ORI-02') =>
  ({
    current_question: 'What does 4y mean?',
    question_id: 'Q-T02-D01',
    student_model_event: { journey_state: { topic_id: topicId }, phase_payload: phasePayload },
  } as unknown as SessionRecord);

const DIAGNOSTIC = record({
  phase: 'PHASE_0_DIAGNOSTIC',
  payload_type: 'QUESTION_SET',
  orientation_bundle: null,
  question_set: {
    questions: [
      { question_id: 'Q-T02-D01', student_view: { question_text: 'What does 4y mean?', question_type: 'SINGLE_CHOICE', options: [{ option_id: 'A', text: '4 + y' }], requires_student_response: true } },
      { question_id: 'Q-T02-D02', student_view: { question_text: 'Which is compact for z + z + z + z?', question_type: 'SINGLE_CHOICE', options: [], requires_student_response: true } },
      // Backend has been seen to include a placeholder with no text.
      { question_id: 'Q-T02-D03', student_view: { question_text: '', question_type: 'SINGLE_CHOICE', options: [], requires_student_response: true } },
    ],
  },
});

const ORIENTATION = record({
  phase: 'PHASE_1_ORIENTATION',
  payload_type: 'ORIENTATION_BUNDLE',
  question_set: null,
  orientation_bundle: {
    target_micro_skill_ids: ['T02.M1'],
    // Deliberately out of order — the backend does not guarantee sorting.
    delivery_sequence: [
      { sequence_no: 2, content_type: 'WORKED_EXAMPLE', video: null, worked_example: { worked_example_id: 'WE-KS3-T02-01', title: 'Decoding Compact Algebraic Notation', final_answer: null, student_answer_required: false, steps: [] } },
      { sequence_no: 1, content_type: 'ORIENTATION_VIDEO', video: { video_id: 'VID-KS3-T02-ORI', title: 'The Secret Language of Algebra', asset_url: null, duration_seconds: 75 }, worked_example: null },
    ],
  },
});

describe('diagnosticQuestions', () => {
  it('returns the whole set, not just the record’s current question', () => {
    expect(diagnosticQuestions(DIAGNOSTIC).map((q) => q.question_id)).toEqual(['Q-T02-D01', 'Q-T02-D02']);
  });

  it('drops questions with no text rather than rendering a blank prompt', () => {
    expect(diagnosticQuestions(DIAGNOSTIC).some((q) => q.question_id === 'Q-T02-D03')).toBe(false);
  });

  it('is empty for an orientation payload and for no session', () => {
    expect(diagnosticQuestions(ORIENTATION)).toEqual([]);
    expect(diagnosticQuestions(null)).toEqual([]);
  });
});

describe('orientationSequence', () => {
  it('sorts by sequence_no so the video plays before the worked example', () => {
    expect(orientationSequence(ORIENTATION).map((i) => i.content_type)).toEqual([
      'ORIENTATION_VIDEO',
      'WORKED_EXAMPLE',
    ]);
  });

  it('keeps a video whose asset_url is null so the topic code can fill it', () => {
    const video = orientationSequence(ORIENTATION)[0];
    expect(video.video?.asset_url).toBeNull();
  });

  it('is empty for a diagnostic payload', () => {
    expect(orientationSequence(DIAGNOSTIC)).toEqual([]);
  });
});

describe('orientationVideoForTopicCode', () => {
  it('resolves the uploaded file the backend left null', () => {
    expect(orientationVideoForTopicCode(sessionTopicCode(ORIENTATION))).toBe(
      'https://nablixmathvideos.blob.core.windows.net/numeradev/ALG-ORI-02.mp4',
    );
  });

  it('handles the inconsistent codes in learning.topics', () => {
    // Subtopic 1 is ALG-KS3-01 and subtopic 4 is ALG-04, but both files are ALG-ORI-0N.
    expect(orientationVideoForTopicCode('ALG-KS3-01')).toMatch(/ALG-ORI-01\.mp4$/);
    expect(orientationVideoForTopicCode('ALG-04')).toMatch(/ALG-ORI-04\.mp4$/);
  });

  it('returns null when no file exists for that topic', () => {
    expect(orientationVideoForTopicCode('ALG-07')).toBeNull();
    expect(orientationVideoForTopicCode(null)).toBeNull();
  });
});

/**
 * Orientation completion contract (PR #44).
 *
 * /orientation/complete rejects anything that isn't exactly what was served:
 * missing ids are a 409, duplicate or unknown ids a 422. The frontend collects
 * ids as each piece of content finishes, so the required list has to be read
 * from the bundle correctly or the call fails at runtime with no local signal.
 */
describe('requiredOrientationContent', () => {
  it('lists the ids the bundle actually served', () => {
    expect(requiredOrientationContent(ORIENTATION)).toEqual({
      videoIds: ['VID-KS3-T02-ORI'],
      workedExampleIds: ['WE-KS3-T02-01'],
    });
  });

  it('is empty when there is no orientation bundle', () => {
    expect(requiredOrientationContent(DIAGNOSTIC)).toEqual({ videoIds: [], workedExampleIds: [] });
    expect(requiredOrientationContent(null)).toEqual({ videoIds: [], workedExampleIds: [] });
  });

  it('gates Continue until every served item is complete', () => {
    const { videoIds, workedExampleIds } = requiredOrientationContent(ORIENTATION);
    const complete = (v: string[], w: string[]) =>
      videoIds.every((id) => v.includes(id)) && workedExampleIds.every((id) => w.includes(id));

    expect(complete([], [])).toBe(false);                                  // nothing watched
    expect(complete(['VID-KS3-T02-ORI'], [])).toBe(false);                 // video only -> 409
    expect(complete([], ['WE-KS3-T02-01'])).toBe(false);                   // example only -> 409
    expect(complete(['VID-KS3-T02-ORI'], ['WE-KS3-T02-01'])).toBe(true);   // both -> allowed
  });
});

/**
 * completeOrientation must work against a backend on either side of PR #44.
 *
 * Frontend and backend deploy independently, so for a window the client sends
 * completed_video_ids to a backend whose OrientationPhaseRequest still sets
 * extra="forbid" and answers 422 "Extra inputs are not permitted". Without the
 * retry, nobody can finish orientation during that window.
 */
describe('completeOrientation across backend versions', () => {
  const url = '/session/SESSION001/orientation/complete';
  const forbid = {
    response: { status: 422, data: { message: 'Extra inputs are not permitted', field: 'completed_video_ids' } },
  };

  afterEach(() => { vi.restoreAllMocks(); });

  it('sends the ids to a backend that accepts them', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { session_id: 'SESSION001' } } as never);
    await completeOrientation('SESSION001', 'ST001', { videoIds: ['V1'], workedExampleIds: ['W1'] });
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][1]).toMatchObject({
      completed_video_ids: ['V1'],
      completed_worked_example_ids: ['W1'],
    });
  });

  it('retries without them against a pre-#44 backend', async () => {
    const post = vi.spyOn(api, 'post')
      .mockRejectedValueOnce(forbid)
      .mockResolvedValueOnce({ data: { session_id: 'SESSION001' } } as never);
    const rec = await completeOrientation('SESSION001', 'ST001', { videoIds: ['V1'], workedExampleIds: ['W1'] });
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1]).toEqual([url, { student_id: 'ST001' }]);
    expect(rec).toEqual({ session_id: 'SESSION001' });
  });

  it('does not swallow a real rejection', async () => {
    // A genuine 409 (missing required content) must still surface.
    vi.spyOn(api, 'post').mockRejectedValue({ response: { status: 409, data: { message: 'missing' } } });
    await expect(
      completeOrientation('SESSION001', 'ST001', { videoIds: [], workedExampleIds: [] }),
    ).rejects.toBeTruthy();
  });
});

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

import { describe, it, expect } from 'vitest';
import {
  diagnosticQuestions,
  orientationSequence,
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

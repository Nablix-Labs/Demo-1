/**
 * What the Review header calls this session's topic.
 *
 * Row 42: the header read "Linear equations · today" for every student, because
 * the screen used the mock worksheet's label even on a real session. A student
 * who had spent the lesson on "What Is Algebra?" was told they had done linear
 * equations.
 *
 * `journey_state.topic_id` is a CODE ('ALG-ORI-02') and is not showable. The
 * orientation video's title is the only human name the backend sends, so null
 * is a legitimate answer — and the caller must render the date alone rather
 * than fall back to content the student never saw.
 */

import { describe, it, expect } from 'vitest';
import { sessionTopicTitle, type SessionRecord } from '@/lib/api';

function record(videoTitles: (string | null)[] | null): SessionRecord {
  return {
    student_model_event: {
      phase_payload: videoTitles
        ? {
            phase: 'ORIENTATION',
            payload_type: 'ORIENTATION_BUNDLE',
            question_set: null,
            orientation_bundle: {
              target_micro_skill_ids: [],
              delivery_sequence: videoTitles.map((title, i) => ({
                sequence_no: i + 1,
                content_type: 'ORIENTATION_VIDEO' as const,
                video: title === null ? null : {
                  video_id: `V${i}`, title, asset_url: null, duration_seconds: null,
                },
                worked_example: null,
              })),
            },
          }
        : null,
      journey_state: { topic_id: 'ALG-ORI-02' },
    },
  } as unknown as SessionRecord;
}

describe('sessionTopicTitle', () => {
  it('names the topic from the orientation video', () => {
    expect(sessionTopicTitle(record(['What Is Algebra?']))).toBe('What Is Algebra?');
  });

  it('takes the first item that actually carries a title', () => {
    // A worked example comes through the same sequence with no video on it.
    expect(sessionTopicTitle(record([null, 'What Is Algebra?']))).toBe('What Is Algebra?');
  });

  it('admits it does not know rather than guessing', () => {
    // The review phase payload carries no orientation bundle at all — which is
    // exactly the state the Review screen reads it in.
    expect(sessionTopicTitle(record(null))).toBeNull();
    expect(sessionTopicTitle(null)).toBeNull();
    expect(sessionTopicTitle(undefined)).toBeNull();
  });

  it('treats a blank title as no title', () => {
    expect(sessionTopicTitle(record(['   ']))).toBeNull();
  });
});

/**
 * The Review payload now carries the name itself.
 *
 * Chiru added `topic_info` to Phase4ReviewResponse on 11 Sep 2026 (PR #271),
 * which closes the gap this file was written around: at REVIEW the phase
 * payload is REVIEW_SUMMARY with a null orientation_bundle, so the video title
 * is gone by exactly the screen that needs it and every live review was headed
 * "This topic". Verified on the VM the same day — topic_info.title comes back
 * "What Is Algebra?" for ST015.
 */
describe('sessionTopicTitle at Review', () => {
  const atReview = (title: unknown): SessionRecord => ({
    student_model_event: {
      phase_payload: {
        phase: 'REVIEW', payload_type: 'REVIEW_SUMMARY',
        question_set: { questions: [] }, orientation_bundle: null,
      },
      journey_state: { topic_id: 'ALG-KS3-01' },
    },
    phase4_review: { topic_info: { title } },
  } as unknown as SessionRecord);

  it('names the topic from the review payload once the bundle is gone', () => {
    expect(sessionTopicTitle(atReview('What Is Algebra?'))).toBe('What Is Algebra?');
  });

  it('still admits it does not know when the title is blank or absent', () => {
    // Never the topic CODE as a fallback: guessing a name from it is row 42.
    expect(sessionTopicTitle(atReview('  '))).toBeNull();
    expect(sessionTopicTitle(atReview(undefined))).toBeNull();
    expect(sessionTopicTitle(atReview(42))).toBeNull();
  });

  it('prefers the orientation video while one is still on the record', () => {
    // Mid-journey both can be present; the bundle is the older, phase-local
    // source and staying with it keeps the header stable across the transition.
    const rec = record(['What Is Algebra?']) as SessionRecord & { phase4_review?: unknown };
    rec.phase4_review = { topic_info: { title: 'Something Else' } };
    expect(sessionTopicTitle(rec)).toBe('What Is Algebra?');
  });
});

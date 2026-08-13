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

/**
 * The infinite review loop: `reportReviewFinished` threw away
 * `completeReview`'s response — including `next_topic_handoff` — and
 * `decideReview` then picked the next topic out of a hardcoded table. The
 * Student Model had already completed that topic, so it reopened it in REVIEW,
 * and the student came back to the same review forever.
 */
import { describe, expect, it } from 'vitest';
import { handoffDestination } from '@/lib/usePhaseRouting';
import { startPayloadFor } from '@/lib/sessionStart';

const handoff = (over: Record<string, string> = {}) => ({
  source_session_id: 'S1',
  student_model_request_id: 'REQ1',
  topic_id: 'ALG-KS3-01',
  entry_phase: 'PHASE_0_DIAGNOSTIC',
  ...over,
});

describe('routing from the handoff', () => {
  it('maps the Student Model phase through the existing map, not a new one', () => {
    expect(handoffDestination(handoff())).toEqual({
      topicId: 'ALG-KS3-01',
      href: '/diagnostic/ALG-KS3-01',
      unlock: 'topic-diagnostic',
    });
  });

  it('routes each journey phase to the screen that phase happens on', () => {
    expect(handoffDestination(handoff({ entry_phase: 'PHASE_1_ORIENTATION' }))!.href)
      .toBe('/orientation/ALG-KS3-01');
    expect(handoffDestination(handoff({ entry_phase: 'PHASE_2_GUIDED_LEARNING' }))!.href)
      .toBe('/');
    expect(handoffDestination(handoff({ entry_phase: 'PHASE_3_INDEPENDENT_PRACTICE' }))!.href)
      .toBe('/practice');
  });

  it('falls back to the diagnostic for a phase name it does not know', () => {
    // A new phase name must not strand the student on a blank route.
    expect(handoffDestination(handoff({ entry_phase: 'PHASE_9_SOMETHING' }))!.href)
      .toBe('/diagnostic/ALG-KS3-01');
  });

  it('is null without a handoff, so the caller keeps its own routing', () => {
    expect(handoffDestination(null)).toBeNull();
    expect(handoffDestination(handoff({ topic_id: '  ' }))).toBeNull();
  });
});

describe('starting the next topic', () => {
  it('sends the handoff topic as topic_code, never as concept_id', () => {
    // `topic_id` is a topic CODE. The backend resolves concept_id through a map
    // holding one entry, so sending it there is a 422 and the next topic never
    // starts.
    expect(startPayloadFor('ST1', 'ALG_LINEAR_ONE_STEP', 'ALG-KS3-01', 'TEXT')).toEqual({
      student_id: 'ST1',
      topic_code: 'ALG-KS3-01',
      interaction_mode: 'TEXT',
    });
  });

  it('falls back to concept_id when there is no topic code', () => {
    expect(startPayloadFor('ST1', 'ALG_LINEAR_ONE_STEP', null, 'TEXT')).toEqual({
      student_id: 'ST1',
      concept_id: 'ALG_LINEAR_ONE_STEP',
      interaction_mode: 'TEXT',
    });
  });

  it('never sends both — topic_code alone identifies the topic', () => {
    const payload = startPayloadFor('ST1', 'ALG_LINEAR_ONE_STEP', 'ALG-KS3-01', 'VOICE');
    expect('concept_id' in payload).toBe(false);
  });
});

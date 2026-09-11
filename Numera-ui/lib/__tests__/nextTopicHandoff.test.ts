/**
 * The infinite review loop: `reportReviewFinished` threw away
 * `completeReview`'s response — including `next_topic_handoff` — and
 * `decideReview` then picked the next topic out of a hardcoded table. The
 * Student Model had already completed that topic, so it reopened it in REVIEW,
 * and the student came back to the same review forever.
 */
import { describe, expect, it } from 'vitest';
import { handoffDestination, routeForPhase } from '@/lib/usePhaseRouting';
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

describe('the phase left behind when the handoff moves the student', () => {
  it('routes a phase it knows to that phase’s screen', () => {
    expect(routeForPhase('CONCEPT_ORIENTATION', 'ALG-ORI-02')).toBe('/orientation/ALG-ORI-02');
    expect(routeForPhase('REVIEW', 'ALG-ORI-02')).toBe('/review');
  });

  it('routes nowhere once the phase has been cleared', () => {
    // The third root cause of the blank topic transition (11 Sep 2026). The
    // handoff pushes the student to the next topic's orientation, but
    // `currentPhase` is still the finished session's REVIEW, so usePhaseRouting
    // reads it on the new page's first render and pushes them straight back to
    // /review.
    //
    // Clearing it is the honest value, not a placeholder: the old session is
    // over and the new one has not reported a phase yet. Chirudeva, 11 Sep:
    // "/session/start is authoritative. Stop routing off last_journey_state."
    // An empty phase routes nowhere, so the student stays where the handoff put
    // them until the session says otherwise.
    expect(routeForPhase('', 'ALG-ORI-02')).toBeNull();
  });

  it('routes nowhere for a phase name it does not know', () => {
    // Same protection as landingRoute's fallback, but here a wrong guess would
    // yank a student off a page they are already correctly on.
    expect(routeForPhase('PHASE_9_SOMETHING', 'ALG-ORI-02')).toBeNull();
  });
});

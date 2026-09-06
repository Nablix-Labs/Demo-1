/**
 * Built from the literal outputs in "Phase 3 Repeated Failure — Test Case
 * Changes & New Cases" (v3, 5 Sep 2026). Each case names the TC it came from,
 * so when the backend contract moves the failing test says which test case
 * changed rather than which assertion broke.
 *
 * Cases are written twice where it matters: once as the backend sends them
 * TODAY (payload_type only — `routing` is stripped by PublicStudentModelEvent)
 * and once as the spec describes them (routing present). Both must route the
 * same way, because that is the whole reason payload_type is consulted first.
 */
import { describe, it, expect } from 'vitest';
import {
  phase3Destination,
  resumesCheckpoint,
  interventionOptions,
  DEFAULT_INTERVENTION_OPTIONS,
  type Phase3RoutingSource,
} from '@/lib/phase3Routing';

/** A reply as it reaches the browser today: payload_type, no routing block. */
const asShipped = (payloadType: string, extra?: Record<string, unknown>): Phase3RoutingSource =>
  ({ student_model_event: { phase_payload: { payload_type: payloadType, ...extra } } });

describe('phase3Destination — as the backend sends it today (payload_type only)', () => {
  it('TC-18: FRESH_INDEPENDENT_QUESTION serves a question', () => {
    expect(phase3Destination(asShipped('FRESH_INDEPENDENT_QUESTION')).kind).toBe('SERVE_QUESTION');
  });

  it('TC-26/28/32: RESUME_SAME_INDEPENDENT_QUESTION resumes the checkpoint', () => {
    expect(phase3Destination(asShipped('RESUME_SAME_INDEPENDENT_QUESTION')).kind)
      .toBe('RESUME_CHECKPOINT');
  });

  it('TC-31: PREREQUISITE_REMEDIATION routes out to the prerequisite', () => {
    expect(phase3Destination(asShipped('PREREQUISITE_REMEDIATION')).kind).toBe('GO_TO_PREREQUISITE');
  });

  it('TC-33: INTERVENTION_INPUT_REQUIRED collects the difficulty input', () => {
    expect(phase3Destination(asShipped('INTERVENTION_INPUT_REQUIRED')).kind)
      .toBe('COLLECT_INTERVENTION');
  });

  it('TC-19: REVIEW_SUMMARY starts the review', () => {
    expect(phase3Destination(asShipped('REVIEW_SUMMARY')).kind).toBe('START_REVIEW');
  });
});

describe('phase3Destination — with the routing block (once it is forwarded)', () => {
  it('TC-20/27: RETURN_TO_GUIDED_LEARNING goes to repair, carrying the cycle', () => {
    const d = phase3Destination({
      student_model_event: { phase_payload: null },
      routing: { reason_code: 'FRESH_RETRY_FAILED', next_action: 'RETURN_TO_GUIDED_LEARNING' },
      phase_2_guided_learning: { repair_cycle_no: 1 },
    });
    expect(d).toEqual({ kind: 'GO_TO_GUIDED_REPAIR', cycle: 1 });
  });

  it('TC-27: the second repair cycle is reported as 2', () => {
    const d = phase3Destination({
      routing: { next_action: 'RETURN_TO_GUIDED_LEARNING' },
      phase_2_guided_learning: { repair_cycle_no: 2 },
    });
    expect(d).toEqual({ kind: 'GO_TO_GUIDED_REPAIR', cycle: 2 });
  });

  it('TC-31: the prerequisite route carries where to go and where to come back to', () => {
    const d = phase3Destination({
      student_model_event: { phase_payload: { payload_type: 'PREREQUISITE_REMEDIATION' } },
      routing: {
        reason_code: 'PREREQUISITE_REMEDIATION_REQUIRED',
        next_action: 'START_PREREQUISITE_ORIENTATION',
        next_topic_id: 'ALG-KS3-01',
        next_topic_entry_phase: 'PHASE_1_ORIENTATION',
        return_topic_id: 'ALG-KS3-03',
        return_question_id: 'Q-T03-024',
      },
    });
    expect(d).toEqual({
      kind: 'GO_TO_PREREQUISITE',
      topicId: 'ALG-KS3-01',
      entryPhase: 'PHASE_1_ORIENTATION',
      returnTopicId: 'ALG-KS3-03',
      returnQuestionId: 'Q-T03-024',
    });
  });

  it('TC-32: RETURN_TO_SAME_PHASE_3_QUESTION resumes the checkpoint', () => {
    expect(phase3Destination({
      routing: { next_action: 'RETURN_TO_SAME_PHASE_3_QUESTION', reason_code: 'PREREQUISITE_REMEDIATION_COMPLETED' },
    }).kind).toBe('RESUME_CHECKPOINT');
  });

  it('TC-36: AWAIT_INTERVENTION_REVIEW does NOT reopen the popup', () => {
    // The topic is still INTERVENTION_REQUIRED after the input is submitted
    // (spec §11: submitting does not clear the state). Reading the status alone
    // would show the popup again to a student who has just filled it in.
    const d = phase3Destination({
      routing: { next_action: 'AWAIT_INTERVENTION_REVIEW', reason_code: 'INTERVENTION_INPUT_COLLECTED' },
      status: { intervention_required: true, status_code: 'INTERVENTION_REQUIRED' },
    });
    expect(d.kind).toBe('AWAIT_INTERVENTION_REVIEW');
  });

  it('TC-34: intervention_required alone is enough to ask for the input', () => {
    // No prerequisite route found — the popup must still appear.
    expect(phase3Destination({
      status: { intervention_required: true, status_code: 'INTERVENTION_REQUIRED' },
      routing: { reason_code: 'NO_PREREQUISITE_ROUTE_AVAILABLE', next_action: 'COLLECT_INTERVENTION_INPUT' },
    }).kind).toBe('COLLECT_INTERVENTION');
  });

  it('TC-35: the earliest topic with no backward route is the same destination', () => {
    expect(phase3Destination({
      status: { intervention_required: true },
      routing: { reason_code: 'EARLIEST_TOPIC_NO_BACKWARD_ROUTE' },
    }).kind).toBe('COLLECT_INTERVENTION');
  });
});

describe('phase3Destination — degrading', () => {
  it('is UNKNOWN, not a throw, for null and empty replies', () => {
    expect(phase3Destination(null).kind).toBe('UNKNOWN');
    expect(phase3Destination(undefined).kind).toBe('UNKNOWN');
    expect(phase3Destination({}).kind).toBe('UNKNOWN');
    expect(phase3Destination({ student_model_event: { phase_payload: null } }).kind).toBe('UNKNOWN');
  });

  it('is UNKNOWN for a payload type or action nobody has taught it', () => {
    // A renamed enum must leave the screen alone, not send the student somewhere.
    expect(phase3Destination(asShipped('SOMETHING_CHIRU_ADDED_LATER')).kind).toBe('UNKNOWN');
    expect(phase3Destination({ routing: { next_action: 'NEW_ACTION' } }).kind).toBe('UNKNOWN');
  });

  it('reads values case- and whitespace-insensitively', () => {
    expect(phase3Destination(asShipped('  resume_same_independent_question ')).kind)
      .toBe('RESUME_CHECKPOINT');
  });

  it('leaves the prerequisite ids null when routing is stripped', () => {
    // Today's reality: payload_type arrives, routing does not. The destination
    // is still right; only the display detail is missing.
    expect(phase3Destination(asShipped('PREREQUISITE_REMEDIATION'))).toEqual({
      kind: 'GO_TO_PREREQUISITE',
      topicId: null,
      entryPhase: null,
      returnTopicId: null,
      returnQuestionId: null,
    });
  });
});

describe('resumesCheckpoint', () => {
  it('is true only for the checkpoint re-serve', () => {
    expect(resumesCheckpoint(asShipped('RESUME_SAME_INDEPENDENT_QUESTION'))).toBe(true);
    expect(resumesCheckpoint(asShipped('FRESH_INDEPENDENT_QUESTION'))).toBe(false);
    expect(resumesCheckpoint(null)).toBe(false);
  });
});

describe('interventionOptions', () => {
  it('uses the six selections from TC-33 when the backend sends them', () => {
    const opts = interventionOptions({
      selection_options: [
        { code: 'DONT_KNOW_HOW_TO_START', label: 'I do not know how to start.' },
        { code: 'OTHER', label: 'Something else.' },
      ],
    });
    expect(opts.map((o) => o.code)).toEqual(['DONT_KNOW_HOW_TO_START', 'OTHER']);
  });

  it('falls back to the spec §11 list when the field is missing or empty', () => {
    // TC-34's payload omits selection_options entirely. An empty popup cannot
    // satisfy selection_required, so the student could never submit.
    expect(interventionOptions(null)).toEqual(DEFAULT_INTERVENTION_OPTIONS);
    expect(interventionOptions({})).toEqual(DEFAULT_INTERVENTION_OPTIONS);
    expect(interventionOptions({ selection_options: [] })).toEqual(DEFAULT_INTERVENTION_OPTIONS);
  });

  it('drops malformed entries and falls back if none survive', () => {
    const junk = { selection_options: [{ code: '', label: 'x' }, { label: 'no code' }] as never };
    expect(interventionOptions(junk)).toEqual(DEFAULT_INTERVENTION_OPTIONS);
  });
});

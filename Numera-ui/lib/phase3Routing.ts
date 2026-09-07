/**
 * Phase 3 repeated-failure routing — reading the backend's destination.
 *
 * Spec: "Phase 3 Repeated Failure & Prerequisite Remediation", 5 Sep 2026, §12:
 *
 *     Manav — Frontend: Follow backend routing and display the destination.
 *     Do not independently calculate prerequisite or repair logic.
 *
 * So this module READS. It never counts repair cycles, never decides when
 * prerequisites are checked, never reduces a difficulty. Those are the Student
 * Model's (Chiru's) and the curriculum service's (Saravanan's), and duplicating
 * them here is the one thing §12 forbids outright.
 *
 * ── Why this exists at all ─────────────────────────────────────────────────
 *
 * Until this change the frontend could infer what to do next from the phase
 * plus "did a new question id arrive". The repair chain breaks that inference,
 * because its whole point is that the checkpoint question does NOT change:
 * Repair #1, Repair #2 and prerequisite remediation all return the student to
 * the SAME `question_id` and the SAME `question_usage_id` (spec §9, TC-26,
 * TC-28, TC-32).
 *
 * A reply carrying an id we have already seen is therefore ambiguous. It is
 * either a duplicate — which must change nothing — or a deliberate re-serve of
 * the checkpoint, which must hand the canvas back. `payload_type` is the only
 * thing that tells them apart, so it is what this reads.
 *
 * ── Where each signal actually lives ───────────────────────────────────────
 *
 * All three now arrive (Chirudeva, 7 Sep 2026), but not in one place, so this
 * reads both:
 *
 *   `payload_type`  on `student_model_event.phase_payload`. The only one that
 *                   ever survived the public projection, and still the one
 *                   consulted first.
 *   `routing`       published TWICE — on `student_model_event` as asked, and
 *                   again at the response root, because the root is where this
 *                   module was already reading it.
 *   `status`        on `student_model_event` ONLY. The root name is taken:
 *                   `SessionRecord.status` is "started" and
 *                   `InteractionResponse.status` is DUPLICATE_TURN and friends,
 *                   so overloading it would have broken every existing caller.
 *
 * Root wins where both carry `routing`, and they are the same object by
 * construction. Reading both is not belt-and-braces: `status` has exactly one
 * home, and a build that reads it at the root would silently never see it.
 *
 * Everything stays optional and an unrecognised value degrades to UNKNOWN — a
 * missing backend field has become a live outage here before, and the repair
 * chain adds fourteen new reason codes to drift.
 */

/** The destinations this module can recognise. */
export type Phase3Destination =
  /** A new independent question to work on. */
  | { kind: 'SERVE_QUESTION' }
  /**
   * The SAME checkpoint question again, after a repair or prerequisite
   * remediation. Same ids as before — this is what says so.
   */
  | { kind: 'RESUME_CHECKPOINT' }
  /** Back to Phase 2 for a guided repair. `cycle` is for display only. */
  | { kind: 'GO_TO_GUIDED_REPAIR'; cycle: number | null }
  /** Out to an earlier topic's orientation, then back to the checkpoint. */
  | {
      kind: 'GO_TO_PREREQUISITE';
      topicId: string | null;
      entryPhase: string | null;
      returnTopicId: string | null;
      returnQuestionId: string | null;
    }
  /** Automated remediation has stopped; ask the student what is hard. */
  | { kind: 'COLLECT_INTERVENTION'; request: InterventionInputRequest | null }
  /** Input collected, topic paused for a human. */
  | { kind: 'AWAIT_INTERVENTION_REVIEW' }
  /** Practice is finished. */
  | { kind: 'START_REVIEW' }
  /** Nothing recognisable — callers keep whatever they would have done. */
  | { kind: 'UNKNOWN' };

/** One predefined difficulty reason the student can tick in the popup. */
export interface InterventionSelectionOption {
  code: string;
  label: string;
}

/** The popup the backend asks us to show (spec §11, TC-33). */
export interface InterventionInputRequest {
  intervention_id?: string | null;
  prompt?: string | null;
  selection_required?: boolean | null;
  voice_input_enabled?: boolean | null;
  voice_input_required?: boolean | null;
  selection_options?: InterventionSelectionOption[] | null;
  /**
   * The case's own topic and micro-skill, if the backend names them.
   *
   * Not in the §11 shape as written, and read here because the submission is
   * validated against both (409 on a mismatch) and the frontend cannot derive
   * either one honestly. Absent, they are simply not sent.
   */
  topic_id?: string | null;
  micro_skill_id?: string | null;
}

/**
 * The fields this module reads, all optional.
 *
 * Typed structurally rather than against `InteractionResponse` so the same
 * parse works on an interaction reply, a canvas submission and a session
 * record — three shapes that carry the student model event in the same place
 * and have drifted from each other before.
 */
export interface Phase3Routing {
  next_action?: string | null;
  reason_code?: string | null;
  next_topic_id?: string | null;
  next_topic_entry_phase?: string | null;
  return_topic_id?: string | null;
  return_question_id?: string | null;
}

export interface Phase3Status {
  intervention_required?: boolean | null;
  status_code?: string | null;
}

export interface Phase3RoutingSource {
  student_model_event?: {
    phase_payload?: {
      payload_type?: string | null;
      intervention_input_request?: InterventionInputRequest | null;
    } | null;
    /** The event's own copy. Identical to the root one by construction. */
    routing?: Phase3Routing | null;
    /** `status` has no root form — this is its only home. */
    status?: Phase3Status | null;
  } | null;
  /** The root copy, which is where this module already read it. */
  routing?: Phase3Routing | null;
  /**
   * Never sent at the root today — `SessionRecord.status` and
   * `InteractionResponse.status` already own that name and mean something else
   * entirely. Kept on the type so that if a differently-named root block ever
   * lands, one line here is the whole change.
   */
  status?: Phase3Status | null;
  /** Repair cycle for display, where the backend surfaces it. */
  phase_2_guided_learning?: { repair_cycle_no?: number | null } | null;
}

function norm(v: string | null | undefined): string | null {
  const t = v?.trim().toUpperCase();
  return t ? t : null;
}

/**
 * The routing block, from whichever of its two homes carries it.
 *
 * Root first because that is where an interaction and a session reply publish
 * it; the event's copy is what a stored session record hands back. They agree
 * where both exist, so the order only decides which object is returned, never
 * which destination.
 */
export function phase3Routing(src: Phase3RoutingSource | null | undefined): Phase3Routing | null {
  return src?.routing ?? src?.student_model_event?.routing ?? null;
}

/** The status block. Published on the event only — see the header. */
export function phase3Status(src: Phase3RoutingSource | null | undefined): Phase3Status | null {
  return src?.student_model_event?.status ?? src?.status ?? null;
}

/**
 * Where the backend is sending the student.
 *
 * `payload_type` is consulted before `next_action` deliberately. It is the half
 * that survives the public projection, so a build that ships the payload types
 * before the routing block still routes correctly; and where both are present
 * they agree by construction (every TC pairs RESUME_SAME_INDEPENDENT_QUESTION
 * with RETURN_TO_SAME_PHASE_3_QUESTION, and so on).
 */
export function phase3Destination(src: Phase3RoutingSource | null | undefined): Phase3Destination {
  const payload = src?.student_model_event?.phase_payload ?? null;
  const routing = phase3Routing(src);
  const status = phase3Status(src);
  const payloadType = norm(payload?.payload_type);
  const nextAction = norm(routing?.next_action);

  // Intervention first: it is the only destination that is also a status, and
  // a student owed the popup must get it even if the payload type is one we
  // don't recognise. Missing the popup strands them with no visible reason.
  if (
    payloadType === 'INTERVENTION_INPUT_REQUIRED'
    || nextAction === 'COLLECT_INTERVENTION_INPUT'
    || (status?.intervention_required === true && nextAction !== 'AWAIT_INTERVENTION_REVIEW')
  ) {
    return { kind: 'COLLECT_INTERVENTION', request: payload?.intervention_input_request ?? null };
  }

  if (nextAction === 'AWAIT_INTERVENTION_REVIEW') return { kind: 'AWAIT_INTERVENTION_REVIEW' };

  if (payloadType === 'RESUME_SAME_INDEPENDENT_QUESTION'
    || nextAction === 'RETURN_TO_SAME_PHASE_3_QUESTION') {
    return { kind: 'RESUME_CHECKPOINT' };
  }

  if (payloadType === 'PREREQUISITE_REMEDIATION' || nextAction === 'START_PREREQUISITE_ORIENTATION') {
    return {
      kind: 'GO_TO_PREREQUISITE',
      topicId: routing?.next_topic_id?.trim() || null,
      entryPhase: norm(routing?.next_topic_entry_phase),
      returnTopicId: routing?.return_topic_id?.trim() || null,
      returnQuestionId: routing?.return_question_id?.trim() || null,
    };
  }

  if (nextAction === 'RETURN_TO_GUIDED_LEARNING') {
    return {
      kind: 'GO_TO_GUIDED_REPAIR',
      cycle: src?.phase_2_guided_learning?.repair_cycle_no ?? null,
    };
  }

  if (payloadType === 'REVIEW_SUMMARY' || nextAction === 'START_REVIEW') {
    return { kind: 'START_REVIEW' };
  }

  if (payloadType === 'FRESH_INDEPENDENT_QUESTION'
    || nextAction === 'DELIVER_REDUCED_DIFFICULTY_FRESH_RETRY') {
    return { kind: 'SERVE_QUESTION' };
  }

  return { kind: 'UNKNOWN' };
}

/**
 * Is the backend handing the checkpoint question back to be answered again?
 *
 * The narrow question `app/practice/page.tsx` needs, kept separate from the
 * full destination so the lock logic in `lib/phase3.ts` depends on one boolean
 * rather than on this whole union.
 */
export function resumesCheckpoint(src: Phase3RoutingSource | null | undefined): boolean {
  return phase3Destination(src).kind === 'RESUME_CHECKPOINT';
}

/**
 * The six reasons from spec §11, used when the backend sends none.
 *
 * The popup must never be empty: a student who cannot pick anything cannot
 * satisfy `selection_required`, and the submit button would never enable. The
 * codes match the spec's own payload example so a fallback submission is still
 * readable by whoever reviews the intervention.
 */
export const DEFAULT_INTERVENTION_OPTIONS: InterventionSelectionOption[] = [
  { code: 'DONT_UNDERSTAND_QUESTION', label: 'I do not understand what the question is asking.' },
  { code: 'DONT_KNOW_HOW_TO_START', label: 'I do not know how to start.' },
  { code: 'CANNOT_APPLY_IDEA', label: 'I understand the idea, but I cannot use it in this question.' },
  { code: 'WORDS_SYMBOLS_CONFUSING', label: 'The maths words or symbols are confusing.' },
  { code: 'WORKING_MISTAKES', label: 'I keep making calculation or working mistakes.' },
  { code: 'OTHER', label: 'Something else.' },
];

export const DEFAULT_INTERVENTION_PROMPT = 'What are you finding difficult?';

/** The options to render, falling back so the popup is never unusable. */
export function interventionOptions(
  request: InterventionInputRequest | null | undefined,
): InterventionSelectionOption[] {
  const given = request?.selection_options;
  if (!Array.isArray(given)) return DEFAULT_INTERVENTION_OPTIONS;
  const usable = given.filter(
    (o): o is InterventionSelectionOption =>
      Boolean(o && typeof o.code === 'string' && o.code.trim() && typeof o.label === 'string' && o.label.trim()),
  );
  return usable.length > 0 ? usable : DEFAULT_INTERVENTION_OPTIONS;
}

/**
 * The local inactivity controller.
 *
 * From the Guided Practice Phase 2 handoff (Manav — Frontend, "Local inactivity
 * controller"). One controller for canvas, text, voice, request lifecycle, page
 * visibility and connectivity — deliberately not a timer per input, because
 * independent timers are how you end up nudging a student who is mid-sentence
 * on one input while another input's clock happened to expire.
 *
 * ── What leaves this module ─────────────────────────────────────────────────
 * Activity stays local. No strokes, keystrokes, partial text, pointer paths or
 * microphone data is transmitted — the controller only ever reports "the
 * student has been idle since the tutor's turn", and the backend independently
 * validates that against its own clock. Client timing is telemetry, never
 * authority.
 *
 * ── Why the delivery states exist ───────────────────────────────────────────
 * A nudge is not a fire-and-forget message. Between deciding to send one and
 * the student actually hearing it there are several places the student can
 * start working again, and a nudge that arrives after they have resumed is
 * worse than no nudge at all — it interrupts exactly the state it exists to
 * end. So each nudge carries a state, and activity at any point moves it to
 * SUPPRESSED rather than racing the presentation.
 *
 *   PENDING                  claimed locally, request in flight
 *   SUPPRESSED               the student resumed; never show, never speak
 *   PRESENTED_UNACKNOWLEDGED shown/spoken, backend not yet told
 *   PRESENTED                backend acknowledged
 *
 * Retry applies ONLY to the acknowledgement, never to the presentation. Retrying
 * the presentation would show or speak the same nudge twice.
 */

export type NudgeState =
  | 'PENDING'
  | 'SUPPRESSED'
  | 'PRESENTED_UNACKNOWLEDGED'
  | 'PRESENTED';

/** Server-owned policy. No local defaults — an absent policy disables nudging. */
export interface InactivityPolicy {
  initialIdleThresholdMs: number;
  cooldownMs: number;
  maxNudgesPerTutorTurn: number;
}

/** Everything that counts as the student being busy, or us not being allowed to nudge. */
export interface ActivityGate {
  /** Drawing, typing, or speaking right now. */
  studentActive: boolean;
  /** A request is in flight — the tutor is already working. */
  requestInFlight: boolean;
  /** Tab hidden: they may be reading something else, and we cannot see activity. */
  pageHidden: boolean;
  /** Socket down or reconnecting. */
  disconnected: boolean;
  /** The backend is actually waiting on the student. */
  awaitingStudent: boolean;
}

export interface NudgeRecord {
  id: string;
  state: NudgeState;
  /** The tutor turn this nudge belongs to. */
  tutorTurnId: string | null;
}

const IDLE_GATE_KEYS = [
  'studentActive',
  'requestInFlight',
  'pageHidden',
  'disconnected',
] as const;

/**
 * May the idle clock run at all right now?
 *
 * Note `awaitingStudent`: a nudge is only meaningful when the backend is
 * actually waiting for the student. Nudging while the tutor still owes a reply
 * would blame the student for the tutor being slow.
 */
export function clockMayRun(gate: ActivityGate): boolean {
  if (!gate.awaitingStudent) return false;
  return IDLE_GATE_KEYS.every((k) => !gate[k]);
}

export interface IdleDecision {
  /** Ask the backend for a nudge. */
  claim: boolean;
  reason:
    | 'eligible'
    | 'blocked'
    | 'below_threshold'
    | 'in_cooldown'
    | 'max_reached'
    | 'no_policy';
}

/**
 * Should we claim a nudge right now?
 *
 * Pure so every branch is checkable without timers. `elapsedMs` is time since
 * the idle clock last restarted, `sinceLastNudgeMs` since the last one was
 * claimed for this tutor turn.
 */
export function shouldClaimNudge(args: {
  policy: InactivityPolicy | null;
  gate: ActivityGate;
  elapsedMs: number;
  sinceLastNudgeMs: number | null;
  nudgesThisTurn: number;
}): IdleDecision {
  const { policy, gate, elapsedMs, sinceLastNudgeMs, nudgesThisTurn } = args;

  // No local defaults: without server policy we do not invent one.
  if (!policy) return { claim: false, reason: 'no_policy' };
  if (!clockMayRun(gate)) return { claim: false, reason: 'blocked' };
  if (nudgesThisTurn >= policy.maxNudgesPerTutorTurn)
    return { claim: false, reason: 'max_reached' };
  if (elapsedMs < policy.initialIdleThresholdMs)
    return { claim: false, reason: 'below_threshold' };
  if (sinceLastNudgeMs !== null && sinceLastNudgeMs < policy.cooldownMs)
    return { claim: false, reason: 'in_cooldown' };

  return { claim: true, reason: 'eligible' };
}

/**
 * Apply student activity to a nudge already in flight.
 *
 * Activity before the claim lands prevents transmission; activity after it
 * marks the record suppressed. Once a nudge has actually been shown or spoken
 * it is too late — suppressing then would be pretending it never happened, and
 * the acknowledgement still has to reach the backend so its records match.
 */
export function onStudentActivity(record: NudgeRecord): NudgeRecord {
  if (record.state === 'PENDING') return { ...record, state: 'SUPPRESSED' };
  return record;
}

/** True when a nudge may be shown or spoken. Suppressed ones never are. */
export function mayPresent(record: NudgeRecord): boolean {
  return record.state === 'PENDING';
}

/**
 * Presentation has begun.
 *
 * Deliberately one-way: from here only the acknowledgement is retried, never
 * the visual or spoken presentation.
 */
export function markPresented(record: NudgeRecord): NudgeRecord {
  if (record.state !== 'PENDING') return record;
  return { ...record, state: 'PRESENTED_UNACKNOWLEDGED' };
}

/** The backend acknowledged the presentation. Terminal. */
export function markAcknowledged(record: NudgeRecord): NudgeRecord {
  if (record.state !== 'PRESENTED_UNACKNOWLEDGED') return record;
  return { ...record, state: 'PRESENTED' };
}

/**
 * Connection dropped.
 *
 * Anything still pending is suppressed rather than held. A nudge claimed before
 * a disconnect is about a silence that ended some unknown time ago, and
 * restoring it on reconnect would deliver a stale interruption — the handoff is
 * explicit that a new full interval starts instead.
 */
export function onDisconnect(records: NudgeRecord[]): NudgeRecord[] {
  return records.map((r) => (r.state === 'PENDING' ? { ...r, state: 'SUPPRESSED' } : r));
}

/**
 * Does this nudge belong in what the learner sees?
 *
 * PRESENTED only — acknowledged by the backend.
 *
 * PRESENTED_UNACKNOWLEDGED is deliberately excluded even though the words were
 * shown: the handoff is explicit that a generated nudge stays outside learner
 * history "until presentation acknowledgement". Until the backend has confirmed
 * it, the two sides disagree about whether the turn happened, and the frontend
 * must not be the one that decides. Suppressed, stale, failed and pending
 * nudges are delivery telemetry and never appear.
 */
export function inLearnerHistory(record: NudgeRecord): boolean {
  return record.state === 'PRESENTED';
}

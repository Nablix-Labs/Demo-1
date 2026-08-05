'use client';

/**
 * The inactivity controller, wired to the live lesson.
 *
 * lib/inactivity.ts holds the rules as pure functions; this is the one place
 * that feeds them real signals and acts on the answer. Deliberately a single
 * interval rather than a timer per input — independent timers are how you end
 * up nudging a student who is mid-sentence on one input because another input's
 * clock happened to expire.
 *
 * ── Dormant until the server says otherwise ────────────────────────────────
 * No policy, no nudging. The handoff calls for explicit validated configuration
 * with no model defaults, and the backend does not send it yet, so today this
 * runs, observes, and claims nothing. That is the correct behaviour rather than
 * a placeholder: inventing a threshold locally would mean the first student to
 * pause for thought gets interrupted on a number nobody agreed.
 *
 * ── What is transmitted ────────────────────────────────────────────────────
 * Nothing about the activity itself. No strokes, keystrokes, partial text,
 * pointer paths or microphone data leaves the browser. The client claims a
 * nudge; the backend independently validates the silence against its own clock,
 * and treats any client timing as telemetry.
 */

import { useEffect, useRef } from 'react';
import { useNumeraStore } from '@/store/useNumeraStore';
import { useMicLevel } from '@/store/useMicLevel';
import { isStudentWriting } from '@/lib/tutorSpeech';
import {
  shouldClaimNudge,
  onStudentActivity,
  markPresented,
  markAcknowledged,
  onDisconnect,
  mayPresent,
  type ActivityGate,
  type NudgeRecord,
} from '@/lib/inactivity';

/** How often the single controller re-evaluates. Not a threshold — just a tick. */
const TICK_MS = 1_000;

export interface InactivityNudgeOptions {
  /** True while any tutor request is in flight. */
  requestInFlight?: boolean;
  /** True while the socket is down or reconnecting. */
  disconnected?: boolean;
  /**
   * Claim a nudge from the backend. Returns the nudge id, or null if the
   * backend declined (its own clock disagreed, cooldown, rate limit).
   * Omitted until the endpoint exists — without it nothing is ever claimed.
   */
  claim?: () => Promise<string | null>;
  /** Show/speak the nudge. Called at most once per nudge, never retried. */
  present?: (id: string) => void;
  /** Tell the backend it was presented. Retried; the presentation is not. */
  acknowledge?: (id: string) => Promise<void>;
}

export function useInactivityNudge(options: InactivityNudgeOptions = {}): void {
  // Refs, not state: this loop must not re-render the lesson every second.
  const idleSinceRef = useRef<number | null>(null);
  const lastClaimAtRef = useRef<number | null>(null);
  const nudgesThisTurnRef = useRef(0);
  const recordsRef = useRef<NudgeRecord[]>([]);
  const claimingRef = useRef(false);
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => {
    const gateNow = (): ActivityGate => {
      const s = useNumeraStore.getState();
      const speaking = useMicLevel.getState().aiSpeaking;
      return {
        // Drawing, typing, or talking all count the same way.
        studentActive:
          isStudentWriting() ||
          s.textInput.trim().length > 0 ||
          (s.voiceStatus === 'listening' && !s.micMuted),
        requestInFlight:
          Boolean(optsRef.current.requestInFlight) ||
          s.voiceStatus === 'processing' ||
          s.voiceStatus === 'speaking' ||
          speaking,
        pageHidden: typeof document !== 'undefined' && document.visibilityState === 'hidden',
        disconnected: Boolean(optsRef.current.disconnected),
        // Only meaningful when the backend is actually waiting on the student.
        awaitingStudent: s.expectsStudentResponse,
      };
    };

    /** Any activity suppresses whatever is still in flight. */
    const suppressPending = () => {
      recordsRef.current = recordsRef.current.map(onStudentActivity);
    };

    const tick = async () => {
      const gate = gateNow();
      const now = Date.now();

      // Busy in any way: restart the clock and abandon anything pending.
      if (gate.studentActive || gate.requestInFlight || gate.pageHidden || gate.disconnected) {
        idleSinceRef.current = null;
        suppressPending();
        return;
      }
      if (!gate.awaitingStudent) {
        idleSinceRef.current = null;
        return;
      }

      if (idleSinceRef.current === null) idleSinceRef.current = now;

      const decision = shouldClaimNudge({
        policy: useNumeraStore.getState().inactivityPolicy,
        gate,
        elapsedMs: now - idleSinceRef.current,
        sinceLastNudgeMs: lastClaimAtRef.current === null ? null : now - lastClaimAtRef.current,
        nudgesThisTurn: nudgesThisTurnRef.current,
      });
      if (!decision.claim) return;

      const { claim, present, acknowledge } = optsRef.current;
      if (!claim || claimingRef.current) return;

      claimingRef.current = true;
      try {
        const id = await claim();
        if (!id) return;

        lastClaimAtRef.current = Date.now();
        nudgesThisTurnRef.current += 1;
        let record: NudgeRecord = {
          id,
          state: 'PENDING',
          tutorTurnId: useNumeraStore.getState().lastTutorTurnId,
        };
        recordsRef.current = [...recordsRef.current, record];

        // The student may have started working while the claim was in flight.
        // Re-read rather than trusting the gate from before the await.
        const after = gateNow();
        if (after.studentActive || !after.awaitingStudent) {
          suppressPending();
          return;
        }
        if (!mayPresent(record)) return;

        // One-way from here: only the acknowledgement is ever retried.
        record = markPresented(record);
        recordsRef.current = recordsRef.current.map((r) => (r.id === id ? record : r));
        present?.(id);

        if (acknowledge) {
          try {
            await acknowledge(id);
            recordsRef.current = recordsRef.current.map((r) =>
              r.id === id ? markAcknowledged(r) : r,
            );
          } catch {
            // Stays PRESENTED_UNACKNOWLEDGED — shown to the student but kept out
            // of learner history until the backend confirms it. Never re-present.
            console.warn('[nudge] presented but not acknowledged');
          }
        }
      } finally {
        claimingRef.current = false;
      }
    };

    const timer = setInterval(() => void tick(), TICK_MS);

    // A tab returning to the foreground starts a fresh interval rather than
    // resuming a stale one — the student has been away for an unknown time.
    const onVisibility = () => {
      idleSinceRef.current = null;
      suppressPending();
    };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      // Nothing claimed before teardown may be delivered afterwards.
      recordsRef.current = onDisconnect(recordsRef.current);
    };
  }, []);

  // A new tutor turn resets the per-turn allowance.
  const lastTutorTurnId = useNumeraStore((s) => s.lastTutorTurnId);
  useEffect(() => {
    nudgesThisTurnRef.current = 0;
    lastClaimAtRef.current = null;
    idleSinceRef.current = null;
  }, [lastTutorTurnId]);
}

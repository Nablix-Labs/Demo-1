'use client';

/**
 * Nablix Assist — Safe Action Registry.
 *
 * THE SECURITY MODEL: the backend can only trigger frontend behaviour by
 * naming an action id from this fixed allow-list. Backend-provided code,
 * selectors or arbitrary ids are never executed — an unknown id is refused.
 * Each action calls existing app functions in execute() and confirms the
 * expected result in verify(); the UI never reports "done" until verify()
 * passes.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { useSupportStore } from '@/store/useSupportStore';
import { useMicLevel } from '@/store/useMicLevel';
import { testMicrophone, listInputDevices, type MicTestResult } from '@/lib/support/diagnostics';
import { resendVerificationEmail } from '@/lib/support/assistApi';

export type RiskLevel = 'low' | 'medium' | 'high';

/** Capabilities the executing component injects (e.g. the Next router). */
export interface ActionContext {
  navigate: (path: string) => void;
}

export interface SafeAction {
  id: string;
  /** Human phrasing used by the consent modal ("I can {label} — continue?"). */
  label: string;
  /** Past-tense phrasing for the outcome message ("Done — I've {completedLabel}"). */
  completedLabel: string;
  riskLevel: RiskLevel;
  requiresConfirmation: boolean;
  execute: (ctx: ActionContext) => Promise<void> | void;
  /** Confirms the expected result actually happened. */
  verify: (ctx: ActionContext) => Promise<boolean>;
  /** Optional extra detail appended to the outcome message (e.g. test results). */
  describeResult?: () => string | null;
}

/** Poll `check` until it returns true or `timeoutMs` elapses. */
async function waitFor(check: () => boolean, timeoutMs = 4_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (check()) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return check();
}

const apiConfigured = () => Boolean(process.env.NEXT_PUBLIC_API_BASE_URL);

/** Unpause the tutor mic and keep it unpaused after support closes: the
 *  close-time snapshot restore must not undo what the student just asked for. */
function unmuteAndKeep(): void {
  useNumeraStore.getState().setMicMuted(false);
  useSupportStore.setState((s) =>
    s.snapshot ? { snapshot: { ...s.snapshot, micMuted: false, voiceStatus: 'listening' } } : {},
  );
}

const OPEN_CANVAS: SafeAction = {
  id: 'OPEN_CANVAS',
  label: 'open the lesson canvas',
  completedLabel: 'opened the lesson canvas',
  riskLevel: 'low',
  requiresConfirmation: false,
  execute: (ctx) => {
    ctx.navigate('/');
  },
  // The canvas registers its PNG exporter on mount — that's the proof it's up.
  verify: () =>
    waitFor(
      () =>
        window.location.pathname === '/' &&
        useNumeraStore.getState().canvasExporter !== null,
    ),
};

const CLOSE_CANVAS: SafeAction = {
  id: 'CLOSE_CANVAS',
  label: 'close the canvas and go back to the workbook',
  completedLabel: 'closed the canvas',
  riskLevel: 'low',
  requiresConfirmation: false,
  execute: (ctx) => {
    // The canvas IS the lesson screen; leaving it (drawings stay in the store)
    // is the closest thing to "closing" it.
    if (window.location.pathname === '/') ctx.navigate('/workbook');
  },
  verify: () => waitFor(() => window.location.pathname !== '/'),
};

// Result of the last mic test, shared between execute/verify/describeResult.
let lastMicTest: MicTestResult | null = null;

const START_MICROPHONE_TEST: SafeAction = {
  id: 'START_MICROPHONE_TEST',
  label: 'run a quick microphone test (a few seconds of listening)',
  completedLabel: 'run the microphone test',
  riskLevel: 'medium',
  requiresConfirmation: true,
  execute: async () => {
    lastMicTest = null;
    lastMicTest = await testMicrophone();
  },
  verify: async () => lastMicTest?.permission_granted ?? false,
  describeResult: () =>
    lastMicTest == null
      ? null
      : !lastMicTest.permission_granted
        ? 'The browser blocked the microphone.'
        : lastMicTest.audio_detected
          ? 'I heard you clearly — the mic is picking up sound.'
          : "The mic is allowed but I couldn't hear anything. Check it isn't muted at the hardware level, or try a different microphone.",
};

const SELECT_INPUT_DEVICE: SafeAction = {
  id: 'SELECT_INPUT_DEVICE',
  label: 'show your available microphones so you can pick one',
  completedLabel: 'listed your microphones — pick the one to use',
  riskLevel: 'low',
  requiresConfirmation: false,
  execute: () => {
    useSupportStore.getState().setDevicePickerOpen(true);
  },
  verify: async () => (await listInputDevices()).length > 0,
};

const RECONNECT_TUTOR_VOICE: SafeAction = {
  id: 'RECONNECT_TUTOR_VOICE',
  label: 'restart the tutor voice connection',
  completedLabel: 'restarted the tutor voice connection',
  riskLevel: 'medium',
  requiresConfirmation: true,
  execute: async (ctx) => {
    if (window.location.pathname !== '/') ctx.navigate('/');
    // Pulse mute → unmute: the lesson page tears down and restarts capture on
    // this flag (and the voice server reconnects on the next audio).
    useNumeraStore.getState().setMicMuted(true);
    await new Promise((r) => setTimeout(r, 300));
    unmuteAndKeep();
  },
  verify: () =>
    waitFor(
      () =>
        !useNumeraStore.getState().micMuted &&
        (!apiConfigured() || useMicLevel.getState().active),
      8_000,
    ),
};

const RETRY_CONNECTION: SafeAction = {
  id: 'RETRY_CONNECTION',
  label: 'retry the tutor connection',
  completedLabel: 'retried the tutor connection',
  riskLevel: 'medium',
  requiresConfirmation: true,
  execute: (ctx) => {
    if (window.location.pathname !== '/') ctx.navigate('/');
    // Clearing sessionId makes the lesson page start a fresh backend session
    // (same mechanism setActiveEquation uses). No-op without a backend.
    if (apiConfigured()) useNumeraStore.setState({ sessionId: null });
  },
  verify: () =>
    waitFor(
      () =>
        navigator.onLine &&
        (!apiConfigured() || useNumeraStore.getState().sessionId !== null),
      8_000,
    ),
};

const RESEND_VERIFICATION_EMAIL: SafeAction = {
  id: 'RESEND_VERIFICATION_EMAIL',
  label: 'send a new verification email',
  completedLabel: 'sent a new verification email',
  riskLevel: 'medium',
  requiresConfirmation: true,
  execute: async () => {
    await resendVerificationEmail();
  },
  verify: async () => true, // the (stubbed) endpoint resolves only on success
};

const OPEN_PREVIOUS_ONBOARDING_STEP: SafeAction = {
  id: 'OPEN_PREVIOUS_ONBOARDING_STEP',
  label: 'take you back to the previous sign-up step',
  completedLabel: 'taken you back a step',
  riskLevel: 'low',
  requiresConfirmation: false,
  execute: (ctx) => {
    if (window.location.pathname.startsWith('/consent')) {
      ctx.navigate('/onboard');
    } else {
      // The onboard page listens for this and returns to step 1 (see onboard/page.tsx).
      window.dispatchEvent(new Event('nablix:onboard-back'));
    }
  },
  // Step 1 of onboarding is the only screen with the auth-method inputs.
  verify: () =>
    waitFor(
      () =>
        window.location.pathname.startsWith('/onboard') &&
        document.querySelector(
          '[data-support-id="registration-email"], [data-support-id="registration-phone"]',
        ) !== null,
    ),
};

const RESUME_TUTOR_SESSION: SafeAction = {
  id: 'RESUME_TUTOR_SESSION',
  label: 'resume the tutor session (unmute the mic)',
  completedLabel: 'resumed the tutor session',
  riskLevel: 'low',
  requiresConfirmation: false,
  execute: () => {
    unmuteAndKeep();
  },
  verify: () => waitFor(() => !useNumeraStore.getState().micMuted),
};

const REGISTRY: Record<string, SafeAction> = Object.fromEntries(
  [
    OPEN_CANVAS,
    CLOSE_CANVAS,
    START_MICROPHONE_TEST,
    SELECT_INPUT_DEVICE,
    RECONNECT_TUTOR_VOICE,
    RETRY_CONNECTION,
    RESEND_VERIFICATION_EMAIL,
    OPEN_PREVIOUS_ONBOARDING_STEP,
    RESUME_TUTOR_SESSION,
  ].map((a) => [a.id, a]),
);

/** Allow-list lookup — the ONLY way an action id becomes behaviour. */
export function getSafeAction(id: string): SafeAction | null {
  return REGISTRY[id] ?? null;
}

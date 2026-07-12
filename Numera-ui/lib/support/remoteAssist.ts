'use client';

/**
 * Nablix Assist — remote assist (user side).
 *
 * Screen share is getDisplayMedia behind explicit consent (the browser's own
 * picker plus our consent modal), with a persistent "Support is viewing your
 * screen" banner and a Stop button while active (see RemoteAssistBanner).
 *
 * SECURITY: incoming agent commands are only ever { action_id } envelopes run
 * through the SAME safe action registry as everything else — an agent gets no
 * powers a student-triggered action doesn't have. No code, no selectors.
 *
 * The WebRTC signaling transport is the backend team's side of the contract
 * (see RemoteAssistSignal in assistApi.ts); until it exists, executeAgentCommand
 * is the single entry point the data channel will call.
 */

import { useSupportStore } from '@/store/useSupportStore';
import { getSafeAction, type ActionContext } from '@/lib/support/supportActions';

/** Agent → user command envelope: allow-listed action ids ONLY. */
export interface AgentCommandEnvelope {
  type: 'action';
  request_id: string;
  action_id: string;
}

export interface AgentCommandResult {
  request_id: string;
  action_id: string;
  status: 'refused' | 'verified' | 'failed';
}

let shareStream: MediaStream | null = null;

/**
 * Start sharing the screen with support. The caller must have collected
 * explicit consent first. Resolves false if the student cancels the browser
 * picker.
 */
export async function startScreenShare(): Promise<boolean> {
  if (shareStream) return true;
  try {
    shareStream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
  } catch {
    return false; // student dismissed the picker — that's a "no"
  }
  useSupportStore.getState().setRemoteAssistActive(true);
  // The browser's own "stop sharing" UI must also clear our state.
  shareStream.getVideoTracks().forEach((t) => {
    t.addEventListener('ended', stopScreenShare);
  });
  return true;
}

export function stopScreenShare(): void {
  shareStream?.getTracks().forEach((t) => t.stop());
  shareStream = null;
  useSupportStore.getState().setRemoteAssistActive(false);
}

export function isScreenSharing(): boolean {
  return shareStream !== null;
}

interface AgentCommandHooks {
  /** Ask the student to approve a requires-confirmation action. */
  requestConfirmation: (label: string) => Promise<boolean>;
  /** Surface progress/outcome in the support chat. */
  notify: (text: string) => void;
}

/**
 * Run one incoming agent command through the safe action registry. This is the
 * ONLY path from a remote agent to app behaviour.
 */
export async function executeAgentCommand(
  envelope: AgentCommandEnvelope,
  ctx: ActionContext,
  hooks: AgentCommandHooks,
): Promise<AgentCommandResult> {
  const base = { request_id: envelope.request_id, action_id: envelope.action_id };

  const action = envelope.type === 'action' ? getSafeAction(envelope.action_id) : null;
  if (!action) {
    hooks.notify('The support agent requested something outside the allowed actions, so it was refused.');
    return { ...base, status: 'refused' };
  }

  if (action.requiresConfirmation || action.riskLevel !== 'low') {
    const approved = await hooks.requestConfirmation(action.label);
    if (!approved) return { ...base, status: 'refused' };
  }

  await action.execute(ctx);
  const ok = await action.verify(ctx);
  hooks.notify(
    ok
      ? `Support asked me to ${action.label} — done and verified.`
      : `Support asked me to ${action.label}, but I couldn't verify it worked.`,
  );
  return { ...base, status: ok ? 'verified' : 'failed' };
}

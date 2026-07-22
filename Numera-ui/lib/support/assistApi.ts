'use client';

/**
 * Nablix Assist — backend adapter (STUBBED).
 *
 * The FE↔BE contract lives here so the UI works before the backend does:
 *
 *   POST /support/instruction  { context: SupportContext, issue: string }
 *     → SupportInstructionResponse
 *   POST /support/action-result  ActionResultReport   (fire-and-forget)
 *   POST /support/escalate  EscalationPayload → { reference_id }
 *   POST /support/screenshot  { screenshot_data_url } → { screenshot_reference }
 *     (server OCRs it; the client never stores the image)
 *   POST /auth/resend-verification  → 200 on success
 *   WS   /support/remote-assist  — RemoteAssistSignal both ways for WebRTC
 *     signaling; agent→user commands are AgentCommandEnvelope (allow-listed
 *     action ids only, see lib/support/remoteAssist.ts)
 *
 * Swap each stub body for the real call once the endpoints exist; callers
 * only depend on these function signatures. The stub answers with simple
 * keyword rules over the same context object the backend will receive.
 */

import type { SupportContext } from '@/lib/support/supportContext';
import type { SupportDiagnostics } from '@/lib/support/diagnostics';

export interface SupportInstructionResponse {
  instruction_text: string;
  highlight_support_id?: string;
  action_id?: string;
  requires_confirmation?: boolean;
  escalate?: boolean;
}

export interface ActionResultReport {
  action_id: string;
  verification_status: 'verified' | 'failed';
  context: SupportContext;
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Ask the support backend for the next instruction. */
export async function requestSupportInstruction(
  issue: string,
  context: SupportContext,
): Promise<SupportInstructionResponse> {
  await delay(400); // simulate the round-trip
  const q = issue.toLowerCase();

  if (!context.connection_status.online) {
    return {
      instruction_text:
        "You look offline. Check your internet connection, then tell me when you're back online and I'll reconnect the tutor.",
      action_id: 'RETRY_CONNECTION',
      requires_confirmation: true,
    };
  }

  if (/wrong (mic|microphone)|different (mic|microphone)|(pick|choose|select|switch).*(mic|microphone|input)/.test(q)) {
    return {
      instruction_text: "Let's pick the right microphone from the ones your browser can see.",
      action_id: 'SELECT_INPUT_DEVICE',
    };
  }

  if (/\bmic|microphone|hear|audio|sound\b/.test(q)) {
    if (context.mic_permission === 'denied') {
      return {
        instruction_text:
          'Your browser has blocked the microphone. Click the padlock icon in the address bar, allow the microphone, then reload. Meanwhile you can type to me here.',
      };
    }
    return {
      instruction_text:
        "Let's run a quick mic test — I'll listen for a couple of seconds while you say something.",
      action_id: 'START_MICROPHONE_TEST',
      requires_confirmation: true,
    };
  }

  if (/\bvoice\b.*(stop|drop|disconnect|cut|quiet|silent)|tutor (stopped|went quiet)/.test(q)) {
    return {
      instruction_text: 'The voice link may have dropped. I can restart it.',
      action_id: 'RECONNECT_TUTOR_VOICE',
      requires_confirmation: true,
    };
  }

  if (/\b(resume|unpause|paused|continue the lesson)\b/.test(q)) {
    return {
      instruction_text: "I'll resume the tutor session for you.",
      action_id: 'RESUME_TUTOR_SESSION',
    };
  }

  if (/\b(go|take me|went) back\b|previous step|last step/.test(q)) {
    return {
      instruction_text: "I'll take you back to the previous sign-up step.",
      action_id: 'OPEN_PREVIOUS_ONBOARDING_STEP',
    };
  }

  if (/\bconnect|disconnect|offline|frozen|stuck|not responding|reload\b/.test(q)) {
    return {
      instruction_text: 'The tutor connection may have dropped. I can retry it for you.',
      action_id: 'RETRY_CONNECTION',
      requires_confirmation: true,
    };
  }

  if (/\bcanvas|draw|write|working\b/.test(q)) {
    if (context.screen_id !== '/' || !context.canvas_status.open) {
      return {
        instruction_text: "I'll open the lesson canvas for you.",
        action_id: 'OPEN_CANVAS',
      };
    }
    return {
      instruction_text:
        'The canvas is already open — write your working with the pen, then tap Check to submit it.',
      highlight_support_id: 'check-answer',
    };
  }

  if (/\bcheck|submit|answer\b/.test(q)) {
    return {
      instruction_text: 'When your working is on the canvas, tap the Check button to submit it.',
      highlight_support_id: 'check-answer',
    };
  }

  if (/\bemail|verification|code|otp\b/.test(q)) {
    if (context.screen_id.startsWith('/consent')) {
      return {
        instruction_text:
          "If the code hasn't arrived, check your spam folder — or tap Resend code to get a new one.",
        highlight_support_id: 'resend-verification',
      };
    }
    return {
      instruction_text: 'I can send you a fresh verification email.',
      action_id: 'RESEND_VERIFICATION_EMAIL',
      requires_confirmation: true,
    };
  }

  return {
    instruction_text:
      "I'm not sure I can fix that one myself. Can you describe it differently — or I can pass this to the support team.",
    escalate: true,
  };
}

/** Ask the backend to resend the guardian verification email. */
export async function resendVerificationEmail(): Promise<void> {
  await delay(300);
  // Stub: resolves = sent. The real call will surface failures as a rejection.
  console.log('[nablix-assist] resend verification email');
}

/** Report the structured outcome of a safe action (fire-and-forget). */
export async function reportActionResult(report: ActionResultReport): Promise<void> {
  // Stub: the real endpoint will receive this exact shape.
  console.log('[nablix-assist] action result', report);
}

export interface EscalationPayload {
  issue: string;
  note: string;
  context: SupportContext;
  diagnostics: SupportDiagnostics;
  /** From uploadSupportScreenshot — only present with the student's consent. */
  screenshot_reference?: string;
}

/** Escalate to a human; returns the support reference id to show the student. */
export async function escalateToSupport(
  payload: EscalationPayload,
): Promise<{ reference_id: string }> {
  await delay(300);
  console.log('[nablix-assist] escalation', payload);
  return { reference_id: `NBX-${Date.now().toString(36).toUpperCase().slice(-6)}` };
}

/**
 * Hand a consented, masked screenshot to the support backend (which OCRs it).
 * The data URL is not kept client-side after this resolves.
 */
export async function uploadSupportScreenshot(
  screenshotDataUrl: string,
): Promise<{ screenshot_reference: string }> {
  await delay(300);
  console.log('[nablix-assist] screenshot upload', { bytes: screenshotDataUrl.length });
  return { screenshot_reference: `SHOT-${Date.now().toString(36).toUpperCase().slice(-6)}` };
}

/** WebRTC signaling envelope for remote assist — shape agreed with the BE team. */
export interface RemoteAssistSignal {
  type: 'offer' | 'answer' | 'ice';
  support_session_id: string;
  payload: unknown; // SDP or ICE candidate, opaque to this layer
}

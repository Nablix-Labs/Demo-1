/**
 * Nablix Assist — scenario tests.
 *
 * Covers the support playbook end to end at the unit/integration level:
 * instruction routing per scenario (mic denied, no signal, wrong mic, voice
 * disconnected, canvas, resend email, disconnection, unknown issue), the
 * safe-action allow-list, agent-command security, and close-and-return state
 * isolation.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { requestSupportInstruction } from '@/lib/support/assistApi';
import type { SupportContext } from '@/lib/support/supportContext';
import { getSafeAction } from '@/lib/support/supportActions';
import { executeAgentCommand } from '@/lib/support/remoteAssist';
import { useSupportStore } from '@/store/useSupportStore';
import { useNumeraStore } from '@/store/useNumeraStore';

/** A healthy on-lesson context; tests override what each scenario needs. */
function ctx(overrides: Partial<SupportContext> = {}): SupportContext {
  return {
    screen_id: '/',
    workflow_id: 'learning',
    current_step: 'lesson',
    mic_permission: 'granted',
    audio_input_detected: false,
    voice_session_status: 'listening',
    canvas_status: { open: true, item_count: 0 },
    connection_status: { online: true, api_configured: false, session_active: false },
    visible_error_code: null,
    ...overrides,
  };
}

describe('support instruction routing (stub adapter)', () => {
  it('mic permission denied → browser-settings guidance, no action', async () => {
    const res = await requestSupportInstruction(
      "my mic isn't working",
      ctx({ mic_permission: 'denied' }),
    );
    expect(res.instruction_text).toMatch(/blocked the microphone/i);
    expect(res.action_id).toBeUndefined();
  });

  it('mic issue with permission → runs the microphone test (confirmed)', async () => {
    const res = await requestSupportInstruction('there is no signal from my mic', ctx());
    expect(res.action_id).toBe('START_MICROPHONE_TEST');
    expect(res.requires_confirmation).toBe(true);
  });

  it('wrong microphone → SELECT_INPUT_DEVICE', async () => {
    const res = await requestSupportInstruction('I think it uses the wrong microphone', ctx());
    expect(res.action_id).toBe('SELECT_INPUT_DEVICE');
  });

  it('voice dropped → RECONNECT_TUTOR_VOICE (confirmed)', async () => {
    const res = await requestSupportInstruction('the voice suddenly stopped', ctx());
    expect(res.action_id).toBe('RECONNECT_TUTOR_VOICE');
    expect(res.requires_confirmation).toBe(true);
  });

  it('canvas not open → OPEN_CANVAS', async () => {
    const res = await requestSupportInstruction(
      "I can't open the canvas",
      ctx({ screen_id: '/workbook', canvas_status: { open: false, item_count: 0 } }),
    );
    expect(res.action_id).toBe('OPEN_CANVAS');
  });

  it('canvas open but not submitted → points at Check', async () => {
    const res = await requestSupportInstruction('how do I submit my canvas working?', ctx());
    expect(res.highlight_support_id).toBe('check-answer');
  });

  it('missing code on the consent screen → highlights Resend', async () => {
    const res = await requestSupportInstruction(
      "I didn't get the verification code",
      ctx({ screen_id: '/consent', workflow_id: 'consent' }),
    );
    expect(res.highlight_support_id).toBe('resend-verification');
  });

  it('missing code elsewhere → RESEND_VERIFICATION_EMAIL (confirmed)', async () => {
    const res = await requestSupportInstruction(
      'I never received the verification email',
      ctx({ screen_id: '/login', workflow_id: 'registration' }),
    );
    expect(res.action_id).toBe('RESEND_VERIFICATION_EMAIL');
    expect(res.requires_confirmation).toBe(true);
  });

  it('frozen/disconnected → RETRY_CONNECTION (confirmed)', async () => {
    const res = await requestSupportInstruction('everything is frozen', ctx());
    expect(res.action_id).toBe('RETRY_CONNECTION');
    expect(res.requires_confirmation).toBe(true);
  });

  it('offline → connection guidance regardless of wording', async () => {
    const res = await requestSupportInstruction(
      'nothing works',
      ctx({
        connection_status: { online: false, api_configured: false, session_active: false },
        visible_error_code: 'OFFLINE',
      }),
    );
    expect(res.action_id).toBe('RETRY_CONNECTION');
    expect(res.instruction_text).toMatch(/offline/i);
  });

  it('unknown issue → offers escalation', async () => {
    const res = await requestSupportInstruction('the moon is upside down', ctx());
    expect(res.escalate).toBe(true);
    expect(res.action_id).toBeUndefined();
  });
});

describe('safe action registry (allow-list)', () => {
  it('refuses unknown action ids', () => {
    expect(getSafeAction('FORMAT_DISK')).toBeNull();
    expect(getSafeAction('')).toBeNull();
    expect(getSafeAction('open_canvas')).toBeNull(); // ids are exact
  });

  it('every registered action has execute, verify and confirmation coherence', () => {
    const ids = [
      'OPEN_CANVAS',
      'CLOSE_CANVAS',
      'START_MICROPHONE_TEST',
      'SELECT_INPUT_DEVICE',
      'RECONNECT_TUTOR_VOICE',
      'RETRY_CONNECTION',
      'RESEND_VERIFICATION_EMAIL',
      'OPEN_PREVIOUS_ONBOARDING_STEP',
      'RESUME_TUTOR_SESSION',
    ];
    for (const id of ids) {
      const action = getSafeAction(id);
      expect(action, id).not.toBeNull();
      expect(typeof action!.execute).toBe('function');
      expect(typeof action!.verify).toBe('function');
      // Anything above low risk must ask the student first.
      if (action!.riskLevel !== 'low') expect(action!.requiresConfirmation).toBe(true);
    }
  });
});

describe('remote assist agent commands', () => {
  const noopCtx = { navigate: () => {} };

  it('refuses commands outside the allow-list', async () => {
    const notify = vi.fn();
    const result = await executeAgentCommand(
      { type: 'action', request_id: 'r1', action_id: 'RUN_EVAL' },
      noopCtx,
      { requestConfirmation: async () => true, notify },
    );
    expect(result.status).toBe('refused');
    expect(notify).toHaveBeenCalledWith(expect.stringMatching(/refused/i));
  });

  it('asks for confirmation on risk >= medium and honours a "no"', async () => {
    const requestConfirmation = vi.fn(async () => false);
    const result = await executeAgentCommand(
      { type: 'action', request_id: 'r2', action_id: 'RETRY_CONNECTION' },
      noopCtx,
      { requestConfirmation, notify: () => {} },
    );
    expect(requestConfirmation).toHaveBeenCalled();
    expect(result.status).toBe('refused');
  });

  it('runs a low-risk action and verifies it', async () => {
    useNumeraStore.getState().setMicMuted(true);
    const result = await executeAgentCommand(
      { type: 'action', request_id: 'r3', action_id: 'RESUME_TUTOR_SESSION' },
      noopCtx,
      { requestConfirmation: async () => true, notify: () => {} },
    );
    expect(result.status).toBe('verified');
    expect(useNumeraStore.getState().micMuted).toBe(false);
  });
});

describe('close-and-return state isolation', () => {
  beforeEach(() => {
    useSupportStore.setState({ open: false, snapshot: null, messages: [] });
  });

  it('open pauses the tutor; close restores the exact prior voice state', () => {
    const n = useNumeraStore.getState();
    n.setMicMuted(false); // student was live
    useNumeraStore.getState().setVoiceStatus('listening');

    useSupportStore.getState().openSupport();
    expect(useNumeraStore.getState().micMuted).toBe(true); // paused

    useSupportStore.getState().closeSupport();
    expect(useNumeraStore.getState().micMuted).toBe(false); // restored
    expect(useNumeraStore.getState().voiceStatus).toBe('listening');
  });

  it('support chat never touches the academic transcript', () => {
    const before = useNumeraStore.getState().transcript;
    useSupportStore.getState().openSupport();
    useSupportStore.getState().addMessage({ role: 'user', text: 'help!' });
    useSupportStore.getState().addMessage({ role: 'assist', text: 'on it' });
    useSupportStore.getState().closeSupport();
    expect(useNumeraStore.getState().transcript).toBe(before); // same reference — untouched
    expect(useSupportStore.getState().messages).toHaveLength(2); // kept for re-open
  });
});

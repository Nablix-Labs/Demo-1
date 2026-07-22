'use client';

/**
 * Nablix Assist — screen-state provider.
 *
 * Assembles the structured context the support backend needs to pick the next
 * instruction. PRIVACY RULE: this object must never include passwords, OTPs,
 * payment details or unnecessary personal data — only workflow position and
 * device/feature status. Field names are snake_case to match the FE↔BE
 * contract.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { useAuthStore } from '@/store/useAuthStore';
import { useMicLevel } from '@/store/useMicLevel';

export type MicPermission = 'granted' | 'denied' | 'prompt' | 'unknown';

export interface SupportContext {
  screen_id: string;
  workflow_id: 'registration' | 'consent' | 'learning';
  current_step: string;
  mic_permission: MicPermission;
  audio_input_detected: boolean;
  voice_session_status: string;
  canvas_status: { open: boolean; item_count: number };
  connection_status: { online: boolean; api_configured: boolean; session_active: boolean };
  visible_error_code: string | null;
}

async function queryMicPermission(): Promise<MicPermission> {
  try {
    // 'microphone' isn't in the lib.dom PermissionName union yet.
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName });
    return status.state;
  } catch {
    return 'unknown';
  }
}

export async function getSupportContext(): Promise<SupportContext> {
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  const n = useNumeraStore.getState();
  const auth = useAuthStore.getState();
  const mic = useMicLevel.getState();

  const workflow_id: SupportContext['workflow_id'] =
    pathname.startsWith('/onboard') || pathname.startsWith('/login')
      ? 'registration'
      : pathname.startsWith('/consent')
        ? 'consent'
        : 'learning';

  const online = typeof navigator !== 'undefined' ? navigator.onLine : true;

  return {
    screen_id: pathname,
    workflow_id,
    current_step: workflow_id === 'learning' ? n.flowStage : auth.accountStatus,
    mic_permission: await queryMicPermission(),
    audio_input_detected: mic.active && mic.levels.some((l) => l > 0.05),
    voice_session_status: n.micMuted ? 'muted' : n.voiceStatus,
    canvas_status: { open: n.canvasExporter !== null, item_count: n.items.length },
    connection_status: {
      online,
      api_configured: Boolean(process.env.NEXT_PUBLIC_API_BASE_URL),
      session_active: n.sessionId !== null,
    },
    visible_error_code: online ? null : 'OFFLINE',
  };
}

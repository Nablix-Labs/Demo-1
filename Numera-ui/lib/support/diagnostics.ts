'use client';

/**
 * Nablix Assist — client diagnostics.
 *
 * Everything the support flow needs to reason about voice problems: browser/OS,
 * connectivity, mic permission + devices, live audio detection, and the voice
 * session status. Same privacy rule as supportContext: device labels and
 * feature status only — never personal data.
 */

import { useNumeraStore } from '@/store/useNumeraStore';
import { useMicLevel } from '@/store/useMicLevel';
import { voiceStreamingEnabled } from '@/lib/runtimeConfig';
import { getPreferredMicId, audioConstraints } from '@/lib/support/micPreference';
import { type MicPermission } from '@/lib/support/supportContext';

export interface InputDevice {
  device_id: string;
  label: string; // e.g. "MacBook Pro Microphone" — empty until permission granted
}

export interface SupportDiagnostics {
  browser: string;
  os: string;
  online: boolean;
  mic_permission: MicPermission;
  input_devices: InputDevice[];
  selected_input: string | null; // preferred deviceId, null = browser default
  audio_input_detected: boolean;
  voice_status: string;
  mic_muted: boolean;
  api_configured: boolean;
  voice_ws_configured: boolean;
  session_active: boolean;
}

/** Coarse browser/OS from the user agent — for support triage, not analytics. */
function parseUserAgent(ua: string): { browser: string; os: string } {
  const browser = /edg\//i.test(ua)
    ? 'Edge'
    : /chrome\//i.test(ua)
      ? 'Chrome'
      : /safari\//i.test(ua) && /version\//i.test(ua)
        ? 'Safari'
        : /firefox\//i.test(ua)
          ? 'Firefox'
          : 'Unknown';
  const os = /windows/i.test(ua)
    ? 'Windows'
    : /mac os x/i.test(ua)
      ? 'macOS'
      : /android/i.test(ua)
        ? 'Android'
        : /iphone|ipad|ipos/i.test(ua)
          ? 'iOS'
          : /linux/i.test(ua)
            ? 'Linux'
            : 'Unknown';
  return { browser, os };
}

async function queryMicPermission(): Promise<MicPermission> {
  try {
    const status = await navigator.permissions.query({ name: 'microphone' as PermissionName });
    return status.state;
  } catch {
    return 'unknown';
  }
}

/** List audio inputs. Labels are blank until mic permission has been granted. */
export async function listInputDevices(): Promise<InputDevice[]> {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices
    .filter((d) => d.kind === 'audioinput')
    .map((d, i) => ({ device_id: d.deviceId, label: d.label || `Microphone ${i + 1}` }));
}

export async function collectDiagnostics(): Promise<SupportDiagnostics> {
  const n = useNumeraStore.getState();
  const mic = useMicLevel.getState();
  const { browser, os } = parseUserAgent(navigator.userAgent);
  return {
    browser,
    os,
    online: navigator.onLine,
    mic_permission: await queryMicPermission(),
    input_devices: await listInputDevices(),
    selected_input: getPreferredMicId(),
    audio_input_detected: mic.active && mic.levels.some((l) => l > 0.05),
    voice_status: n.voiceStatus,
    mic_muted: n.micMuted,
    api_configured: Boolean(process.env.NEXT_PUBLIC_API_BASE_URL),
    voice_ws_configured: voiceStreamingEnabled,
    session_active: n.sessionId !== null,
  };
}

export interface MicTestResult {
  permission_granted: boolean;
  audio_detected: boolean;
  /** 0–1 RMS peak over the test window. */
  peak_level: number;
}

/**
 * Short live mic check: capture for `durationMs`, measure the peak level, then
 * release the mic. Uses the same preferred-device constraints as the real
 * capture hooks so it tests what the tutor would actually hear.
 */
export async function testMicrophone(durationMs = 2500): Promise<MicTestResult> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: audioConstraints({ echoCancellation: true, noiseSuppression: true }),
    });
  } catch {
    return { permission_granted: false, audio_detected: false, peak_level: 0 };
  }

  const ctx = new AudioContext();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);

  let peak = 0;
  const deadline = Date.now() + durationMs;
  while (Date.now() < deadline) {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    peak = Math.max(peak, Math.sqrt(sum / buf.length));
    await new Promise((r) => setTimeout(r, 50));
  }

  stream.getTracks().forEach((t) => t.stop());
  void ctx.close();
  return { permission_granted: true, audio_detected: peak > 0.01, peak_level: peak };
}

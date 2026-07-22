'use client';

/**
 * Preferred microphone — set by Nablix Assist's SELECT_INPUT_DEVICE action so
 * a student on the wrong mic can switch without digging through browser
 * settings. Both capture hooks (useVoiceTurn, useVoiceStream) merge this into
 * their getUserMedia constraints; `ideal` (not `exact`) so a stale saved id
 * falls back to the default device instead of failing capture.
 */

const KEY = 'numera-mic-device';

export function getPreferredMicId(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(KEY);
}

export function setPreferredMicId(deviceId: string | null): void {
  if (typeof localStorage === 'undefined') return;
  if (deviceId) localStorage.setItem(KEY, deviceId);
  else localStorage.removeItem(KEY);
}

/** Base audio constraints + the preferred device, when one is set. */
export function audioConstraints(base: MediaTrackConstraints): MediaTrackConstraints {
  const deviceId = getPreferredMicId();
  return deviceId ? { ...base, deviceId: { ideal: deviceId } } : base;
}

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
 *
 * Phase 1 registers OPEN_CANVAS and RETRY_CONNECTION to prove the loop;
 * the rest of the registry lands in Phase 2.
 */

import { useNumeraStore } from '@/store/useNumeraStore';

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

const REGISTRY: Record<string, SafeAction> = {
  [OPEN_CANVAS.id]: OPEN_CANVAS,
  [RETRY_CONNECTION.id]: RETRY_CONNECTION,
};

/** Allow-list lookup — the ONLY way an action id becomes behaviour. */
export function getSafeAction(id: string): SafeAction | null {
  return REGISTRY[id] ?? null;
}

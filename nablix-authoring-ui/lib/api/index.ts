/**
 * Adapter selection. Default is the mock adapter so the portal runs standalone.
 * Set NEXT_PUBLIC_API_MODE=http (and NEXT_PUBLIC_AUTHORING_API_BASE) to talk to
 * the real backend authoring API once those endpoints exist (spec §16).
 */
import type { AuthoringApi } from './contracts';
import { mockApi } from './mockAdapter';
import { createHttpApi } from './httpAdapter';

const mode = process.env.NEXT_PUBLIC_API_MODE ?? 'mock';

export const api: AuthoringApi =
  mode === 'http'
    ? createHttpApi(process.env.NEXT_PUBLIC_AUTHORING_API_BASE ?? '/api/authoring')
    : mockApi;

export * from './contracts';

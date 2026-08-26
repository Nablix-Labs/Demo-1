/**
 * Fetches the Phase 4 work-artifact PDF as a Blob and hands back an object
 * URL, so `TutorStage` can point an iframe at it.
 *
 * An iframe given `pdf_url` directly cannot attach a bearer token, and the
 * backend proxy this hits requires one to enforce per-student ownership.
 * Routing through the shared `api` client picks up both `baseURL` and the
 * auth interceptor (lib/api.ts) — which a raw `<iframe src>` never could.
 *
 * The caller owns the returned URL's lifetime and must revoke it (see the
 * lifecycle precedent at lib/tts.ts's MediaSource object URL).
 */
import { api } from '@/lib/api';

export async function fetchWorkArtifactPdfUrl(pdfUrl: string): Promise<string> {
  const response = await api.get<Blob>(pdfUrl, { responseType: 'blob' });
  return URL.createObjectURL(response.data);
}

/**
 * Fetching the Phase 4 work-artifact PDF, and saying precisely why when it
 * cannot be shown.
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

/**
 * What the viewer should show. One boolean could not tell these apart, so a
 * revoked token, a deleted artifact and a truncated response all reported
 * "couldn't load" — indistinguishable to the approver, and to anyone they
 * escalated it to.
 */
export type PdfOutcome =
  | { kind: 'ready'; url: string }
  /** 401/403 — the caller may not read this artifact. */
  | { kind: 'unauthorized' }
  /** 404 — there is no such artifact. */
  | { kind: 'unavailable' }
  /** A response arrived but is not a usable PDF. */
  | { kind: 'invalid' }
  /** Anything else, with the message to show. */
  | { kind: 'error'; message: string };

/** The five bytes every PDF starts with. */
const PDF_SIGNATURE = '%PDF-';

function statusOf(err: unknown): number | null {
  const res = (err as { response?: { status?: unknown } } | null)?.response;
  return typeof res?.status === 'number' ? res.status : null;
}

/**
 * Is this actually a PDF?
 *
 * The status alone is not enough: a proxy that has lost the caller's session
 * can answer 200 with an HTML sign-in page, and an iframe pointed at that shows
 * a login form where the student's working should be. So the content type is
 * checked AND the first bytes are read — the type is a claim, the signature is
 * evidence.
 *
 * A body we cannot read is treated as invalid rather than waved through: this
 * viewer's whole job is to show a specific student's work, and showing
 * something unverified in its place is the failure worth avoiding.
 */
async function isPdf(blob: Blob): Promise<boolean> {
  if (blob.size === 0) return false;
  if (blob.type && !blob.type.toLowerCase().includes('application/pdf')) return false;
  try {
    const head = await blob.slice(0, PDF_SIGNATURE.length).text();
    return head === PDF_SIGNATURE;
  } catch {
    return false;
  }
}

/**
 * Load one work-artifact PDF, reporting exactly why when it cannot.
 *
 * Never throws: every failure is a state the viewer renders, because the
 * alternative is a caught exception collapsing back into one message.
 */
export async function loadWorkArtifactPdf(pdfUrl: string): Promise<PdfOutcome> {
  let blob: Blob;
  try {
    const response = await api.get<Blob>(pdfUrl, { responseType: 'blob' });
    blob = response.data;
  } catch (err) {
    const status = statusOf(err);
    if (status === 401 || status === 403) return { kind: 'unauthorized' };
    if (status === 404) return { kind: 'unavailable' };
    return {
      kind: 'error',
      message: err instanceof Error ? err.message : 'The document could not be loaded.',
    };
  }
  if (!(await isPdf(blob))) return { kind: 'invalid' };
  return { kind: 'ready', url: URL.createObjectURL(blob) };
}

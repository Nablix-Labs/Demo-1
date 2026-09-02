/**
 * The Phase 4 work-artifact viewer had one `pdfLoadFailed` boolean, so a
 * revoked token, a deleted artifact and a truncated response all rendered the
 * same message — an approver could not tell a permissions problem from a
 * missing file, and neither could anyone they reported it to.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const get = vi.fn();

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: (...args: unknown[]) => get(...args) },
}));

const axiosError = (status: number) =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status },
  });

describe('loading a work-artifact PDF', () => {
  const original = URL.createObjectURL;
  beforeEach(() => {
    get.mockReset();
    URL.createObjectURL = vi.fn(() => 'blob:mock-object-url');
  });
  afterEach(() => { URL.createObjectURL = original; });

  const load = async (url = '/work-artifacts/ART-1/pdf') => {
    const { loadWorkArtifactPdf } = await import('@/lib/workArtifactPdf');
    return loadWorkArtifactPdf(url);
  };

  it('returns ready with an object url for a real PDF', async () => {
    get.mockResolvedValue({ data: new Blob(['%PDF-1.4 real'], { type: 'application/pdf' }) });
    expect(await load()).toEqual({ kind: 'ready', url: 'blob:mock-object-url' });
  });

  it('distinguishes unauthorized from unavailable', async () => {
    get.mockRejectedValue(axiosError(401));
    expect((await load()).kind).toBe('unauthorized');
    get.mockRejectedValue(axiosError(403));
    expect((await load()).kind).toBe('unauthorized');
    get.mockRejectedValue(axiosError(404));
    expect((await load()).kind).toBe('unavailable');
  });

  it('reports any other failure as an error, not as a missing file', async () => {
    get.mockRejectedValue(axiosError(500));
    expect((await load()).kind).toBe('error');
  });

  it('rejects a response that is not a PDF', async () => {
    // The proxy returning an HTML login page with a 200 is the case that makes
    // a status check alone insufficient.
    get.mockResolvedValue({ data: new Blob(['<html>sign in</html>'], { type: 'text/html' }) });
    expect((await load()).kind).toBe('invalid');
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it('rejects an empty body', async () => {
    get.mockResolvedValue({ data: new Blob([], { type: 'application/pdf' }) });
    expect((await load()).kind).toBe('invalid');
  });

  it('rejects a body whose signature is not %PDF-', async () => {
    get.mockResolvedValue({ data: new Blob(['not really a pdf'], { type: 'application/pdf' }) });
    expect((await load()).kind).toBe('invalid');
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
